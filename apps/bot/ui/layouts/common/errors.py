"""
ui/layouts/common/errors.py

V1-style error card.

Moderation-specific errors use ModerationRenderer.error() instead.
This file keeps full backwards-compatibility with all existing call-sites.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord
from discord import ui
from discord.ext import commands

from ui.layouts.uiBase import BaseActionRow, BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot

    SourceType = discord.Interaction["Bot"] | commands.Context["Bot"]


class ErrorActionRow(BaseActionRow):
    def __init__(self, bot: "Bot"):
        super().__init__(bot, None)

        self.add_item(ui.Button(
            emoji="❓",
            label="Need Support?",
            style=discord.ButtonStyle.url,
            url="https://discord.gg/7vxJbzKY5E",
        ))
        self.add_item(ui.Button(
            emoji="🌐",
            label="Our website",
            style=discord.ButtonStyle.url,
            url="https://meowcall.xyz/",
        ))


class ErrorLayout(BaseLayoutView):
    """
    V1-style error card.

    Changes vs old V2:
      - Title is prefixed with '### ❌ ' if not already markdown
      - Always shows a footer timestamp
      - Support + Website buttons appear below a separator (not above footer)
    """

    def __init__(
        self,
        bot: "Bot",
        title: str | None,
        message: str,
        error_id: str | None = None,
        dev: bool = False,
        source: "SourceType | None" = None,
        error: Exception | None = None,
        user: discord.User | discord.Member | None = None,
    ):
        super().__init__(user, timeout=None)

        raw_title = title or "Error!"
        # Preserve existing '### ...' headings; add prefix otherwise
        if raw_title.lstrip().startswith("#"):
            display_title = raw_title
        else:
            display_title = f"### ❌ {raw_title}"

        now = int(time.time())
        footer = ui.TextDisplay(f"-# Meowcall • <t:{now}:f>")

        container_items: list = [
            ui.TextDisplay(f"{display_title}\n{message}"),
        ]

        if error_id:
            container_items.append(ui.TextDisplay(f"-# Error ID: `{error_id}`"))

        container_items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))

        if not dev:
            container_items.append(ErrorActionRow(bot))
        else:
            command   = getattr(source, "command", None)
            guild     = getattr(source, "guild",   None)
            inv       = command.qualified_name if command else "unknown"
            guild_info = f"{guild.name} (`{guild.id}`)" if guild else "DM"

            if isinstance(source, discord.Interaction) or (
                isinstance(source, commands.Context)
                and source.interaction is not None
            ):
                cmd_type = getattr(command, "type", None)
                if cmd_type == discord.AppCommandType.user:
                    src_type = "User Context Menu"
                elif cmd_type == discord.AppCommandType.message:
                    src_type = "Message Context Menu"
                else:
                    src_type = "Slash Command"
            else:
                src_type = "Prefix Command"

            err_extra = ""
            if isinstance(error, discord.HTTPException):
                err_extra = (
                    f"\n> **Endpoint:** {error.response.method} {error.response.url}"
                    f"\n> **HTTP Status:** {error.status} | **Discord Code:** {error.code}"
                    f"\n> **Message:** {error.text}"
                )

            container_items.append(ui.TextDisplay(
                f"**Dev Info** | {src_type}\n"
                f"**Cmd:** `{inv}`\n"
                f"**In:** {guild_info}\n"
                f"**By:** {user.mention} (`{user.id}`)"
                f"{err_extra}"
            ))

        container_items.append(footer)

        self.add_item(ui.Container(
            *container_items,
            accent_color=discord.Color.red(),
        ))