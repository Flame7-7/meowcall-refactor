"""
ui/layouts/commands/moderation/modlogs.py

Moderation log viewer — V1 visual identity, V2 feature set.

V1 style restored:
  - Header:  "📖 Modlogs — TargetName" with ID subtext
  - Each infraction card:
      [emoji] **TYPE** (`id`)  [REVOKED / ACTIVE badge]
      **Moderator:** @mod  •  <timestamp>
      **Reason:** …
      **Expires:** …  /  **Revoked by:** @mod
  - Summary line: "X infraction(s) found  (Y total)"
  - Footer: "Meowcall Moderation • <t:…:f>"
  - Accent: yellow/gold (0xFAA61A — V1 sidebar colour)
  - Pagination buttons keep ◀ page/total ▶ style
  - Filter select kept from V2 (new feature, styled to V1 language)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord
from discord import ui
from discord.ext import commands
from models import InfractionStatus, InfractionType
from services.moderation import ModerationService
from ui.layouts.uiBase import BaseActionRow, BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot
    from models import Infraction
    from sqlalchemy.ext.asyncio import AsyncSession


# V1 accent: golden yellow (matches old embed side-bar colour)
_ACCENT = discord.Color(0xFAA61A)

_TYPE_EMOJI: dict[InfractionType, str] = {
    InfractionType.BAN:     "🔨",
    InfractionType.WARNING: "⚠️",
}
_STATUS_BADGE: dict[InfractionStatus, str] = {
    InfractionStatus.ACTIVE:   "🟢 Active",
    InfractionStatus.REVOKED:  "🔴 Revoked",
    InfractionStatus.APPEALED: "🟠 Appealed",
}


def _infraction_block(infraction: "Infraction") -> str:
    """
    Build the text block for a single infraction entry.

    Format (V1):
        [emoji] **TYPE** (`id`)  •  🟢 Active
        **Moderator:** <@mod_id>  •  <t:ts:R>
        **Reason:** …
        **Expires:** …          ← bans only
        **Revoked by:** <@id>   ← revoked only
    """
    reason = infraction.reason or "No reason provided"
    revoked_by_id: str | None = None

    # Parse "reason | Revoked by MOD_ID: revoke_reason" encoding
    if "| Revoked by " in reason:
        main_reason, revoke_part = reason.split("| Revoked by ", 1)
        reason = main_reason.strip() or "No reason provided"
        if ": " in revoke_part:
            revoked_id, revoke_reason = revoke_part.split(": ", 1)
            revoked_by_id = revoked_id.strip()
            reason = f"{reason} *(Revoke reason: {revoke_reason.strip()})*"
        else:
            revoked_by_id = revoke_part.strip()

    type_emoji = _TYPE_EMOJI.get(infraction.type, "📋")
    status_badge = _STATUS_BADGE.get(infraction.status, "")

    lines = [
        f"{type_emoji} **{infraction.type.value.title()}** (`{infraction.id}`)  •  {status_badge}",
        f"**Moderator:** <@{infraction.moderatorId}>  •  <t:{int(infraction.createdAt.timestamp())}:R>",
        f"**Reason:** {reason}",
    ]

    if infraction.status == InfractionStatus.ACTIVE and infraction.type == InfractionType.BAN:
        expiry = (
            "Permanent"
            if infraction.expiresAt is None
            else f"<t:{int(infraction.expiresAt.timestamp())}:R>"
        )
        lines.append(f"**Expires:** {expiry}")

    if infraction.status == InfractionStatus.REVOKED and revoked_by_id:
        lines.append(f"**Revoked by:** <@{revoked_by_id}>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Action rows
# ---------------------------------------------------------------------------

class ModerationLogFilter(BaseActionRow):
    def __init__(
        self,
        bot: "Bot",
        user: discord.User | discord.Member,
        active_filters: set[str],
        callback,
    ):
        super().__init__(bot, user)

        select = ui.Select(
            placeholder="🔍  Filter infractions…",
            options=[
                discord.SelectOption(
                    label="Active",
                    description="Show active infractions",
                    emoji="🟢",
                    value="filter_active",
                    default="filter_active" in active_filters,
                ),
                discord.SelectOption(
                    label="Expired / Revoked",
                    description="Show expired or appealed infractions",
                    emoji="🔴",
                    value="filter_expired",
                    default="filter_expired" in active_filters,
                ),
                discord.SelectOption(
                    label="Bans",
                    description="Show bans only",
                    emoji="🔨",
                    value="filter_bans",
                    default="filter_bans" in active_filters,
                ),
                discord.SelectOption(
                    label="Warnings",
                    description="Show warnings only",
                    emoji="⚠️",
                    value="filter_warnings",
                    default="filter_warnings" in active_filters,
                ),
            ],
            max_values=4,
            min_values=1,
        )
        select.callback = callback
        self.add_item(select)


class ModerationLogsActionRow(BaseActionRow):
    def __init__(
        self,
        bot: "Bot",
        user: discord.User | discord.Member,
        current_page: int,
        total_pages: int,
        prev_callback,
        next_callback,
    ):
        super().__init__(bot, user)

        self.prev_button = ui.Button(
            emoji="◀️",
            style=discord.ButtonStyle.grey,
            disabled=current_page == 0,
        )
        self.page_button = ui.Button(
            label=f"Page {current_page + 1} of {max(total_pages, 1)}",
            style=discord.ButtonStyle.grey,
            disabled=True,
        )
        self.next_button = ui.Button(
            emoji="▶️",
            style=discord.ButtonStyle.grey,
            disabled=current_page >= total_pages - 1,
        )

        self.prev_button.callback = prev_callback
        self.next_button.callback = next_callback

        for button in (self.prev_button, self.page_button, self.next_button):
            self.add_item(button)


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

class ModerationLogsLayout(BaseLayoutView):
    def __init__(
        self,
        user: discord.User | discord.Member,
        target: discord.User | discord.Member | discord.Guild,
    ):
        super().__init__(user, 300)

        self.target = target
        self.current_page: int = 0
        self.total_pages: int = 1
        self.active_filters: set[str] = {
            "filter_active",
            "filter_expired",
            "filter_bans",
            "filter_warnings",
        }
        self.filter_type: dict[str, set[InfractionType]] = {
            "filter_bans":     {InfractionType.BAN},
            "filter_warnings": {InfractionType.WARNING},
        }
        self.filter_status: dict[str, set[InfractionStatus]] = {
            "filter_active":  {InfractionStatus.ACTIVE},
            "filter_expired": {InfractionStatus.REVOKED, InfractionStatus.APPEALED},
        }
        self._source: discord.Interaction | commands.Context | None = None
        self._bot: "Bot | None" = None

        # Header items stored for reuse across rebuilds
        self._target_label = target.name
        self._target_id    = target.id
        self._is_guild     = isinstance(target, discord.Guild)

    @staticmethod
    def _service(session: "AsyncSession") -> ModerationService:
        return ModerationService(session)

    async def _fetch_infractions(
        self,
        bot: "Bot",
        target: discord.User | discord.Member | discord.Guild,
    ) -> list["Infraction"]:
        specific_server_id = str(target.id) if isinstance(target, discord.Guild) else None
        specific_user_id   = None if isinstance(target, discord.Guild) else str(target.id)

        async with bot.db.uow() as session:
            svc = self._service(session)
            infractions, _ = await svc.list_infractions(
                page=0,
                per_page=1000,
                specific_user_id=specific_user_id,
                specific_server_id=specific_server_id,
            )
        return infractions

    def _apply_filters(self, infractions: list["Infraction"]) -> list["Infraction"]:
        allowed_statuses: set[InfractionStatus] = set()
        allowed_types: set[InfractionType] = set()

        for f in self.active_filters:
            if f in self.filter_status:
                allowed_statuses |= self.filter_status[f]
            if f in self.filter_type:
                allowed_types |= self.filter_type[f]

        return [
            inf for inf in infractions
            if inf.status in allowed_statuses
            and (not allowed_types or inf.type in allowed_types)
        ]

    async def build_container(
        self,
        bot: "Bot",
        source: discord.Interaction | commands.Context,
        target: discord.User | discord.Member | discord.Guild,
        page: int = 0,
    ) -> None:
        self._bot    = bot
        self._source = source

        all_infractions = await self._fetch_infractions(bot, target)
        unfiltered_count = len(all_infractions)
        filtered = self._apply_filters(all_infractions)

        total_count      = len(filtered)
        self.total_pages = max(1, -(-total_count // 5))
        self.current_page = min(page, self.total_pages - 1)

        page_infractions = filtered[
            self.current_page * 5 : (self.current_page + 1) * 5
        ]

        invoker = (
            source.author if isinstance(source, commands.Context) else source.user
        )

        # ── header ────────────────────────────────────────────────────────────
        target_label = (
            target.name if isinstance(target, discord.Guild) else f"@{target.name}"
        )
        header = [
            ui.TextDisplay(f"### 📖 Modlogs — {target_label}"),
            ui.TextDisplay(
                f"-# {'Server' if self._is_guild else 'User'} ID: `{self._target_id}`"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
        ]

        # ── summary ───────────────────────────────────────────────────────────
        if unfiltered_count != total_count:
            summary_text = (
                f"Showing **{total_count}** infraction(s) "
                f"*(filtered from {unfiltered_count} total)*"
            )
        else:
            summary_text = f"**{total_count}** infraction(s) on record"

        summary = [ui.TextDisplay(summary_text)]

        # ── infraction entries ────────────────────────────────────────────────
        entries: list = []
        if not filtered:
            entries.extend([
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("*No infractions match the current filters.*"),
            ])
        else:
            for infraction in page_infractions:
                entries.extend([
                    ui.Separator(spacing=discord.SeparatorSpacing.small),
                    ui.TextDisplay(_infraction_block(infraction)),
                ])

        # ── footer + controls ─────────────────────────────────────────────────
        now = int(time.time())
        footer_row = [
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(f"-# Meowcall Moderation • <t:{now}:f>"),
            ModerationLogFilter(
                bot, invoker, self.active_filters, self._filter_callback
            ),
            ModerationLogsActionRow(
                bot, invoker,
                current_page=self.current_page,
                total_pages=self.total_pages,
                prev_callback=self._prev_callback,
                next_callback=self._next_callback,
            ),
        ]

        all_items = [*header, *summary, *entries, *footer_row]

        self.clear_items()
        self.add_item(ui.Container(*all_items, accent_color=_ACCENT))

        if isinstance(source, discord.Interaction):
            await source.edit_original_response(view=self)
            self.bind_message(await source.original_response())
        else:
            message = await source.send(view=self)
            self.bind_message(message)

    # ── callbacks ─────────────────────────────────────────────────────────────

    async def _filter_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        self.active_filters = set(interaction.data["values"])  # pyright: ignore
        await self.build_container(self._bot, interaction, self.target, page=0)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.current_page > 0:
            await self.build_container(
                self._bot, interaction, self.target,
                page=self.current_page - 1,
            )

    async def _next_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.current_page < self.total_pages - 1:
            await self.build_container(
                self._bot, interaction, self.target,
                page=self.current_page + 1,
            )