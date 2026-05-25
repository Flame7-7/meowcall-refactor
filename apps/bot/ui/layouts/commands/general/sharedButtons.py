from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import discord
from discord import ui
from ui.layouts.uiBase import BaseActionRow

if TYPE_CHECKING:
    from core.bot import Bot


class SharedButtonsActionRow(BaseActionRow):
    def __init__(
        self,
        bot: Bot,
        selected: type[ui.LayoutView] | None = None,
    ):
        super().__init__(bot, None)

        from .about import AboutLayout
        from .links import LinksLayout
        from .stats import StatsLayout

        self.selected = selected
        self.button_types: list[
            tuple[type[ui.LayoutView], str, Callable[[], ui.LayoutView]]
        ] = [
            (StatsLayout, "Stats", lambda: StatsLayout(self.bot)),
            (LinksLayout, "Links", lambda: LinksLayout(self.bot)),
            (AboutLayout, "About", lambda: AboutLayout(self.bot)),
        ]

        self.build_buttons()

    def build_buttons(self) -> None:
        for layout, label, factory in self.button_types:
            is_selected = layout is self.selected

            button = ui.Button(
                label=label,
                style=discord.ButtonStyle.blurple,
                disabled=is_selected,
            )
            if not is_selected:
                button.callback = self._make_layout_callback(factory)
            self.add_item(button)

    def _make_layout_callback(self, view_factory: Callable[[], ui.LayoutView]):
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=view_factory())

        return callback
