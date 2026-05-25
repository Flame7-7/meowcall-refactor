from typing import TYPE_CHECKING

import discord
from discord import ui
from discord.ext import commands
from ui.layouts.uiBase import BaseLayoutView
from utils.discord.validators import fetch_staff_position

if TYPE_CHECKING:
    from core.bot import Bot


class OfficialLayout(BaseLayoutView):
    def __init__(
        self,
        ctx: commands.Context[Bot],
        user: discord.User | discord.Member,
        target: discord.User | discord.Member,
    ) -> None:
        super().__init__(user, 60)
        self.ctx = ctx
        self.target = target

        self.add_item(
            ui.Container(
                ui.TextDisplay("Loading profile..."),
            )
        )

    async def build_container(self) -> None:
        position = await fetch_staff_position(self.ctx, self.target.id)
        is_staff = position is not None

        if is_staff:
            subtitle = "This user is an **official member** of the **Meowcall Team**."
            info_text = f"> **User:** {self.target.mention} (`{self.target.id}`)\n> **Position:** {position}"
            footer = "-# Official Meowcall Team"
        else:
            subtitle = "This user is **not** a member of the **Meowcall Team**."
            info_text = f"> **User:** {self.target.mention} (`{self.target.id}`)\n> **Position:** N/A"
            footer = "-# Meowcall"

        self.clear_items()
        self.add_item(
            ui.Container(
                ui.TextDisplay(f"### {self.target.mention} (`{self.target.id}`)"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(subtitle),
                ui.Section(
                    ui.TextDisplay("**User Information**"),
                    ui.TextDisplay(info_text),
                    accessory=ui.Thumbnail(media=self.target.display_avatar.url),
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(footer),
                accent_color=16765404 if is_staff else discord.Color.red(),
            )
        )

        if isinstance(self.ctx, discord.Interaction):
            await self.ctx.edit_original_response(view=self)
            self.bind_message(await self.ctx.original_response())
        else:
            message = await self.ctx.send(view=self)
            self.bind_message(message)
