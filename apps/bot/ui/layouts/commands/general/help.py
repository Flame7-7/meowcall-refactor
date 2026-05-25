from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import ui
from ui.layouts.uiBase import BaseActionRow, BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot


PAGE_COLORS = [
    0x5865F2,  # blue
    0x57F287,  # green
    0xFEE75C,  # orange
    0xEB459E,  # purple
]


class HelpLinkRow(BaseActionRow):
    def __init__(self, bot: Bot) -> None:
        super().__init__(bot, None)
        for button in [
            ui.Button(
                label="⭐ Vote",
                style=discord.ButtonStyle.link,
                url="https://top.gg/bot/1355389597818945639/vote",
            ),
            ui.Button(
                label="😺 Support",
                style=discord.ButtonStyle.link,
                url="https://discord.gg/BxNnGC8TAs",
            ),
            ui.Button(
                label="🌐 Website",
                style=discord.ButtonStyle.link,
                url="https://meowcall.xyz/",
            ),
        ]:
            self.add_item(button)


class HelpNavRow(BaseActionRow):
    def __init__(self, bot: Bot, on_prev, on_next, page: int, total: int) -> None:
        super().__init__(bot, None)

        prev_btn = ui.Button(
            label="◀ Previous",
            style=discord.ButtonStyle.secondary,
            disabled=page == 0,
        )
        prev_btn.callback = on_prev

        page_btn = ui.Button(
            label=f"Page {page + 1}/{total}",
            style=discord.ButtonStyle.primary,
            disabled=True,
        )
        page_btn.callback = self._noop

        next_btn = ui.Button(
            label="Next ▶",
            style=discord.ButtonStyle.secondary,
            disabled=page >= total - 1,
        )
        next_btn.callback = on_next

        self.add_item(prev_btn)
        self.add_item(page_btn)
        self.add_item(next_btn)

    async def _noop(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()


class HelpLayout(BaseLayoutView):
    def __init__(
        self,
        bot: Bot,
        user: discord.User | discord.Member,
        commands_by_category: dict[str, list[str]],
    ) -> None:
        super().__init__(user, timeout=120)
        self.bot = bot
        self.current_page = 0
        self._pages = list(commands_by_category.items())
        self._render()

    def _render(self) -> None:
        self.clear_items()
        total = len(self._pages)
        category, lines = self._pages[self.current_page]
        color = PAGE_COLORS[self.current_page % len(PAGE_COLORS)]

        is_last = self.current_page == total - 1
        footer = (
            "Thank you for using MeowCall! 🐾"
            if is_last
            else "Use buttons below to navigate! 🐱"
        )

        container = ui.Container(
            ui.TextDisplay(
                f"### 📚 MeowCall Help — Page {self.current_page + 1}/{total}"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(f"**{category}**"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay("\n".join(lines) or "No commands."),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            HelpNavRow(self.bot, self._previous, self._next, self.current_page, total),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            HelpLinkRow(self.bot),
            ui.TextDisplay(f"-# {footer}"),
            accent_color=color,
        )
        self.add_item(container)

    async def _previous(self, interaction: discord.Interaction) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self._render()
            await interaction.response.edit_message(view=self)

    async def _next(self, interaction: discord.Interaction) -> None:
        if self.current_page < len(self._pages) - 1:
            self.current_page += 1
            self._render()
            await interaction.response.edit_message(view=self)

    async def send(self, ctx) -> None:
        if not self._pages:
            await ctx.send("No commands found. 😺", ephemeral=True)
            return
        message = await ctx.send(view=self)
        self.bind_message(message)
