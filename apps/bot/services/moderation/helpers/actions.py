from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from services.moderation.types import ActionType, ModerationTarget
from utils.patterns import Patterns

if TYPE_CHECKING:
    from .base import ModerationBaseCog


@dataclass
class ParsedTarget:
    user: discord.User | None = None
    guild: discord.Guild | None = None

    @property
    def is_empty(self) -> bool:
        return not any([self.user, self.guild])


class ModerationActionCommands:
    def __init__(self, cog: ModerationBaseCog):
        self.cog = cog
        self.bot = cog.bot

    async def _resolve_identifier(self, target_id: int) -> ParsedTarget:
        guild = self.bot.get_guild(target_id)
        if guild:
            return ParsedTarget(guild=guild)

        try:
            user = self.bot.get_user(target_id) or await self.bot.fetch_user(target_id)
            return ParsedTarget(user=user)
        except (discord.NotFound, discord.HTTPException):
            return ParsedTarget()

    async def parse_target_from_str(self, input_str: str) -> ParsedTarget:
        id_match = Patterns.DISCORD_ID_OR_MENTION.match(input_str)
        if id_match:
            try:
                id_str = id_match.group("discord_id")
                if id_str:
                    target_id = int(id_str)
                    return await self._resolve_identifier(target_id)
            except (ValueError, TypeError):
                pass

        return ParsedTarget()

    async def execute_mod_action(
        self,
        ctx: discord.Interaction | commands.Context,
        action: ActionType,
        target_str: str,
        args: str,
    ) -> None:
        # Only defer if this is an Interaction (slash command)
        if isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
            await ctx.response.defer()

        target = await self.parse_target_from_str(target_str)

        if target.user or target.guild:
            mod_target = ModerationTarget(user=target.user, guild=target.guild)
            await self.cog.execute_direct_action(ctx, action, mod_target, args)
            return

        await self.cog.handle_no_target_error(ctx)
