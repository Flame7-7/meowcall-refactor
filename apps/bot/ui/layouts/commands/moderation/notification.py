from __future__ import annotations

import datetime
import time
from typing import TYPE_CHECKING

import discord
from discord import ui

from ui.layouts.uiBase import BaseLayoutView

if TYPE_CHECKING:
    from models.moderation import Infraction


class NotificationLayout(BaseLayoutView):
    def __init__(self, infraction: "Infraction"):
        super().__init__(user=None, timeout=None)

        from models import InfractionType  # local import keeps module importable standalone

        is_ban = infraction.type == InfractionType.BAN

        # ── strings ──────────────────────────────────────────────────────────
        emoji     = "⛔" if is_ban else "⚠️"
        action    = "been banned from using" if is_ban else "received a warning in"
        title_txt = "Banned" if is_ban else "Warned"

        expires_text: str
        if is_ban:
            raw_expires = getattr(infraction, "expiresAt", None)
            if raw_expires is not None:
                try:
                    # Force UTC so .timestamp() is correct on any host timezone.
                    if raw_expires.tzinfo is None:
                        raw_expires = raw_expires.replace(tzinfo=datetime.timezone.utc)
                    expires_text = f"<t:{int(raw_expires.timestamp())}:R>"
                except Exception:
                    expires_text = str(raw_expires)
            else:
                expires_text = "Never"  # permanent ban

        type_value  = getattr(infraction.type, "value", str(infraction.type))
        reason_text = getattr(infraction, "reason", None) or "No reason provided"

        # ── accent colour ─────────────────────────────────────────────────────
        accent = discord.Color.red() if is_ban else discord.Color.orange()

        # ── body block ────────────────────────────────────────────────────────
        body_lines = [
            f"You have {action} Meowcall.",
            f"**Type:** {type_value.title()} (`{infraction.id}`)",
            f"**Reason:** {reason_text}",
        ]
        if is_ban:
            body_lines.append(f"**Expires:** {expires_text}")

        # ── link footer ───────────────────────────────────────────────────────
        links = (
            "-# [Terms](https://meowcall.xyz/terms)"
            " • [Appeal](https://meowcall.xyz/appeal)"
            " • [Support](https://discord.gg/7vxJbzKY5E)"
        )

        # ── buttons ──────────────────────────────────────────────────────────
        btn_support = ui.Button(
            emoji="❓",
            label="Need support?",
            style=discord.ButtonStyle.url,
            url="https://discord.gg/7vxJbzKY5E",
        )
        btn_appeal = ui.Button(
            emoji="📝",
            label="Appeal",
            style=discord.ButtonStyle.url,
            url="https://meowcall.xyz/appeal",
        )
        btn_website = ui.Button(
            emoji="🌐",
            label="Our website",
            style=discord.ButtonStyle.url,
            url="https://meowcall.xyz/",
        )
        button_row = ui.ActionRow()
        button_row.add_item(btn_support)
        button_row.add_item(btn_appeal)
        button_row.add_item(btn_website)

        now = int(time.time())

        self.add_item(ui.Container(
            ui.TextDisplay(f"### {emoji} {title_txt}"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay("\n".join(body_lines)),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(links),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(f"-# Meowcall Moderation • <t:{now}:f>"),
            accent_color=accent,
        ))
        self.add_item(button_row)