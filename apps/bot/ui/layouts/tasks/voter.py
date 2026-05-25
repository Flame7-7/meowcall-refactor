from typing import TYPE_CHECKING

import discord
from discord import ui
from ui.layouts.uiBase import BaseActionRow, BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot


class VoterLayoutButtons(BaseActionRow):
    def __init__(self, bot: Bot, user: discord.User | discord.Member):
        super().__init__(bot, user)

        buttons = [
            ui.Button(
                emoji="❓",
                label="Need Support?",
                style=discord.ButtonStyle.url,
                url="https://discord.gg/7vxJbzKY5E",
            ),
            ui.Button(
                emoji="🌐",
                label="Our website",
                style=discord.ButtonStyle.url,
                url="https://meowcall.xyz/",
            ),
        ]
        for button in buttons:
            self.add_item(button)


class VoterLayout(BaseLayoutView):
    def __init__(
        self,
        bot: Bot,
        user: discord.User | discord.Member,
    ):
        super().__init__(user, 120)

        self.add_item(
            ui.Container(
                ui.TextDisplay("### Thanks for voting!"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    "**Thank you** for voting for Meowcall - we appriciate it! As a thank you, for 8 hours you now have the following perks."
                ),
                ui.TextDisplay(
                    "**Userphone**\n> ✨ Media passthrough!\n\n**Our support server**\n> 📷 Gif Permissions\n\nMore to come in the future! Keep voting, our top voter gets a reward."
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("These perks are now active - happy calling!"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                VoterLayoutButtons(bot, user),
                accent_color=16765404,
            )
        )
