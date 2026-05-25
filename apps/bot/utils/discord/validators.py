from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from core.errors.customDiscord import InteractionCheck
from repositories.moderationRepository import ModerationRepository
from utils.discord.errors import send_error_message
from utils import redis_client, logger

if TYPE_CHECKING:
    from core.bot import Bot

STAFF_GUILD_ID = 1508007962931888128

STAFF_ROLE_ID   = 1508007962986414171
MOD_ROLE_ID     = 1508007962986414173
ADMIN_ROLE_ID   = 1508007962986414175

STAFF_MAP: dict[int, str] = {
    1508007962986414178: "Core Team",
    1508007962986414174: "Developer",
    1508007962986414175: "Administrator",
    1508007962986414173: "Moderator",
    1508007962986414172: "Trial Moderator",
}


async def _resolve_member(
    bot: "Bot", uid: int
) -> discord.Member | None:
    """Return a Member from cache, falling back to a single fetch if needed."""
    guild = bot.get_guild(STAFF_GUILD_ID)
    if guild is None:
        try:
            guild = await bot.fetch_guild(STAFF_GUILD_ID)
        except discord.HTTPException:
            return None

    member = guild.get_member(uid)
    if member is None:
        try:
            member = await guild.fetch_member(uid)
        except (discord.NotFound, discord.HTTPException):
            return None

    return member


async def fetch_staff_position(
    ctx: commands.Context, uid: int | None = None
) -> str | None:
    uid = uid or ctx.author.id
    member = await _resolve_member(ctx.bot, uid)
    if member is None:
        return None

    member_role_ids = {role.id for role in member.roles}
    return next(
        (title for role_id, title in STAFF_MAP.items() if role_id in member_role_ids),
        None,
    )


async def is_staff_direct(ctx: commands.Context, uid: int | None = None) -> bool:
    uid = uid or ctx.author.id

    if uid in ctx.bot.staff_ids:
        return True

    member = await _resolve_member(ctx.bot, uid)
    if member is None:
        return False

    if any(role.id == STAFF_ROLE_ID for role in member.roles):
        ctx.bot.staff_ids.add(uid)
        return True

    return False


def is_staff():
    async def predicate(ctx: commands.Context["Bot"]):
        if not await is_staff_direct(ctx):
            await send_error_message(
                ctx, "You must be a Meowcall staff member to use this command.", ephemeral=True
            )
            return False
        return True

    return commands.check(predicate)


async def is_moderator_direct(ctx: commands.Context, uid: int | None = None) -> bool:
    uid = uid or ctx.author.id

    if uid in ctx.bot.moderator_ids:
        return True

    member = await _resolve_member(ctx.bot, uid)
    if member is None:
        return False

    if any(role.id == MOD_ROLE_ID for role in member.roles):
        ctx.bot.moderator_ids.add(uid)
        return True

    return False


def is_moderator():
    async def predicate(ctx: commands.Context["Bot"]):
        if not await is_moderator_direct(ctx):
            await send_error_message(
                ctx, "You must be a Meowcall moderator to use this command.", ephemeral=True
            )
            return False
        return True

    return commands.check(predicate)


async def is_admin_direct(ctx: commands.Context, uid: int | None = None) -> bool:
    uid = uid or ctx.author.id

    if uid in ctx.bot.admin_ids:
        return True

    member = await _resolve_member(ctx.bot, uid)
    if member is None:
        return False

    if any(role.id == ADMIN_ROLE_ID for role in member.roles):
        ctx.bot.admin_ids.add(uid)
        return True

    return False


def is_admin():
    async def predicate(ctx: commands.Context["Bot"]):
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(ephemeral=True)
            except discord.HTTPException:
                pass

        if not await is_admin_direct(ctx):
            await send_error_message(
                ctx, "You must be a Meowcall Administrator to use this command.", ephemeral=True
            )
            return False
        return True

    return commands.check(predicate)

async def is_blacklisted(bot: Bot, user: discord.abc.User | None) -> bool:
    if user is None:
        return False

    cache_key = f"blacklist:{user.id}"
    try:
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return cached == "1"
    except Exception:
        pass  # Redis down → fall through to DB

    try:
        async with bot.db.uow() as uow:
            moderation_repository = ModerationRepository(uow.session)
            result = await moderation_repository.is_user_blacklisted(user.id)

        try:
            await redis_client.set(cache_key, "1" if result else "0", ex=5000)
        except Exception:
            pass  # Cache write failure is non-fatal

        return result
    except Exception as e:
        logger.error(f"DB error checking blacklist for {user.id}: {e}")
        return False  # Fail open — don't block users on DB outage


async def interaction_check(
    interaction: discord.Interaction,
    user: discord.abc.User | None,
    target_user: discord.abc.User | None,
) -> bool:
    if user is None or target_user is None:
        return True

    if user.id == target_user.id:
        return True

    raise InteractionCheck()