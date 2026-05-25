from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import ui
from ui.layouts.commands.general.sharedButtons import SharedButtonsActionRow
from ui.layouts.uiBase import BaseActionRow, BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot


class LinksLayoutActionRow(BaseActionRow):
    def __init__(self, bot: Bot):
        super().__init__(bot, None)

        buttons = [
            ui.Button(
                emoji="➕",
                label="Add Meowcall",
                style=discord.ButtonStyle.blurple,
                url="https://discord.com/oauth2/authorize?client_id=1487786643384438804",
            ),
            ui.Button(
                emoji="📈",
                label="Vote for us!",
                style=discord.ButtonStyle.blurple,
                url="https://top.gg/bot/1355389597818945639/vote",
            ),
            ui.Button(
                emoji="🌐",
                label="Our website",
                style=discord.ButtonStyle.link,
                url="https://meowcall.xyz/",
            ),
            ui.Button(
                emoji="🏘️",
                label="Our server",
                style=discord.ButtonStyle.link,
                url="https://discord.gg/7vxJbzKY5E",
            ),
        ]

        for button in buttons:
            self.add_item(button)


class LinksLayout(BaseLayoutView):
    def __init__(self, bot: Bot):
        super().__init__(None, 300)

        self.add_item(
            ui.Container(
                ui.TextDisplay("### Useful Links!"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    "Looking for our official sites, and support services? See the links below. Can't find what you're looking for? Join our support server - we are always more then happy to help."
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                SharedButtonsActionRow(bot, selected=type(self)),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                LinksLayoutActionRow(bot),
                accent_color=16765404,
            )
        )
