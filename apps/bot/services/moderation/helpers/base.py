from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from core.cogs import CogBase
from discord.ext import commands
from services.moderation.actionHandler import ModerationActionHandler
from services.moderation.helpers.helpers import parse_args_for_target_and_reason
from services.moderation.types import ActionType, ModerationTarget
from utils import logger

if TYPE_CHECKING:
    from core.bot import Bot


class ModerationBaseCog(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None) -> None:
        super().__init__(bot, emoji)

    async def _send_ephemeral(
        self, ctx: discord.Interaction | commands.Context, content: str
    ) -> None:
        if isinstance(ctx, commands.Context):
            await ctx.send(content)
        else:
            if ctx.response.is_done():
                await ctx.followup.send(content, ephemeral=True)
            else:
                await ctx.response.send_message(content, ephemeral=True)

    async def execute_direct_action(
        self,
        ctx: discord.Interaction | commands.Context,
        action: ActionType,
        target: ModerationTarget,
        args: str,
    ) -> None:
        """Route the action to the appropriate handler method."""
        is_valid, err = target.validate()
        if not is_valid:
            await self._send_ephemeral(ctx, err or "Invalid moderation target.")
            return

        reason, duration_ms, _ = parse_args_for_target_and_reason(args, action)

        moderator = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        handler = ModerationActionHandler(self.bot, moderator)

        if action in (ActionType.WARN, ActionType.BAN):
            await handler.handle_punitive_action(
                ctx, action, target, reason, duration_ms
            )
        elif action in (ActionType.UNBAN,):
            await handler.handle_revoke_action(ctx, action, target, reason)
        else:
            logger.warning(f"Unhandled moderation action type: {action.value}")
            await self._send_ephemeral(
                ctx, f"Action `{action.value}` is not supported."
            )

    async def handle_no_target_error(
        self, ctx: discord.Interaction | commands.Context
    ) -> None:
        await self._send_ephemeral(
            ctx,
            "❌ No valid target was found. Please provide a user or guild ID/mention.",
        )
