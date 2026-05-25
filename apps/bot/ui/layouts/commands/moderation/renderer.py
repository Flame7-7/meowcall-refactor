from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from core.bot import Bot
    from models import Infraction


# ── helpers ────────────────────────────────────────────────────────────────────

def _now() -> datetime.datetime:
    """UTC-aware timestamp used in every embed."""
    return datetime.datetime.now(datetime.UTC)


def _fmt_target(target: discord.User | discord.Member | discord.Guild | Any) -> str:
    """Return the standard V1 'Name (ID: `123`)' string for any target."""
    if isinstance(target, (discord.User, discord.Member)):
        return f"{target} (`{target.id}`)"
    if isinstance(target, discord.Guild):
        return f"{target.name} (`{target.id}`)"
    return str(target)


def _fmt_expiry(expires_at: datetime.datetime | None) -> str:
    """V1 expiry format: discord relative timestamp or 'Permanent'."""
    if expires_at is None:
        return "Permanent"
    return discord.utils.format_dt(expires_at, style="R")


def _footer(ctx: str = "MeowCall Moderation") -> str:
    return ctx


# ── base embed factory ─────────────────────────────────────────────────────────

class _EmbedFactory:
    """Thin wrapper that produces embeds pre-stamped with V1 defaults."""

    @staticmethod
    def action(
        title: str,
        colour: discord.Colour,
        *,
        description: str | None = None,
        footer: str = "MeowCall Moderation",
        timestamp: bool = True,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            colour=colour,
            description=description,
            timestamp=_now() if timestamp else None,
        )
        embed.set_footer(text=footer)
        return embed

    @staticmethod
    def error(title: str, description: str | None = None) -> discord.Embed:
        return _EmbedFactory.action(
            title,
            discord.Colour.red(),
            description=description,
            footer="MeowCall Moderation",
        )

    @staticmethod
    def success(title: str, description: str | None = None) -> discord.Embed:
        return _EmbedFactory.action(
            title,
            discord.Colour.green(),
            description=description,
            footer="MeowCall Moderation",
        )

    @staticmethod
    def warning(title: str, description: str | None = None) -> discord.Embed:
        return _EmbedFactory.action(
            title,
            discord.Colour.yellow(),
            description=description,
            footer="MeowCall Moderation",
        )

    @staticmethod
    def info(title: str, description: str | None = None) -> discord.Embed:
        return _EmbedFactory.action(
            title,
            discord.Colour.blurple(),
            description=description,
            footer="MeowCall Moderation",
        )


# ── reusable views ─────────────────────────────────────────────────────────────

class _EmbedView(discord.ui.View):
    """A View that simply holds one embed. The cog sends `view=…`."""

    def __init__(self, embed: discord.Embed):
        super().__init__(timeout=None)
        self._embed = embed

    @property
    def embed(self) -> discord.Embed:
        return self._embed

    # discord.py reads message.embeds — expose for ctx.send(view=…) callers
    # that pass view= and expect embeds to appear via view.message or manually.
    # The cog calls ctx.send(view=renderer_result) where the renderer result
    # exposes .embed so callers can also do ctx.send(embed=result.embed, view=result).
    # For compatibility we override __repr__ but leave the interface clean.


class _UndoBanView(_EmbedView):
    """
    V1 UndoBanView — ↩ Undo Ban button, only the banning mod can use it,
    times out after 30 s matching V1 exactly.
    """

    def __init__(
        self,
        embed: discord.Embed,
        *,
        target: discord.User | discord.Member | discord.Guild | Any,
        moderator: discord.User | discord.Member,
        infraction_id: str,
        bot: "Bot",
    ):
        super().__init__(embed)
        self.timeout = 30
        self._target = target
        self._moderator = moderator
        self._infraction_id = infraction_id
        self._bot = bot
        self._used = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._moderator.id:
            await interaction.response.send_message(
                "❌ Only the mod who issued this ban can undo it.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]

    @discord.ui.button(label="↩ Undo Ban", style=discord.ButtonStyle.danger, emoji="↩️")
    async def undo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._used:
            await interaction.response.defer()
            return
        self._used = True
        button.disabled = True

        try:
            from services.moderation import ModerationService
            from utils.redis.cache import CacheManager

            async with self._bot.db.uow() as uow:
                svc = ModerationService(uow.session)
                await svc.revoke_infraction(
                    infraction_id=self._infraction_id,
                    mod_id=str(interaction.user.id),
                    reason="Undo via button",
                )

            user_id = self._target.id if isinstance(self._target, (discord.User, discord.Member)) else None
            guild_id = self._target.id if isinstance(self._target, discord.Guild) else None
            await CacheManager.flush_userphone_access_cache(user_id=user_id, guild_id=guild_id)

            await interaction.response.edit_message(
                content=f"↩️ Ban on **{self._target}** reversed by {interaction.user.mention}.",
                embed=None,
                view=self,
            )
        except Exception as exc:
            await interaction.response.send_message(f"⚠️ Failed to undo ban: {exc}", ephemeral=True)
        self.stop()


class _ConfirmRevokeView(_EmbedView):
    """Generic two-button confirmation — 'Yes' / 'Cancel' — matching V1 ConfirmClearView."""

    def __init__(
        self,
        embed: discord.Embed,
        *,
        invoker_id: int,
        confirm_label: str = "Yes, confirm",
        cancel_label: str = "Cancel",
        on_confirm,  # async callable(interaction) -> None
    ):
        super().__init__(embed)
        self.timeout = 20
        self._invoker_id = invoker_id
        self._on_confirm = on_confirm

        # Build buttons dynamically so labels come from the caller
        btn_confirm = discord.ui.Button(label=confirm_label, style=discord.ButtonStyle.danger)
        btn_cancel = discord.ui.Button(label=cancel_label, style=discord.ButtonStyle.secondary)

        btn_confirm.callback = self._confirm_callback
        btn_cancel.callback = self._cancel_callback

        self.add_item(btn_confirm)
        self.add_item(btn_cancel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._invoker_id:
            await interaction.response.send_message(
                "❌ Only the mod who ran this command can confirm.", ephemeral=True
            )
            return False
        return True

    async def _confirm_callback(self, interaction: discord.Interaction) -> None:
        try:
            await self._on_confirm(interaction)
        except Exception as exc:
            await interaction.response.edit_message(content=f"⚠️ Failed: {exc}", view=None)
        self.stop()

    async def _cancel_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content="❌ Cancelled.", view=None)
        self.stop()


# ── ModerationRenderer ─────────────────────────────────────────────────────────

class ModerationRenderer:
    """
    Static factory for every moderation UI surface.

    Usage in the cog:
        return await ctx.send(
            embed=ModerationRenderer.banned(...).embed,
            view=ModerationRenderer.banned(...),
            ephemeral=True,
        )

    Or using the convenience helper:
        view = ModerationRenderer.banned(...)
        return await ctx.send(embed=view.embed, view=view, ephemeral=True)
    """

    # ── ban ───────────────────────────────────────────────────────────────────

    @staticmethod
    def banned(
        *,
        target: discord.User | discord.Member | discord.Guild | Any,
        infraction: "Infraction",
        moderator: discord.User | discord.Member,
        duration_text: str | None,
        bot: "Bot",
    ) -> _UndoBanView:
        """
        V1 ban success embed.

        Field order: User → Reason → Duration → Banned by
        Colour: red  |  Title: 🚫 User Banned / 🚫 Server Banned
        Includes ↩ Undo Ban button (30 s TTL, banning mod only).
        """
        is_server = isinstance(target, discord.Guild)
        title = "🚫 Server Banned" if is_server else "🚫 User Banned"

        embed = _EmbedFactory.action(title, discord.Colour.red())
        embed.add_field(
            name="Server" if is_server else "User",
            value=_fmt_target(target),
            inline=False,
        )
        embed.add_field(name="Reason", value=infraction.reason or "None provided", inline=False)
        embed.add_field(
            name="Duration",
            value=duration_text or "Permanent",
            inline=True,
        )
        embed.add_field(name="Banned by", value=moderator.display_name, inline=True)

        return _UndoBanView(
            embed,
            target=target,
            moderator=moderator,
            infraction_id=str(infraction.id),
            bot=bot,
        )

    @staticmethod
    def already_banned(
        bot: "Bot",
        target: discord.User | discord.Member | discord.Guild | Any,
    ) -> _EmbedView:
        """V1 error: target already banned."""
        embed = _EmbedFactory.error(
            "❌ Already Banned",
            description=f"**{_fmt_target(target)}** is already banned from MeowCall.",
        )
        return _EmbedView(embed)

    @staticmethod
    def not_banned(
        bot: "Bot",
        target: discord.User | discord.Member | discord.Guild | Any,
    ) -> _EmbedView:
        """V1 error: target not currently banned."""
        embed = _EmbedFactory.error(
            "❌ Not Banned",
            description=f"**{_fmt_target(target)}** does not have an active ban.",
        )
        return _EmbedView(embed)

    @staticmethod
    def unbanned(
        *,
        target: discord.User | discord.Member | discord.Guild | Any,
        infraction: "Infraction",
        moderator: discord.User | discord.Member,
    ) -> _EmbedView:
        """
        V1 unban success embed.

        Field order: User → Unbanned by
        Colour: green  |  Title: ✅ User Unbanned / ✅ Server Unbanned
        """
        is_server = isinstance(target, discord.Guild)
        title = "✅ Server Unbanned" if is_server else "✅ User Unbanned"

        embed = _EmbedFactory.success(title)
        embed.add_field(
            name="Server" if is_server else "User",
            value=_fmt_target(target),
            inline=False,
        )
        embed.add_field(name="Unbanned by", value=moderator.display_name, inline=False)
        return _EmbedView(embed)

    # ── warn ──────────────────────────────────────────────────────────────────

    @staticmethod
    def warned(
        *,
        target: discord.User | discord.Member | discord.Guild | Any,
        infraction: "Infraction",
        moderator: discord.User | discord.Member,
        total_warnings: int,
    ) -> _EmbedView:
        """
        V1 warn success embed.

        Field order: User → Reason → Total warnings → Warned by
        Colour: yellow  |  Title: ⚠️ Warning Issued
        """
        embed = _EmbedFactory.warning("⚠️ Warning Issued")
        embed.add_field(name="User", value=_fmt_target(target), inline=False)
        embed.add_field(name="Reason", value=infraction.reason or "None provided", inline=False)
        embed.add_field(name="Total warnings", value=str(total_warnings), inline=True)
        embed.add_field(name="Warned by", value=moderator.display_name, inline=True)
        return _EmbedView(embed)

    # ── infraction ops ────────────────────────────────────────────────────────

    @staticmethod
    def infraction_revoked(
        *,
        infraction: "Infraction",
        moderator: discord.User | discord.Member,
    ) -> _EmbedView:
        """
        V2-new command styled in V1 language.

        Field order: Infraction ID → Type → Target → Reason → Revoked by
        Colour: green  |  Title: ✅ Infraction Revoked
        """
        target_value = (
            f"User `{infraction.userId}`" if infraction.userId
            else f"Server `{infraction.serverId}`" if infraction.serverId
            else "Unknown"
        )
        embed = _EmbedFactory.success("✅ Infraction Revoked")
        embed.add_field(name="Infraction ID", value=f"`{infraction.id}`", inline=False)
        embed.add_field(name="Type", value=str(infraction.type.value).capitalize(), inline=True)
        embed.add_field(name="Target", value=target_value, inline=True)
        embed.add_field(name="Reason", value=infraction.reason or "None provided", inline=False)
        embed.add_field(name="Revoked by", value=moderator.display_name, inline=True)
        return _EmbedView(embed)

    @staticmethod
    def infraction_deleted(
        *,
        infraction: "Infraction",
        moderator: discord.User | discord.Member,
    ) -> _EmbedView:
        """
        V2-new command styled in V1 language.

        Field order: Infraction ID → Type → Target → Deleted by
        Colour: red (destructive action)  |  Title: 🗑️ Infraction Deleted
        """
        target_value = (
            f"User `{infraction.userId}`" if infraction.userId
            else f"Server `{infraction.serverId}`" if infraction.serverId
            else "Unknown"
        )
        embed = _EmbedFactory.action("🗑️ Infraction Deleted", discord.Colour.red())
        embed.add_field(name="Infraction ID", value=f"`{infraction.id}`", inline=False)
        embed.add_field(name="Type", value=str(infraction.type.value).capitalize(), inline=True)
        embed.add_field(name="Target", value=target_value, inline=True)
        embed.add_field(name="Deleted by", value=moderator.display_name, inline=True)
        return _EmbedView(embed)

    # ── generic errors ────────────────────────────────────────────────────────

    @staticmethod
    def not_found(
        bot: "Bot",
        identifier: Any,
    ) -> _EmbedView:
        """V1-style 'not found' error — used for missing infraction IDs, calls, etc."""
        embed = _EmbedFactory.error(
            "❌ Not Found",
            description=f"No record found for `{identifier}`.",
        )
        return _EmbedView(embed)

    @staticmethod
    def invalid_duration(bot: "Bot") -> _EmbedView:
        """V1-style duration parse error."""
        embed = _EmbedFactory.error(
            "❌ Invalid Duration",
            description=(
                "Could not parse the duration you provided.\n"
                "Examples: `1h`, `7d`, `2w`, `permanent`"
            ),
        )
        return _EmbedView(embed)

    @staticmethod
    def no_call_history(
        bot: "Bot",
        target: discord.User | discord.Member | discord.Guild | Any,
    ) -> _EmbedView:
        """V1-style empty-state for call history."""
        embed = _EmbedFactory.info(
            "📲 No Call History",
            description=f"**{_fmt_target(target)}** has no recorded calls.",
        )
        return _EmbedView(embed)