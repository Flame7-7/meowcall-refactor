from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import ui
from ui.layouts.uiBase import BaseActionRow, BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot


class WelcomeButtons(BaseActionRow):
    def __init__(self, bot: Bot):
        super().__init__(bot, None)

        start_button = ui.Button(
            label="Start a Call",
            emoji="📞",
            style=discord.ButtonStyle.primary,
            disabled=True,
        )
        start_button.callback = self.start_call_callback
        self.add_item(start_button)

        self.add_item(
            ui.Button(
                label="Vote on Top.gg",
                emoji="⭐",
                style=discord.ButtonStyle.link,
                url="https://top.gg/bot/1355389597818945639/vote",
            )
        )

        self.add_item(
            ui.Button(
                label="Support Server",
                emoji="😺",
                style=discord.ButtonStyle.link,
                url="https://discord.gg/7vxJbzKY5E",
            )
        )

        self.add_item(
            ui.Button(
                label="Website",
                emoji="🌐",
                style=discord.ButtonStyle.link,
                url="https://meowcall.xyz",
            )
        )

    async def start_call_callback(self, interaction: discord.Interaction[Bot]):
        """Callback to start a call from the welcome message."""
        # defer if not done
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)

        ctx = await self.bot.get_context(interaction)
        userphone_cog = self.bot.get_cog("Userphone")

        if userphone_cog:
            # We need to make sure the command can run
            await userphone_cog.call(ctx)
        else:
            await interaction.followup.send(
                "⚠️ Userphone service is currently unavailable. Please try using `/call` later.",
                ephemeral=True,
            )


class WelcomeLayout(BaseLayoutView):
    def __init__(
        self, bot: Bot, guild: discord.Guild, user: discord.User | discord.Member
    ):
        super().__init__(user, 120)
        self.bot = bot

        member_count = guild.member_count or 0
        server_count = len(bot.guilds)

        self.add_item(
            ui.Container(
                ui.TextDisplay("🐾 **Meow! MeowCall has arrived!**"),
                ui.TextDisplay(
                    f"Thanks for adding me to **{guild.name}** ({member_count} members)! 🎉"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    "**MeowCall** lets you connect your server with a random server anywhere on Discord for real-time cross-server chat — just like a phone call, but for communities! 📞"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("⚡ **Get started in 3 steps:**"),
                ui.TextDisplay("1️⃣ Run `/call` (or `m.call`) in any channel"),
                ui.TextDisplay("2️⃣ Wait a moment to be matched with another server"),
                ui.TextDisplay("3️⃣ Chat freely — use `/hang` to end the call anytime"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    "**📞 Call Commands**\n"
                    "`/call` · `m.c` — Start a random call\n"
                    "`/skip` · `m.s` — Skip to a new server\n"
                    "`/hang` · `m.h` — End the call\n"
                    "`/report` — Report bad behaviour"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    "**🎉 Fun Commands**\n"
                    "`/ship` — Ship two users\n"
                    "`/8ball` — Ask the magic ball\n"
                    "`/coinflip` — Flip a coin!\n"
                    "Anime Recommendations · Smash or pass + more!"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("📖 **Need help?**"),
                ui.TextDisplay(
                    "Use `/help` or `m.help` for the **full interactive command guide** with page navigation, or join our Support server below! 😼"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                WelcomeButtons(bot),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    f"-# MeowCall • Connecting the Meowverse 🐾 | Now in {server_count} servers"
                ),
                accent_color=0xFF4BB4,  # Pinkish color from legacy
            )
        )
