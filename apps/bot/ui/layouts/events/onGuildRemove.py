from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import ui
from ui.layouts.uiBase import BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot


class onGuildRemoveLayout(BaseLayoutView):
    def __init__(self, bot: Bot, guild: discord.Guild):
        super().__init__(None, 60)

        owner_info = f"{guild.owner} (`{guild.owner.id}`)" if guild.owner else "Unknown"

        container = ui.Container(
            ui.TextDisplay("## Kicked!"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                f"{guild.name} (`{guild.id}`) has kicked meowcall from their guild."
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay("### Statistics"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                f"> **Guild Owner:** {owner_info}\n > **Guild Members:** {guild.member_count}\n > **Total Guilds:** {len(bot.guilds)}"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            accent_color=discord.Color.red(),
        )
        self.add_item(container)
