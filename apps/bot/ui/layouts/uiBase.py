from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import discord
from discord import ui

if TYPE_CHECKING:
    from core.bot import Bot


class BaseLayoutView(ui.LayoutView):
    def __init__(
        self,
        user: discord.User | discord.Member | None = None,
        timeout: int | None = 300,  # Seconds // 5 Minutes
    ):
        super().__init__(timeout=timeout)
        self.user = user
        self._message: discord.Message | None = None
        self.timeout = timeout

    @property
    def message(self) -> discord.Message | None:
        return self._message

    def bind_message(self, message: discord.Message) -> None:
        self._message = message

    async def on_timeout(self):
        def disable_items(item: ui.Item) -> None:
            if isinstance(item, (ui.Button, ui.Select)):
                item.disabled = True
                return
            children = getattr(item, "children", None)
            if not children:
                return
            for child in children:
                disable_items(child)

        for item in self.children:
            disable_items(item)
        if self.message is not None:
            await self.message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        from core.bot import Bot
        from utils.discord.validators import interaction_check

        if self.user is None:
            return True
        return await interaction_check(
            cast(discord.Interaction[Bot], interaction), interaction.user, self.user
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: ui.Item
    ) -> None:
        from core.errors.errorHandler import error_handler

        await error_handler(interaction, error)


class BaseActionRow(ui.ActionRow):
    def __init__(self, bot: Bot, user: discord.User | discord.Member | None = None):
        super().__init__()
        self.bot = bot
        self.user = user
        self.constants = bot.constants

    async def interaction_check(self, interaction) -> bool:
        if self.user is not None:
            from utils.discord.validators import interaction_check

            return await interaction_check(interaction, interaction.user, self.user)
        return True

    def add_back_button(self, parent_view: ui.LayoutView) -> None:
        back_button = ui.Button(
            label="Back",
            style=discord.ButtonStyle.grey,
        )
        back_button.callback = self._create_back_callback(parent_view)
        self.add_item(back_button)

    def add_support_button(self, _parent_view: ui.LayoutView | None = None):
        support_button = ui.Button(
            style=discord.ButtonStyle.grey,
            label="Support",
            url=self.constants.SUPPORT_INVITE,
        )
        self.add_item(support_button)
        return self

    @staticmethod
    def _create_back_callback(parent_view) -> Callable:
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=parent_view._view)

        return callback
