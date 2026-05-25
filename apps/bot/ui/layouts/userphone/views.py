from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from core.bot import Bot


class UserphoneReactionLayout(discord.ui.LayoutView):
    def __init__(
        self,
        bot: Bot,
        title: str | None = None,
        message: str | None = None,
    ):
        super().__init__(timeout=None)

        if title or message:
            display = "\n".join(filter(None, [title, message]))
            self.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(display),
                    accent_colour=discord.Color.blurple(),
                )
            )
