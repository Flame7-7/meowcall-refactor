"""
ui/layouts/common/success.py

V1-style success card.

For generic non-mod successes (e.g. settings saved, link cleared).
Moderation-specific successes use ModerationRenderer instead.
"""

from __future__ import annotations

import time

import discord
from discord import ui

from ui.layouts.uiBase import BaseLayoutView


class SuccessLayout(BaseLayoutView):
    """
    Generic success card.

    Parameters
    ----------
    title:   Heading text.  May include markdown (###).
             If it doesn't start with '#', '### ✅ ' is prepended automatically.
    message: Body text shown below the title.
    """

    def __init__(
        self,
        title: str | None,
        message: str,
    ):
        super().__init__(user=None, timeout=None)

        display_title = title or "### ✅ Success!"
        if display_title and not display_title.lstrip().startswith("#"):
            display_title = f"### ✅ {display_title}"

        now = int(time.time())
        footer = ui.TextDisplay(f"-# Meowcall • <t:{now}:f>")

        self.add_item(ui.Container(
            ui.TextDisplay(f"{display_title}\n{message}"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            footer,
            accent_color=discord.Color.green(),
        ))