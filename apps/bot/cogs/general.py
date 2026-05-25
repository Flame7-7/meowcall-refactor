from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import discord
from core.cogs import CogBase
from discord import app_commands
from discord.ext import commands
from repositories.userRepository import UserRepository
from services.leaderboardService import LeaderboardService
from ui.layouts.commands.general.about import AboutLayout
from ui.layouts.commands.general.help import HelpLayout
from ui.layouts.commands.general.links import LinksLayout
from ui.layouts.commands.general.stats import StatsLayout
from utils import logger

if TYPE_CHECKING:
    from core.bot import Bot


class General(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None):
        super().__init__(bot, emoji)

    async def _visible_commands(
        self, ctx: commands.Context[Bot]
    ) -> list[commands.Command]:
        visible: list[commands.Command] = []
        suppress_flag_name = "_suppress_check_errors"
        previous_suppress_flag = getattr(ctx, suppress_flag_name, None)
        setattr(ctx, suppress_flag_name, True)

        try:
            for command in self.bot.walk_commands():
                cog_name = command.cog_name
                if not cog_name or cog_name in ("Group", "Jishaku", "Help"):
                    continue
                if command.hidden:
                    continue
                if (
                    ctx.author.id not in self.bot.staff_ids
                    and cog_name in ("Moderation", "Staff")
                    and command.qualified_name not in {"validate official"}
                ):
                    continue
                if (
                    ctx.author.id not in self.bot.constants._get_auth_users()
                    and cog_name in ("Developer")
                ):
                    continue
                if isinstance(command, commands.Group) and command.commands:
                    continue
                try:
                    if not await command.can_run(ctx):
                        continue
                except Exception:
                    continue
                visible.append(command)
        finally:
            if previous_suppress_flag is None:
                delattr(ctx, suppress_flag_name)
            else:
                setattr(ctx, suppress_flag_name, previous_suppress_flag)

        return visible

    @staticmethod
    def _format_line(command: commands.Command) -> str:
        description = (
            command.description or command.short_doc or "No description provided."
        )
        command_link = (
            f"</{command.qualified_name}:{command.id}>"
            if hasattr(command, "id") and command.id
            else f"`/{command.qualified_name}`"
        )

        if command.aliases:
            prefix_alts = " ".join(f"`m.{a}`" for a in command.aliases[:2])
            return f"{command_link} {prefix_alts}\n-# {description}"

        return f"{command_link}\n-# {description}"

    @commands.hybrid_command(
        name="help", description="❓ - Display all Meowcall commands available to you."
    )
    @app_commands.describe(query="Search for a specific command")
    async def general_help(
        self, ctx: commands.Context[Bot], *, query: str | None = None
    ) -> None:
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        visible = await self._visible_commands(ctx)

        if query:
            lowered = query.lower().strip()
            visible = [c for c in visible if lowered in c.qualified_name.lower()]

        commands_by_category: dict[str, list[str]] = {}
        for command in visible:
            cog_name = command.cog_name or "Other"
            if command.qualified_name in ("validate official",):
                category = "🌐 General"
            else:
                cog = self.bot.get_cog(cog_name)
                emoji = (
                    f"{cog.emoji} "
                    if cog and hasattr(cog, "emoji") and cog.emoji
                    else ""
                )
                category = f"{emoji}{cog_name}"
            commands_by_category.setdefault(category, []).append(
                self._format_line(command)
            )

        if not commands_by_category:
            await ctx.send(
                "No commands found matching your criteria. 😺", ephemeral=True
            )
            return

        view = HelpLayout(self.bot, ctx.author, commands_by_category)
        await view.send(ctx)

    @commands.hybrid_command(
        name="stats",
        description="📊 - View Meowcall's metrics.",
        aliases=["statistics", "stat", "statss", "metrics"],
    )
    async def general_stats(self, ctx: commands.Context[Bot]):
        await ctx.send(view=StatsLayout(self.bot))

    @commands.hybrid_command(
        name="links",
        description="🔗 - Useful, verified links for Meowcall.",
        aliases=["link", "linkss", "url", "urls"],
    )
    async def general_links(self, ctx: commands.Context[Bot]):
        await ctx.send(view=LinksLayout(self.bot))

    @commands.hybrid_command(
        name="about",
        description="❓ - Find out who we are, and what we do.",
        aliases=["info", "information", "abou", "aboutt"],
    )
    async def general_about(self, ctx: commands.Context[Bot]):
        await ctx.send(view=AboutLayout(self.bot))

    @commands.hybrid_command(
        name="invite",
        description="➕ - Invite Meowcall to your own server!",
        aliases=["add", "meowcall", "inv", "invit", "invitee"],
    )
    async def general_invite(self, ctx: commands.Context[Bot]):
        await ctx.send(view=LinksLayout(self.bot))

    @commands.hybrid_command(
        name="support",
        description="❓ - Looking for help, or to just join our community?",
        aliases=["appeal", "us", "suppor", "supportt"],
    )
    async def general_support(self, ctx: commands.Context[Bot]):
        await ctx.send(view=LinksLayout(self.bot))

    @commands.hybrid_command(
        name="vote",
        description="📈 - Vote for Meowcall on top.gg to gain perks!",
        aliases=["perks", "perk", "vot", "votee"],
    )
    async def general_vote(self, ctx: commands.Context[Bot]):
        await ctx.send(view=LinksLayout(self.bot))

    @commands.hybrid_command(
        name="ping",
        description="🏓 - View Meowcall metrics.",
    )
    async def general_ping(self, ctx: commands.Context[Bot]):
        await ctx.send(view=StatsLayout(self.bot))

    @commands.hybrid_command(
        name="mystats",
        description="📊 - View your personal global statistics.",
        aliases=["mystat", "mystatss", "me"],
    )
    async def mystats(self, ctx: commands.Context[Bot]):
        async with self.bot.db.uow() as uow:
            repo = UserRepository(uow.session)
            user = await repo.get_by_id(ctx.author.id)

            embed = discord.Embed(
                title="📊 Your Global Statistics",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(
                name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url
            )
            embed.set_footer(text="MeowCall Global Stats")

            if user:
                call_count = user.callCount or 0
                msg_count = user.messageCount or 0
                call_rank = await repo.get_rank_by_call_count(ctx.author.id)
                msg_rank = await repo.get_rank_by_message_count(ctx.author.id)
                embed.add_field(
                    name="📞 Total Calls",
                    value=f"`{call_count}` (Rank: #{call_rank or '?'})",
                    inline=True,
                )
                embed.add_field(
                    name="💬 Total Messages",
                    value=f"`{msg_count}` (Rank: #{msg_rank or '?'})",
                    inline=True,
                )
                if user.lastMessageAt:
                    embed.add_field(
                        name="🕐 Last Activity",
                        value=discord.utils.format_dt(user.lastMessageAt, "R"),
                        inline=False,
                    )
            else:
                embed.description = "You haven't interacted with MeowCall yet! Use `/call` to get started. 😺"

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="leaderboard",
        description="🏆 - View the global MeowCall leaderboards.",
        aliases=["lb", "top"],
    )
    @app_commands.describe(
        type="The type of leaderboard to view (calls or messages).",
        limit="The number of users to show (default 10, max 50).",
    )
    async def leaderboard(
        self,
        ctx: commands.Context[Bot],
        type: Literal["calls", "messages"] = "calls",
        limit: int = 10,
    ):
        if limit < 1 or limit > 50:
            limit = 10
        async with self.bot.db.uow() as uow:
            service = LeaderboardService(uow.session, self.bot)
            embed = await service.get_user_leaderboard_embed(type, limit)
            await ctx.send(embed=embed)

    # ==================================================================
    # Event listeners
    # ==================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Reply with a help hint when the bot is mentioned with no other content."""
        try:
            if not message or not message.channel:
                return
            if message.author.bot or message.webhook_id:
                return
            if self.bot.user not in message.mentions:
                return
            if message.content.strip() not in (
                f"<@{self.bot.user.id}>",
                f"<@!{self.bot.user.id}>",
            ):
                return
            if (
                message.guild
                and not message.channel.permissions_for(message.guild.me).send_messages
            ):
                return
            await message.reply("Use `/help` or `m.help` for more info! 😺")
        except Exception as e:
            logger.debug(f"on_message ping handler error: {e}")


async def setup(bot: Bot):
    await bot.add_cog(General(bot, "🌐"))
