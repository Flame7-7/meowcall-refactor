from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from models import InfractionType

from core.cogs import CogBase
from core.errors.customDiscord import InvalidInput
from repositories.connectionRepository import ConnectionRepository
from repositories.userphoneRepository import UserphoneRepository
from services.moderation import ModerationService
from services.userphone import UserphoneService
from services.userService import UserService
from ui.layouts.commands.moderation.history import HistoryLayout
from ui.layouts.commands.moderation.modlogs import ModerationLogsLayout
from ui.layouts.commands.moderation.renderer import ModerationRenderer
from utils.autofills import punishment_reason_autocomplete
from utils.discord.validators import is_admin, is_moderator, is_staff
from utils.helpers import parse_duration_ms
from utils.redis.cache import CacheManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from core.bot import Bot


class Moderation(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None):
        super().__init__(bot, emoji)

    @staticmethod
    def _service(session: AsyncSession) -> ModerationService:
        return ModerationService(session)

    @staticmethod
    def _user_service(session: AsyncSession) -> UserService:
        return UserService(session)

    @staticmethod
    def _userphone_service(session: AsyncSession) -> UserphoneService:
        return UserphoneService(
            UserphoneRepository(session),
            ConnectionRepository(session),
        )

    @staticmethod
    def validate_input(
        user: discord.User | discord.Member | None,
        guild: discord.Guild | None,
    ) -> None:
        if not user and not guild:
            raise InvalidInput("You must input a value")
        if user is not None and guild is not None:
            raise InvalidInput("You must provide either a user, or guild.")

    # ── modlogs ───────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="modlogs",
        description="📖 - View the target's moderation history",
        aliases=["ml", "logs", "history"],
    )
    @app_commands.describe(
        user="The desired user to view the moderation history of",
        guild="The desired guild to view the moderation history of",
    )
    @is_staff()
    async def moderation_modlogs(
        self,
        ctx: commands.Context[Bot],
        user: discord.User | discord.Member | None = None,
        guild: discord.Guild | None = None,
    ):
        self.validate_input(user, guild)

        target = user if user is not None else guild
        layout = ModerationLogsLayout(ctx.author, target)
        await layout.build_container(self.bot, ctx, target)

    # ── modcalls ──────────────────────────────────────────────────────────────

    @commands.hybrid_group(name="modcalls")
    async def moderation_call(self, ctx: commands.Context[Bot]) -> None:
        pass

    @moderation_call.command(
        name="history",
        description="📲📄 - View a target's call history.",
    )
    @app_commands.describe(
        user="The desired user to view the call history of",
        guild="The desired guild to view the call history of",
    )
    @is_staff()
    async def moderation_call_history(
        self,
        ctx: commands.Context[Bot],
        user: discord.User | discord.Member | None = None,
        guild: discord.Guild | None = None,
    ):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        self.validate_input(user, guild)

        target = user if user is not None else guild

        async with self.bot.db.uow() as session:
            svc = self._userphone_service(session)
            history = await svc.get_call_history(
                user_id=user.id if user is not None else None,
                guild_id=guild.id if guild is not None else None,
            )

        if not history:
            view = ModerationRenderer.no_call_history(self.bot, target)
            return await ctx.send(embed=view.embed, view=view, ephemeral=True)

        history_layout = HistoryLayout(self.bot, ctx, ctx.author, history)
        await history_layout.build_container()
        return await ctx.send(view=history_layout, ephemeral=True)

    @moderation_call.command(
        name="fetch",
        description="📲 - View a specific call by its ID.",
    )
    @app_commands.describe(call="The ID of the call to be viewed")
    @is_staff()
    async def moderation_call_fetch(
        self,
        ctx: commands.Context[Bot],
        call: str,
    ):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        async with self.bot.db.uow() as session:
            svc = self._userphone_service(session)
            call_real = await svc.get_call_by_id(call)

        if not call_real:
            view = ModerationRenderer.not_found(self.bot, call)
            return await ctx.send(embed=view.embed, view=view, ephemeral=True)

        history_layout = HistoryLayout(self.bot, ctx, ctx.author, [call_real])
        await history_layout.build_container()
        return await ctx.send(view=history_layout, ephemeral=True)

    # ── ban ───────────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="ban",
        description="🔨 - Ban a target from the Meowcall system.",
        aliases=["b", "ba", "bann", "banish", "fuckoff"],
    )
    @app_commands.describe(
        user="The desired user to action",
        guild="The desired guild to action",
        reason="The reason for this punitive action",
        duration="The duration of the ban, 1m, 2h, 3d, 4w, 5mo, 6y…",
    )
    @app_commands.autocomplete(reason=punishment_reason_autocomplete)
    @is_staff()
    async def moderation_ban(
        self,
        ctx: commands.Context[Bot],
        user: discord.User | discord.Member | None,
        guild: discord.Guild | None,
        duration: str | None = None,
        *,
        reason: str | None = None,
    ) -> discord.Message:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        self.validate_input(user, guild)

        target = user if user is not None else guild

        try:
            parsed_duration = parse_duration_ms(duration) if duration else None
        except ValueError:
            view = ModerationRenderer.invalid_duration(self.bot)
            return await ctx.send(embed=view.embed, view=view, ephemeral=True)

        try:
            async with self.bot.db.uow() as uow:
                if user is not None:
                    user_svc = self._user_service(uow.session)
                    await user_svc.upsert_user(user)

                svc = self._service(uow.session)

                infraction = await svc.create_infraction(
                    mod_id=ctx.author.id,
                    user_id=user.id if user else None,
                    server_id=guild.id if guild else None,
                    infraction_type=InfractionType.BAN,
                    reason=reason if reason else "None provided",
                    duration_ms=parsed_duration,
                )

        except ValueError:
            view = ModerationRenderer.already_banned(self.bot, target)
            return await ctx.send(embed=view.embed, view=view, ephemeral=True)

        view = ModerationRenderer.banned(
            target=target,
            infraction=infraction,
            moderator=ctx.author,
            duration_text=duration,  # raw string e.g. "7d" — matches V1 format
            bot=self.bot,
        )
        response = await ctx.send(embed=view.embed, view=view, ephemeral=True)

        if user:
            # DM is best-effort and should not block command responsiveness.
            self.bot.loop.create_task(svc.notify_user(user, infraction))

        return response

    # ── unban ─────────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="unban",
        description="🔓 - Unban a target from the Meowcall system.",
        aliases=["ub", "uban", "unba", "unbann", "unfuckoff"],
    )
    @app_commands.describe(
        user="The desired user to action",
        guild="The desired guild to action",
        reason="The reason for the revocation of the punitive action",
    )
    @is_moderator()
    async def moderation_unban(
        self,
        ctx: commands.Context[Bot],
        user: discord.User | discord.Member | None = None,
        guild: discord.Guild | None = None,
        *,
        reason: str | None = None,
    ) -> discord.Message:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        self.validate_input(user, guild)

        target = user if user is not None else guild

        try:
            async with self.bot.db.uow() as uow:
                svc = self._service(uow.session)

                active_ban = await svc._mod_repo().get_active_by_type(
                    user_id=str(user.id) if user else None,
                    guild_id=str(guild.id) if guild else None,
                    infraction_type=InfractionType.BAN,
                )

                if not active_ban:
                    raise ValueError("No active ban infraction found for target.")

                await svc.revoke_infraction(
                    infraction_id=active_ban.id,
                    mod_id=str(ctx.author.id),
                    reason=reason,
                )

            await CacheManager.flush_userphone_access_cache(
                user_id=user.id if user else None,
                guild_id=guild.id if guild else None,
            )

        except ValueError:
            view = ModerationRenderer.not_banned(self.bot, target)
            return await ctx.send(embed=view.embed, view=view, ephemeral=True)

        view = ModerationRenderer.unbanned(
            target=target,
            infraction=active_ban,
            moderator=ctx.author,
        )
        return await ctx.send(embed=view.embed, view=view, ephemeral=True)

    # ── warn ──────────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="warn",
        description="⚠️ - Warn a target within the Meowcall system.",
        aliases=["w", "war", "warnn", "warning"],
    )
    @app_commands.describe(
        user="The desired user to action",
        guild="The desired guild to action",
        reason="The reason for this punitive action",
    )
    @app_commands.autocomplete(reason=punishment_reason_autocomplete)
    @is_staff()
    async def moderation_warn(
        self,
        ctx: commands.Context[Bot],
        user: discord.User | discord.Member | None = None,
        guild: discord.Guild | None = None,
        *,
        reason: str | None = None,
    ) -> discord.Message:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        self.validate_input(user, guild)

        target = user if user is not None else guild

        async with self.bot.db.uow() as uow:
            if user is not None:
                user_svc = self._user_service(uow.session)
                await user_svc.upsert_user(user)

            svc = self._service(uow.session)

            infraction = await svc.create_infraction(
                mod_id=ctx.author.id,
                user_id=user.id if user else None,
                server_id=guild.id if guild else None,
                infraction_type=InfractionType.WARNING,
                reason=reason if reason else "None provided",
            )

            all_infractions = await svc._mod_repo().list_infractions(
                user_id=str(user.id) if user else None,
                guild_id=str(guild.id) if guild else None,
            )
            total_warnings = sum(
                1 for inf in all_infractions
                if inf.type == InfractionType.WARNING
            )

            await CacheManager.flush_userphone_access_cache(
                user_id=user.id if user else None,
                guild_id=guild.id if guild else None,
            )

        if user:
            await svc.notify_user(user, infraction)

        view = ModerationRenderer.warned(
            target=target,
            infraction=infraction,
            moderator=ctx.author,
            total_warnings=total_warnings,
        )
        return await ctx.send(embed=view.embed, view=view, ephemeral=True)

    # ── revoke ────────────────────────────────────────────────────────────────

    @commands.hybrid_group(name="revoke")
    async def moderation_revoke(self, ctx: commands.Context[Bot]) -> None:
        pass

    @moderation_revoke.command(
        name="infraction",
        description="✏️ - Revoke a target's infraction within the Meowcall system.",
    )
    @app_commands.describe(
        infraction="The ID of the infraction to be revoked",
        reason="The reason for the revocation of the punitive action",
    )
    @is_moderator()
    async def moderation_revoke_infraction(
        self,
        ctx: commands.Context[Bot],
        infraction: str,
        *,
        reason: str | None = None,
    ) -> discord.Message:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        async with self.bot.db.uow() as uow:
            svc = self._service(uow.session)

            infraction_real = await svc.revoke_infraction(
                infraction_id=infraction,
                mod_id=ctx.author.id,
                reason=reason,
            )

        await CacheManager.flush_userphone_access_cache(
            user_id=infraction_real.userId
            if infraction_real and infraction_real.userId is not None
            else None,
            guild_id=infraction_real.serverId
            if infraction_real and infraction_real.serverId is not None
            else None,
        )

        if not infraction_real:
            view = ModerationRenderer.not_found(self.bot, infraction)
            return await ctx.send(embed=view.embed, view=view, ephemeral=True)

        view = ModerationRenderer.infraction_revoked(
            infraction=infraction_real,
            moderator=ctx.author,
        )
        return await ctx.send(embed=view.embed, view=view, ephemeral=True)

    # ── delete ────────────────────────────────────────────────────────────────

    @commands.hybrid_group(name="delete")
    async def moderation_delete(self, ctx: commands.Context[Bot]) -> None:
        pass

    @moderation_delete.command(
        name="infraction",
        description="🗑️ - Delete a target's infraction within the Meowcall system.",
    )
    @app_commands.describe(infraction="The ID of the infraction to be deleted")
    @is_admin()
    async def moderation_delete_infraction(
        self,
        ctx: commands.Context[Bot],
        infraction: str,
    ) -> discord.Message:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        async with self.bot.db.uow() as uow:
            svc = self._service(uow.session)

            infraction_real = await svc.delete_infraction(
                infraction_id=infraction,
            )

        await CacheManager.flush_userphone_access_cache(
            user_id=infraction_real.userId
            if infraction_real and infraction_real.userId is not None
            else None,
            guild_id=infraction_real.serverId
            if infraction_real and infraction_real.serverId is not None
            else None,
        )

        if not infraction_real:
            view = ModerationRenderer.not_found(self.bot, infraction)
            return await ctx.send(embed=view.embed, view=view, ephemeral=True)

        view = ModerationRenderer.infraction_deleted(
            infraction=infraction_real,
            moderator=ctx.author,
        )
        return await ctx.send(embed=view.embed, view=view, ephemeral=True)


async def setup(bot: Bot):
    await bot.add_cog(Moderation(bot, None))