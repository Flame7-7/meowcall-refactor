from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import discord
import sentry_sdk as sdk
from discord import app_commands
from discord.ext import commands
from ui.layouts.common.errors import ErrorLayout
from utils import constants, logger

from .customDiscord import InteractionCheck, InvalidInput, RateLimited, UserBlacklisted

if TYPE_CHECKING:
    from core.bot import Bot

    SourceType = discord.Interaction[Bot] | commands.Context[Bot]

ERROR_MAP = {
    commands.BadArgument: "Invalid input. Please try agian.",
    discord.NotFound: "Asset not found. Please check my permissions.",
    discord.Forbidden: "I do not have permission to do that. Please check my permissions.",
    InteractionCheck: "You may not interact with this.",
    RateLimited: "Woah! Slow down, you are using commands too fast.",
    ValueError: "You have provided an invalid input, was it the correct type?",
}


def _capture_error(error: Exception, source: SourceType) -> str:
    is_interaction = isinstance(source, discord.Interaction)
    user = source.user if is_interaction else source.author
    bot = source.client if is_interaction else source.bot

    error_id = uuid.uuid4().hex[:16]

    if not constants.PRODUCTION:
        logger.error(f"Generated local Error ID: {error_id}")

    attributes: dict[str, str | int] = {
        "error.type": type(error).__name__,
        "error.id": error_id,
    }

    if hasattr(source, "command") and source.command:
        attributes["command.name"] = source.command.qualified_name
        if (
            is_interaction
            and (cmd_type := getattr(source.command, "type", None)) is not None
        ):
            attributes["commands.type"] = str(cmd_type)

    if isinstance(error, discord.HTTPException):
        attributes["http.status_code"] = error.status
        attributes["discord.http.code"] = error.code

    if (shard_id := getattr(bot, "shard_id", None)) is not None:
        attributes["discord.shard_id"] = str(shard_id)

    with sdk.push_scope() as scope:
        scope.set_tag("error_type", type(error).__name__)
        scope.set_tag("error_id", error_id)
        scope.set_extra("error_id", error_id)
        scope.set_level("error")
        scope.set_user({"id": str(user.id)})

        for key, value in attributes.items():
            scope.set_extra(key, value)

        sdk.capture_exception(error)

    return error_id


async def error_handler(source: SourceType, error: Exception) -> None:
    original_error = error
    # Unwrap nested command invoke errors (can be nested multiple levels)
    while isinstance(
        error,
        (
            commands.CommandInvokeError,
            commands.HybridCommandError,
            app_commands.CommandInvokeError,
        ),
    ):
        unwrapped = getattr(error, "original", None)
        if unwrapped is None:
            break
        error = unwrapped

    # Prevent double-handling for hybrid commands: both bot.tree.error and
    # on_command_error fire, but they unwrap to the same `error.original`.
    if getattr(error, "_handled", False):
        return
    error._handled = True  # type: ignore[attr-defined]

    # ── Silently ignored errors ──────────────────────────────────────
    if isinstance(
        error,
        (commands.CommandNotFound, commands.CheckFailure, app_commands.CheckFailure),
    ):
        return

    is_interaction = isinstance(source, discord.Interaction)
    user = source.user if is_interaction else source.author
    layout_title = "### Error!"
    layout_error = "An unexpected error occured. Try again, and if the error persists please contact support."
    error_id: str | None = None

    # ── Cooldown handling (both prefix and app_commands / hybrid) ────
    if isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
        retry = round(error.retry_after, 1)
        layout_error = f"🐾 Slow down! Try again in **{retry}s**."

    # ── Known error types from ERROR_MAP ─────────────────────────────
    elif any(isinstance(error, cls) for cls in ERROR_MAP):
        for error_cls, msg in ERROR_MAP.items():
            if isinstance(error, error_cls):
                layout_error = msg
                break

    # ── Specific error types with custom messages ────────────────────
    elif isinstance(error, commands.MissingRequiredArgument):
        layout_error = (
            f"You must pass the {error.param.name} value when using this command."
        )
    elif isinstance(error, discord.HTTPException) and error.code == 10062:
        layout_error = "Discord could not process that request. Please try again."
    elif isinstance(error, commands.MissingPermissions):
        layout_title = "### Insufficient Permissions"
        layout_error = "You do not have sufficient permissions to do this."
    elif isinstance(error, UserBlacklisted):
        layout_title = "### Blacklisted"
        layout_error = getattr(error, "message", str(error))
    elif isinstance(error, (InteractionCheck, InvalidInput)):
        layout_error = getattr(error, "message", str(error))

    # ── Truly unhandled — log, capture, and assign error ID ──────────
    else:
        logger.error(
            "Unhandled error | error_type=%s command=%s guild_id=%s channel_id=%s author_id=%s error=%s",
            type(error).__name__,
            getattr(getattr(source, "command", None), "qualified_name", None),
            source.guild.id if source.guild else None,
            source.channel.id
            if hasattr(source, "channel") and source.channel
            else None,
            user.id,
            original_error,
            exc_info=original_error,
        )

        error_id = _capture_error(original_error, source) or "unknown"
        layout_title = "### Whoops!"

    bot = source.client if is_interaction else source.bot
    layout_view = ErrorLayout(bot, layout_title, layout_error, error_id)

    try:
        if is_interaction:
            interaction = cast(discord.Interaction, source)
            respond = (
                interaction.followup.send
                if interaction.response.is_done()
                else interaction.response.send_message
            )
            await respond(view=layout_view, ephemeral=True)
        else:
            ctx = cast(commands.Context, source)
            await ctx.send(view=layout_view)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        try:
            await user.send(view=layout_view)
        except Exception as exc:
            logger.debug("Failed to DM error layout to user %s: %s", user.id, exc)

    if error_id:
        dguild = await bot.fetch_guild(1508007962931888128)
        dchannel = await dguild.fetch_channel(1508007964949352497)
        await dchannel.send(
            view=ErrorLayout(
                bot, layout_title, layout_error, error_id, True, source, error, user
            )
        )
