"""
ui/layouts/commands/moderation/history.py

Call history viewer — V1 visual identity, V2 feature set.

V1 style restored:
  - Header:  "📞 Call History — TargetName" with ID subtext
  - Each call card:
      📞  **Call ID** (`id`)  •  🟢 Status
      **Server:** ServerName  •  **User:** @mention
      **Started:** <t:ts:R>   •  **Ended:** <t:ts:R> / Ongoing
      **Paired call:** `id` / None
  - Footer: "Meowcall Moderation • <t:…:f>"
  - Accent: blue (call theme)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord
from discord import ui
from discord.ext import commands

from ui.layouts.uiBase import BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot
    from models import UserphoneCall


_ACCENT = discord.Color(0x5865F2)   # Discord blurple — V1 call colour

_STATUS_BADGE: dict = {}  # populated lazily below


def _status_badge(status) -> str:
    value = getattr(status, "value", str(status)).lower()
    badges = {
        "active":    "🟢 Active",
        "ongoing":   "🟢 Ongoing",
        "ended":     "⚪ Ended",
        "completed": "⚪ Completed",
        "missed":    "🔴 Missed",
    }
    return badges.get(value, f"• {value.title()}")


class HistoryLayout(BaseLayoutView):
    def __init__(
        self,
        bot: "Bot",
        ctx: commands.Context["Bot"],
        user: discord.User | discord.Member,
        calls: list["UserphoneCall"],
    ):
        super().__init__(user, 60)
        self.bot   = bot
        self.calls = calls
        self.ctx   = ctx

        # Placeholder while building
        self.add_item(ui.Container(
            ui.TextDisplay("### 📞 Call History\n-# Loading…"),
            accent_color=_ACCENT,
        ))

    async def build_container(self) -> "HistoryLayout":
        entries: list = []

        for call in self.calls[:5]:
            guild = await self.bot.fetch_guild(call.guildId)
            user  = await self.bot.fetch_user(call.userId)

            paired  = f"`{call.pairedCallId}`" if call.pairedCallId else "None"
            started = f"<t:{int(call.createdAt.timestamp())}:R>"
            ended   = (
                f"<t:{int(call.endedAt.timestamp())}:R>"
                if call.endedAt is not None
                else "Ongoing"
            )

            badge = _status_badge(call.status)

            lines = [
                f"📞 **Call** (`{call.id}`)  •  {badge}",
                f"**Server:** {guild.name}  •  **User:** {user.mention}",
                f"**Started:** {started}  •  **Ended:** {ended}",
                f"**Paired call:** {paired}",
            ]

            entries.extend([
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("\n".join(lines)),
            ])

        now = int(time.time())

        all_items = [
            ui.TextDisplay("### 📞 Call History"),
            ui.TextDisplay(
                f"-# Showing {min(len(self.calls), 5)} of {len(self.calls)} call(s)"
            ),
            *entries,
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(f"-# Meowcall Moderation • <t:{now}:f>"),
        ]

        self.clear_items()
        self.add_item(ui.Container(*all_items, accent_color=_ACCENT))
        return self