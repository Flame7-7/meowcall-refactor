from __future__ import annotations

import builtins
import inspect
from typing import TYPE_CHECKING

import aiohttp
import discord
from core.cogs import CogBase
from discord import app_commands
from discord.ext import commands
from utils import redis_client
from utils.patterns import Patterns

if TYPE_CHECKING:
    from core.bot import Bot


def _is_exception_type(value: object) -> bool:
    return inspect.isclass(value) and issubclass(value, BaseException)


def resolve_exception(name: str):
    # 1. Check Python built-in exceptions (ValueError, TypeError, etc.)
    exc = getattr(builtins, name, None)
    if _is_exception_type(exc):
        return exc

    # 2. Check your globals (custom errors like InvalidInput, etc.)
    exc = globals().get(name)
    if _is_exception_type(exc):
        return exc

    return None


class Developer(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None):
        super().__init__(bot, emoji)

    @commands.hybrid_command(
        name="dev_cache_flush", description="A developer only command"
    )
    @app_commands.allowed_installs(False, True)
    @commands.is_owner()
    async def flush_cache(self, ctx: commands.Context[Bot], key: str | None = None):
        if not key:
            val = await redis_client.flushall()
        else:
            val = await redis_client.delete(key)

        await ctx.send(val)

    @commands.hybrid_command(
        name="dev_sync_staff", description="A developer only command"
    )
    @app_commands.allowed_installs(False, True)
    @commands.is_owner()
    async def sync_staff(self, ctx: commands.Context[Bot]):
        await self.bot.sync_staff_ids()
        await ctx.send(len(self.bot.staff_ids))

    @commands.hybrid_command(
        name="dev_raise_error", description="A developer only command"
    )
    @app_commands.allowed_installs(False, True)
    @commands.is_owner()
    async def raise_error(self, ctx: commands.Context, exception: str):
        exc_type = resolve_exception(exception)

        if not exc_type:
            raise ValueError(f"Unknown exception type: {exception}")

        raise exc_type(f"Raised dynamically: {exception}")

    @commands.hybrid_command(
        name="dev_check_message", description="A developer only command"
    )
    @app_commands.allowed_installs(False, True)
    @commands.is_owner()
    async def check_message(self, ctx: commands.Context[Bot], message_link: str):
        await ctx.interaction.response.defer()

        from services.userphone.validationService import ValidationService

        match = Patterns.MESSAGE_LINK.match(message_link)
        if not match:
            return await ctx.send("Invalid message link")

        channel = await self._fetch_channel(ctx, int(match.group("channel_id")))
        message = await channel.fetch_message(int(match.group("message_id")))

        async with aiohttp.ClientSession() as session:
            svc = ValidationService(session)
            result = await svc.validate_message(message)

        await ctx.send(content=f"Valid: {result.valid} | Reason: {result.reason}")

    async def _fetch_channel(self, ctx: commands.Context[Bot], channel_id: int):
        channel = ctx.guild.get_channel(channel_id)
        if channel is not None:
            return channel

        return await ctx.bot.fetch_channel(channel_id)


async def setup(bot: Bot):
    await bot.add_cog(Developer(bot, "⚒️"))
