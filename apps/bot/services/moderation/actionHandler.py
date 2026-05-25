from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import discord
from models import InfractionType
from services.userService import UserService
from ui.layouts.common.errors import ErrorLayout
from ui.layouts.common.success import SuccessLayout
from utils.discord.validators import is_staff_direct
from utils.formatting import ms_to_human

from .moderationService import NO_REASON, ModerationService
from .types import ActionType, ModerationTarget

if TYPE_CHECKING:
    from discord.ext import commands
    from main import Bot

    class SendKwargs(TypedDict, total=False):
        content: str
        embed: discord.Embed


class ModerationActionHandler:
    def __init__(
        self,
        bot: Bot,
        moderator: discord.User | discord.Member,
        locale: str,
        report_id: str | None = None,
    ):
        self.bot = bot
        self.moderator = moderator
        self.locale = locale
        self.constants = bot.constants
        self.report_id = report_id

    def _get_avatars_for_logging(
        self, target: ModerationTarget
    ) -> tuple[str | None, str]:
        """Get user and moderator avatars for event logging."""
        user_avatar = None
        if target.is_user and target.user:
            user_avatar = target.user.display_avatar.url
        moderator_avatar = self.moderator.display_avatar.url
        return user_avatar, moderator_avatar

    async def _send_error(
        self, ctx: discord.Interaction | commands.Context, message: str
    ):
        """Send a standardized error message."""
        await self.send_message(
            ctx,
            view=ErrorLayout(ctx.bot, "### Error!", message, None, False),
            ephemeral=True,
        )

    async def _send_success(
        self, ctx: discord.Interaction | commands.Context, message: str
    ):
        """Send a standardized success message."""
        await self.send_message(
            ctx, view=SuccessLayout("### Success!", message), ephemeral=True
        )

    def _validate_target(self, target: ModerationTarget) -> str | None:
        """Validate the moderation target, returning an error message if invalid."""
        is_valid, msg = target.validate()
        return None if is_valid else msg

    async def _create_infraction(
        self,
        modsvc: ModerationService,
        target: ModerationTarget,
        infraction_type: InfractionType,
        reason: str | None = None,
        duration_ms: int | None = None,
    ):
        """Create a new infraction."""
        user_avatar, moderator_avatar = self._get_avatars_for_logging(target)

        return await modsvc.create_infraction(
            mod_id=str(self.moderator.id),
            infraction_type=infraction_type,
            reason=reason or NO_REASON,
            duration_ms=duration_ms,
            user_id=target.target_id if target.is_user else None,
            server_id=target.target_id if target.is_server else None,
            server_name=target.target_name if target.is_server else None,
            user_avatar=user_avatar,
            moderator_avatar=moderator_avatar,
        )

    async def send_message(
        self,
        ctx: discord.Interaction | commands.Context,
        content: str | None = None,
        embed: discord.Embed | None = None,
        ephemeral: bool = False,
    ):
        """Send a message in response to an interaction or context."""
        kwargs: SendKwargs = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed

        if isinstance(ctx, discord.Interaction):
            if not ctx.response.is_done():
                await ctx.response.send_message(ephemeral=ephemeral, **kwargs)
            else:
                await ctx.followup.send(ephemeral=ephemeral, **kwargs)
        else:
            await ctx.send(**kwargs)

    async def handle_punitive_action(
        self,
        ctx: discord.Interaction | commands.Context,
        action: ActionType,
        target: ModerationTarget,
        reason: str | None = None,
        duration_ms: int | None = None,
    ):
        """Handle punitive actions (warn, mute, ban)."""
        if error_msg := self._validate_target(target):
            return await self._send_error(ctx, error_msg)

        if not await is_staff_direct(ctx):
            return

        action_map = {
            ActionType.WARN: InfractionType.WARNING,
            ActionType.MUTE: InfractionType.MUTE,
            ActionType.BAN: InfractionType.BAN,
        }
        infraction_type = action_map[action]

        try:
            async with self.bot.db.uow() as uow:
                # Ensure target user exists in database before creating infraction
                if target.user:
                    user_svc = UserService(uow.session)
                    await user_svc.upsert_user(target.user)
                modsvc = ModerationService(uow.session)
                await self._create_infraction(
                    modsvc, target, infraction_type, reason, duration_ms
                )
        except ValueError:
            target_type = "User" if target.is_user else "Server"
            state_map = {
                ActionType.MUTE: "muted",
                ActionType.BAN: "banned",
            }
            state = state_map.get(action, "")
            return await self._send_error(
                ctx, f"This {target_type} is already {state}."
            )

        await self._handle_report_resolution(action)

        action_name_map = {
            ActionType.WARN: "Warned",
            ActionType.MUTE: "Muted",
            ActionType.BAN: "Banned",
        }
        action_name = action_name_map[action]
        target_mention = (
            target.user.mention
            if target.is_user and target.user
            else target.target_name
        )
        description = f"{action_name} {target_mention}"

        if action == ActionType.MUTE and duration_ms:
            duration_str = ms_to_human(duration_ms)
            description += f" for {duration_str}"

        await self._send_success(ctx, description)

    async def handle_revoke_action(
        self,
        ctx: discord.Interaction | commands.Context,
        action: ActionType,
        target: ModerationTarget,
    ):
        """Handle revoke actions (unmute, unban)."""
        if error_msg := self._validate_target(target):
            return await self._send_error(ctx, error_msg)

        if not await is_staff_direct(ctx):
            return

        action_noun_map = {
            ActionType.UNMUTE: "mute",
            ActionType.UNBAN: "ban",
        }
        action_noun = action_noun_map[action]

        async with self.bot.db.uow() as uow:
            modsvc = ModerationService(uow.session)
            active_infractions = await modsvc.get_active_infractions(
                self.hub.id,
                user_id=target.target_id if target.is_user else None,
                server_id=target.target_id if target.is_server else None,
            )
            relevant_infractions = [
                inf
                for inf in active_infractions
                if inf.type in [InfractionType.BAN, InfractionType.MUTE]
            ]

            if not relevant_infractions:
                return await self._send_error(ctx, f"No active {action_noun}.")

            user_avatar, moderator_avatar = self._get_avatars_for_logging(target)

            for inf in relevant_infractions:
                await modsvc.revoke_infraction(
                    inf.id,
                    str(self.moderator.id),
                    user_avatar=user_avatar,
                    moderator_avatar=moderator_avatar,
                )

        await self._handle_report_resolution(action)
        await self._send_success(ctx, f"Revoked {action_noun}!")

    async def handle_global_blacklist_action(
        self,
        ctx: discord.Interaction | commands.Context,
        target: ModerationTarget,
        reason: str | None = None,
        duration_ms: int | None = None,
    ):
        """Handle global blacklist actions."""
        if not await is_staff_direct(ctx):
            return await self._send_error(
                ctx, "You must be Meowcall staff to use this."
            )

        is_valid, error_msg = target.validate()
        if not is_valid:
            if not error_msg:
                return
            return await self._send_error(ctx, error_msg)

        async with self.bot.db.uow() as uow:
            modsvc = ModerationService(uow.session)
            try:
                if target.is_user:
                    await modsvc.create_blacklist_entry(
                        user_id=target.target_id,
                        mod_id=str(self.moderator.id),
                        reason=reason or NO_REASON,
                        duration_ms=duration_ms,
                    )
                else:
                    await modsvc.create_server_blacklist_entry(
                        server_id=target.target_id,
                        mod_id=str(self.moderator.id),
                        reason=reason or NO_REASON,
                        duration_ms=duration_ms,
                    )
            except ValueError:
                return await self._send_error(ctx, "This user is already blacklisted")

        await self._handle_report_resolution(ActionType.BLACKLIST)
        mention = (
            target.user.mention
            if target.is_user and target.user
            else target.target_name
        )
        await self._send_success(ctx, f"Blacklisted {mention}")
