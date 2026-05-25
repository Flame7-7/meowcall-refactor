from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import ui
from ui.layouts.commands.general.sharedButtons import SharedButtonsActionRow
from ui.layouts.uiBase import BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot


class AboutLayout(BaseLayoutView):
    def __init__(self, bot: Bot):
        super().__init__(None, 300)

        self.add_item(
            ui.Container(
                ui.TextDisplay("### About us"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                SharedButtonsActionRow(bot, selected=type(self)),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    "Tired of being stuck in your own server? Meowcall is the only reliable solution. We connect you to a random person, in a random server instantly. Join our pool of thousands of users and start making new memories.\nWe believe the best conversations, and friendships happen on accident. Give it a go, see what it brings you. Happy calling!"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("**Commands**"),
                ui.TextDisplay("Looking for our commands? Try /help!"),
                accent_color=16765404,
            )
        )
