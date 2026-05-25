from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import ui
from utils import logger

if TYPE_CHECKING:
    pass


class SmashOrPassView(ui.View):
    """Interactive view for smash or pass voting on anime characters."""

    def __init__(self, character: dict, timeout: int = 60) -> None:
        super().__init__(timeout=timeout)
        self.character = character
        self.smash_voters: list[discord.User | discord.Member] = []
        self.pass_voters: list[discord.User | discord.Member] = []

        smash_button = ui.Button(label="Smash 💖", style=discord.ButtonStyle.green)
        smash_button.callback = self.smash_button

        pass_button = ui.Button(label="Pass 🙅", style=discord.ButtonStyle.red)
        pass_button.callback = self.pass_button

        self.add_item(smash_button)
        self.add_item(pass_button)

    async def on_timeout(self) -> None:
        """Handle view timeout by updating the embed and disabling buttons."""
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                embed = self.message.embeds[0]
                embed.color = discord.Color.purple()
                embed.set_footer(text="Voting has ended!")
                embed.clear_fields()
                embed.add_field(
                    name="Smash 💖",
                    value="\n".join(f"<@{user.id}>" for user in self.smash_voters)
                    or "No votes",
                    inline=True,
                )
                embed.add_field(
                    name="Pass 🙅",
                    value="\n".join(f"<@{user.id}>" for user in self.pass_voters)
                    or "No votes",
                    inline=True,
                )
                await self.message.edit(embed=embed, view=self)
            except Exception as e:
                logger.error(f"Error updating message on timeout: {e}")

    @property
    def message(self) -> discord.Message | None:
        return getattr(self, "_message", None)

    def bind_message(self, message: discord.Message) -> None:
        self._message = message

    async def update_embed(self, interaction: discord.Interaction) -> None:
        """Update the embed with current vote counts."""
        embed = interaction.message.embeds[0]
        embed.clear_fields()
        embed.add_field(
            name="Smash 💖",
            value="\n".join(f"<@{user.id}>" for user in self.smash_voters)
            or "No votes",
            inline=True,
        )
        embed.add_field(
            name="Pass 🙅",
            value="\n".join(f"<@{user.id}>" for user in self.pass_voters) or "No votes",
            inline=True,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def smash_button(self, interaction: discord.Interaction) -> None:
        """Handle smash button click."""
        user = interaction.user
        if user in self.pass_voters:
            self.pass_voters.remove(user)
        if user not in self.smash_voters:
            self.smash_voters.append(user)
        await self.update_embed(interaction)

    async def pass_button(self, interaction: discord.Interaction) -> None:
        """Handle pass button click."""
        user = interaction.user
        if user in self.smash_voters:
            self.smash_voters.remove(user)
        if user not in self.pass_voters:
            self.pass_voters.append(user)
        await self.update_embed(interaction)
