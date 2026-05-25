from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from core.cogs import CogBase
from discord import app_commands
from discord.ext import commands
from services.moderation.moderationService import ModerationService
from services.userService import UserService
from ui.layouts.commands.staff.official import OfficialLayout
from ui.layouts.common.errors import ErrorLayout
from ui.layouts.common.success import SuccessLayout
from utils.discord.validators import is_moderator
from utils.redis.cache import CacheManager

if TYPE_CHECKING:
    from core.bot import Bot
    from sqlalchemy.ext.asyncio import AsyncSession


class Staff(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None):
        super().__init__(bot, emoji)

    @staticmethod
    def _service(session: AsyncSession) -> ModerationService:
        return ModerationService(session)

    @staticmethod
    def _user_service(session: AsyncSession) -> UserService:
        return UserService(session)

    @commands.hybrid_group(
        name="validate",
    )
    # Doesn't require @is_staff() - Captured in command. Does not catch correctly if done on group.
    # This group is also a public command, therefore does not need the check
    async def staff_validate(self, ctx: commands.Context[Bot]):
        pass

    @staff_validate.command(
        name="official",
        description="✅ - Check if a user is a Meowcall staff member.",
    )
    @app_commands.describe(
        user="The desired user to validate",
    )
    async def staff_validate_official(
        self, ctx: commands.Context[Bot], user: discord.User | discord.Member
    ):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        view = OfficialLayout(ctx, ctx.author, user)
        await view.build_container()

    @commands.hybrid_group(
        name="blacklist",
    )
    @is_moderator()
    async def staff_blacklist(self, ctx: commands.Context[Bot]):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @staff_blacklist.command(
        name="add",
        description="🛠️ - Prevent a user from using the bot entirely.",
    )
    @app_commands.describe(
        user="The desired user to action",
        reason="The reason for this punitive action",
        duration="The duration of the blacklist, 1m, 2h, 3d, 4w, 5mo, 6y...",
    )
    @is_moderator()
    async def staff_blacklist_add(
        self,
        ctx: commands.Context[Bot],
        user: discord.User | discord.Member,
        duration: str | None = None,
        *,
        reason: str,
    ):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        try:
            async with self.bot.db.uow() as uow:
                user_svc = self._user_service(uow.session)
                await user_svc.upsert_user(user)

                svc = self._service(uow.session)
                await svc.create_blacklist_entry(
                    user_id=user.id,
                    mod_id=ctx.author.id,
                    reason=reason,
                    duration_ms=int(duration) if duration else None,
                )
            await CacheManager.flush_userphone_access_cache(user_id=user.id)
        except ValueError:
            return await ctx.send(
                view=ErrorLayout(
                    self.bot,
                    "### Already Blacklisted!",
                    f"{user.mention} (`{user.id}`) is already blacklisted from Meowcall.",
                    None,
                    False,
                ),
                ephemeral=True,
            )

        return await ctx.send(
            view=SuccessLayout(
                "### Blacklisted!",
                f"{user.mention} (`{user.id}`) has been blacklisted from Meowcall.",
            ),
            ephemeral=True,
        )

    @staff_blacklist.command(
        name="remove",
        description="🛠️ - Revoke a user's Meowcall blacklist",
    )
    @app_commands.describe(
        user="The desired user to action",
    )
    @is_moderator()
    async def staff_blacklist_remove(
        self, ctx: commands.Context[Bot], user: discord.User | discord.Member
    ):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        try:
            async with self.bot.db.uow() as uow:
                user_svc = self._user_service(uow.session)
                await user_svc.upsert_user(user)

                svc = self._service(uow.session)
                await svc.delete_blacklist_entry(user_id=user.id)
            await CacheManager.flush_userphone_access_cache(user_id=user.id)

        except ValueError:
            return await ctx.send(
                view=ErrorLayout(
                    self.bot,
                    "### Not Blacklisted!",
                    f"{user.mention} (`{user.id}`) is not blacklisted from Meowcall.",
                    None,
                    False,
                ),
                ephemeral=True,
            )

        return await ctx.send(
            view=SuccessLayout(
                "### Blacklist Removed!",
                f"{user.mention} (`{user.id}`) has been unblacklisted from Meowcall.",
            ),
            ephemeral=True,
        )


async def setup(bot: Bot):
    await bot.add_cog(Staff(bot, "🔨"))
