from __future__ import annotations

import asyncio
import contextlib
import datetime
import io
import random
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from redis.exceptions import MaxConnectionsError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from core.cogs import CogBase
from repositories.messageRepository import MessageRepository
from services.userphone.validationService import ValidationService
from utils import logger, redis_client
from utils.discord.errors import send_error_message
from utils.helpers import send_webhook_with_retry, validate_channel
from utils.message_buffer import (
    build_report_replay_messages,
    flush_channel_messages,
    get_buffered_messages_for_channels,
)
from utils.redis.cache import CacheManager
from utils.runtime.constants import CALL_LOG_CHANNEL_ID, REPORTS_CHANNEL_ID, TIPS
from utils.userphone import (
    ValidationCtx,
    create_connection_webhook,
    ensure_connection_webhook,
    make_service,
    redis_clear_warned,
    redis_delete_call_cache,
    redis_delete_waiting_msg,
    redis_get_waiting_msg,
    redis_get_webhook,
    redis_is_reported_by_key,
    redis_set_reported_by_key,
    redis_set_waiting_msg,
    resolve_webhook_for_channel,
)

if TYPE_CHECKING:
    from core.bot import Bot


# ---------------------------------------------------------------------------
# Redis helper — retries on pool exhaustion, returns None on failure
# ---------------------------------------------------------------------------


async def _redis_call_with_retry(coro_fn, *args, retries: int = 3, backoff: float = 0.1):
    """
    Attempt a Redis coroutine with retries on MaxConnectionsError.
    Returns None on failure so callers can handle gracefully.
    """
    for attempt in range(retries):
        try:
            return await coro_fn(*args)
        except MaxConnectionsError:
            if attempt < retries - 1:
                await asyncio.sleep(backoff * (attempt + 1))
            else:
                logger.warning(
                    f"Redis pool exhausted after {retries} attempts calling "
                    f"{getattr(coro_fn, '__name__', repr(coro_fn))}({args})"
                )
                return None
        except Exception as e:
            logger.error(
                f"Unexpected Redis error in "
                f"{getattr(coro_fn, '__name__', repr(coro_fn))}({args}): {e}"
            )
            return None


# ---------------------------------------------------------------------------
# Report action helpers — mirrors moderation.py
# ---------------------------------------------------------------------------


async def _replay_messages_in_thread(
    thread: discord.Thread,
    messages: list[dict],
    bot: discord.Client,
) -> None:
    """
    Replay captured report messages into a thread using webhooks so each
    message appears under the original sender's name and avatar.
    Messages are replayed chronologically as they were captured.
    """
    parent = thread.parent
    if not isinstance(
        parent, (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel)
    ):
        await thread.send("⚠️ Replay failed: Parent channel is not a text channel.")
        return

    webhook: discord.Webhook | None = None
    try:
        for wh in await parent.webhooks():
            if wh.user and bot.user and wh.user.id == bot.user.id:
                webhook = wh
                break
        if webhook is None:
            webhook = await parent.create_webhook(name="MeowCall Replay")
    except (discord.Forbidden, discord.HTTPException) as e:
        await thread.send(f"⚠️ Could not set up replay webhook: {e}")
        return

    for payload in messages:
        display_name = str(payload.get("author") or "Unknown")
        avatar_url = payload.get("author_avatar")
        content = str(payload.get("content") or "").strip()
        channel_label = str(payload.get("channel_label") or "Unknown Channel")
        attachments = payload.get("attachments")
        if not isinstance(attachments, list):
            attachments = []
        reply_to = payload.get("reply_to")

        reply_embed: discord.Embed | None = None
        if reply_to:
            reply_embed = discord.Embed(
                description=str(reply_to.get("content") or "")[:250],
                color=discord.Color.light_grey(),
            )
            author_name = f"Replying to {reply_to.get('author') or 'Unknown'}"
            author_avatar = reply_to.get("author_avatar")
            if author_avatar:
                reply_embed.set_author(name=author_name, icon_url=str(author_avatar))
            else:
                reply_embed.set_author(name=author_name)

        body_parts: list[str] = []
        body_parts.append(f"[{channel_label}]")
        if reply_to:
            body_parts.append(
                f"> ↩ {reply_to.get('author') or 'Unknown'}: {str(reply_to.get('content') or '')[:100]}"
            )
        if content:
            body_parts.append(content)
        if attachments:
            body_parts.append("\n".join(str(url) for url in attachments))

        body = "\n".join(part for part in body_parts if part).strip()

        try:
            kwargs = {
                "content": body if body else None,
                "username": display_name[:80],
                "avatar_url": str(avatar_url) if avatar_url else None,
                "thread": thread,
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            if reply_embed is not None:
                kwargs["embeds"] = [reply_embed]

            await send_webhook_with_retry(webhook, **kwargs)
        except discord.HTTPException:
            fallback_reply = (
                f"> ↩ {reply_to.get('author') or 'Unknown'}: {str(reply_to.get('content') or '')[:100]}\n"
                if reply_to
                else ""
            )
            fallback_content = body or "[No content]"
            await thread.send(
                f"{fallback_reply}**{display_name}** ({channel_label}): {fallback_content}"
            )

        await asyncio.sleep(0.6)

    await thread.send("✅ **Replay complete.**")


def _build_report_replay_messages(
    buffered_messages: list[dict],
    source_channel: discord.abc.GuildChannel,
    target_channel: discord.abc.GuildChannel,
) -> list[dict]:
    source_label = f"{source_channel.name} ({source_channel.guild.name})"
    target_label = f"{target_channel.name} ({target_channel.guild.name})"

    messages_by_id = {
        str(message.get("id")): message for message in buffered_messages if message.get("id")
    }
    captured_messages: list[dict] = []

    for payload in buffered_messages:
        channel_label = (
            source_label
            if str(payload.get("channel_id")) == str(source_channel.id)
            else target_label
        )

        msg_data = {
            "author": payload.get("author_name") or f"User {payload.get('author_id')}",
            "author_id": payload.get("author_id"),
            "author_avatar": payload.get("author_avatar"),
            "content": payload.get("content"),
            "attachments": payload.get("images_url") or [],
            "timestamp": payload.get("timestamp"),
            "channel_label": channel_label,
        }

        referred_id = payload.get("referred_message_id")
        if referred_id is not None:
            referred_payload = messages_by_id.get(str(referred_id))
            if referred_payload:
                msg_data["reply_to"] = {
                    "author": referred_payload.get("author_name")
                    or f"User {referred_payload.get('author_id')}",
                    "author_avatar": referred_payload.get("author_avatar"),
                    "content": referred_payload.get("content"),
                }

        captured_messages.append(msg_data)

    return captured_messages


class ReportActionView(discord.ui.View):
    """Buttons attached to report embeds: Resolved, Dismissed, and Recreate Convo."""

    def __init__(
        self,
        captured_messages: list | None = None,
        source_label: str = "Source Channel",
        target_label: str = "Connected Channel",
    ):
        super().__init__(
            timeout=None
        )  # Persistent — survives bot restarts if custom_id is set
        self._captured_messages: list = captured_messages or []
        self._source_label = source_label
        self._target_label = target_label

    @discord.ui.button(
        label="Resolved",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="report:resolved",
    )
    async def resolved(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        from utils.helpers import is_mod

        if not is_mod(interaction.user):
            await interaction.response.send_message("❌ Mods only.", ephemeral=True)
            return
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"✅ Resolved by {interaction.user.display_name}")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="Dismissed",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="report:dismissed",
    )
    async def dismissed(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        from utils.helpers import is_mod

        if not is_mod(interaction.user):
            await interaction.response.send_message("❌ Mods only.", ephemeral=True)
            return
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()
        embed.set_footer(text=f"❌ Dismissed by {interaction.user.display_name}")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="Recreate Convo",
        emoji="🔁",
        style=discord.ButtonStyle.secondary,
        custom_id="report:recreate",
    )
    async def recreate(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        from utils.helpers import is_mod

        if not is_mod(interaction.user):
            await interaction.response.send_message("❌ Mods only.", ephemeral=True)
            return

        all_messages = self._captured_messages
        if not all_messages:
            await interaction.response.send_message(
                "⚠️ No message data available — this report was sent before bot restart or had no messages.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            thread = await interaction.message.create_thread(
                name=f"📼 Replay · {datetime.datetime.now(datetime.UTC).strftime('%m/%d %H:%M')}",
                auto_archive_duration=1440,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"⚠️ Could not create thread: {e}", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"🔁 Recreating conversation in {thread.mention}...", ephemeral=True
        )

        try:
            await _replay_messages_in_thread(
                thread=thread,
                messages=self._captured_messages,
                bot=interaction.client,
            )
        except Exception as e:
            from utils import logger

            logger.error("Recreate convo error: %s", e)
            await thread.send(f"⚠️ Replay failed partway through: {e}")


async def _show_random_tip(channel: discord.TextChannel | discord.Thread) -> None:
    """Send a random tip to the channel, silently ignoring errors."""
    try:
        tip = random.choice(TIPS)
        await channel.send(tip)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass


class Userphone(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None) -> None:
        super().__init__(bot, emoji)
        self._cache_manager = CacheManager()
        self._validation_service: ValidationService | None = (
            ValidationService(bot.http_session) if bot.http_session else None
        )
        self._queue_join_buffer: list[tuple[str, str, str, str]] = []
        self._queue_join_buffer_lock = asyncio.Lock()
        self._queue_join_flush_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def cog_load(self) -> None:
        if self._validation_service is None and self.bot.http_session:
            self._validation_service = ValidationService(self.bot.http_session)

    async def cog_unload(self) -> None:
        flush_task = self._queue_join_flush_task
        if flush_task is not None and not flush_task.done():
            flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await flush_task

        await self._flush_queue_join_logs()
        self._validation_service = None
        self._cache_manager = CacheManager()
        await super().cog_unload()

    # ------------------------------------------------------------------
    # Internal shortcut — keeps call sites tidy
    # ------------------------------------------------------------------

    async def _check(
        self,
        ctx: commands.Context[Bot],
        *,
        check_username: bool = True,
        check_guild_name: bool = True,
    ) -> tuple[bool, str | None]:
        from utils.userphone import check_validation_only

        is_valid, error_msg = await check_validation_only(
            ValidationCtx(author=ctx.author, guild=ctx.guild),
            cache_manager=self._cache_manager,
            validation_service=self._validation_service,
            check_username=check_username,
            check_guild_name=check_guild_name,
        )
        if not is_valid:
            return False, error_msg

        try:
            async with self.bot.db.uow() as uow_check:
                if self._validation_service is not None:
                    return await self._validation_service.check_bans_and_validation(
                        ValidationCtx(author=ctx.author, guild=ctx.guild),
                        uow_check.session,
                        cache_manager=self._cache_manager,
                        bot=self.bot,
                        check_username=False,
                        check_guild_name=False,
                    )

                from utils.userphone import check_bans_and_validation

                return await check_bans_and_validation(
                    ValidationCtx(author=ctx.author, guild=ctx.guild),
                    uow_check.session,
                    cache_manager=self._cache_manager,
                    validation_service=None,
                    bot=self.bot,
                    check_username=False,
                    check_guild_name=False,
                )
        except PoolTimeout:
            logger.error("DB pool exhausted during userphone validation check")
            return False, "Unable to process your request right now. Please try again."

    # ==================================================================
    # Commands
    # ==================================================================

    async def _perform_call_logic(self, ctx: commands.Context[Bot], webhook_url: str):
        """Execute the database logic for starting or queuing a call."""
        from services.userService import UserService

        async with self.bot.db.uow() as uow_write:
            await UserService(uow_write.session).upsert_user(ctx.author)
            svc = make_service(uow_write.session)
            await svc.ensure_connection(
                ctx.channel.id, ctx.guild.id, webhook_url
            )
            result = await svc.start_or_queue_call(
                channel_id=ctx.channel.id,
                guild_id=ctx.guild.id,
                user_id=ctx.author.id,
            )
            if result.matched and result.partner_call is not None:
                await svc.link_connections(
                    ctx.channel.id, result.partner_call.channelId
                )
            return result

    @commands.hybrid_command(
        name="call",
        description="📞 - Connect your server to another!",
        aliases=["c", "userphone", "cal", "calll"],
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    @app_commands.checks.cooldown(1, 15.0, key=lambda i: i.user.id)
    @commands.guild_only()
    async def call(self, ctx: commands.Context[Bot]):
        ephemeral = ctx.interaction is not None
        await _redis_call_with_retry(redis_clear_warned, ctx.channel.id)
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(ephemeral=False)
            except discord.HTTPException:
                pass

        is_valid, error_msg = await self._check(ctx, check_guild_name=True, check_username=True)
        if not is_valid:
            await send_error_message(ctx, error_msg, ephemeral=True)
            return

        webhook_url_error = False
        result = None

        webhook_url = await _redis_call_with_retry(redis_get_webhook, ctx.channel.id)
        if webhook_url is None:
            try:
                async with self.bot.db.uow() as uow_read:
                    webhook_url = await ensure_connection_webhook(
                        make_service(uow_read.session), ctx.channel
                    )
            except PoolTimeout:
                logger.error("DB pool exhausted during call webhook read")
                await send_error_message(
                    ctx,
                    "Unable to start the call right now. Please try again.",
                    ephemeral=ephemeral,
                )
                return

        if webhook_url is None:
            webhook_url = await create_connection_webhook(ctx.channel)

        if webhook_url is None:
            webhook_url_error = True

        if not webhook_url_error:
            result = None
            try:
                result = await self._perform_call_logic(ctx, webhook_url)
            except PoolTimeout:
                logger.error("DB pool exhausted during call write phase")
                await send_error_message(
                    ctx,
                    "Unable to start the call right now. Please try again.",
                    ephemeral=ephemeral,
                )
                return

        if webhook_url_error:
            await send_error_message(
                ctx,
                "I need webhook permissions in this channel to start a call.",
                ephemeral=ephemeral,
            )
            return

        if result is None:
            await send_error_message(
                ctx,
                "Unable to start the call right now. Please try again.",
                ephemeral=ephemeral,
            )
            return

        if result.already_in_call:
            await send_error_message(
                ctx,
                "You are already in a call.",
                title="⏳ Hold up!",
                ephemeral=ephemeral,
            )
        elif result.matched:
            partner_name = "Unknown Server"
            if result.partner_call is not None:
                partner_guild = self.bot.get_guild(int(result.partner_call.guildId))
                if partner_guild:
                    partner_name = partner_guild.name
                    await self._cache_manager.flush_userphone_access_cache(
                        guild_id=ctx.guild.id
                    )

            await ctx.send(f"📞 **Connected to {partner_name}!**")
            asyncio.create_task(_show_random_tip(ctx.channel))

            if result.partner_call is not None:
                partner_channel_id = int(result.partner_call.channelId)
                await redis_clear_warned(partner_channel_id)
                msg_content = f'📞 **Connected to {ctx.guild.name}!**'
                waiting_msg_id = await redis_get_waiting_msg(partner_channel_id)
                if waiting_msg_id:
                    await redis_delete_waiting_msg(partner_channel_id)
                    partner_channel = self.bot.get_channel(partner_channel_id)
                    if partner_channel:
                        try:
                            partner_msg = await partner_channel.fetch_message(int(waiting_msg_id))
                            await partner_msg.edit(content=msg_content)
                        except discord.HTTPException:
                            pass
                else:
                    partner_channel = self.bot.get_channel(partner_channel_id)
                    if partner_channel:
                        try:
                            await partner_channel.send(msg_content)
                        except discord.HTTPException:
                            pass
        else:
            msg = await ctx.send('☎️ Waiting for someone else to pick up...')
            await redis_set_waiting_msg(ctx.channel.id, msg.id)
            await self.notify_queue_join(ctx.author, ctx.guild)
            asyncio.create_task(_show_random_tip(ctx.channel))

    @commands.hybrid_command(
        name="skip",
        description="⏩ - Skip this server, and connect to a new one.",
        aliases=["s", "ski", "skipp"],
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    @app_commands.checks.cooldown(1, 15.0, key=lambda i: i.user.id)
    @commands.guild_only()
    async def skip(self, ctx: commands.Context[Bot]):
        ephemeral = ctx.interaction is not None
        await _redis_call_with_retry(redis_clear_warned, ctx.channel.id)
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(ephemeral=False)
            except discord.HTTPException:
                pass

        is_valid, error_msg = await self._check(ctx, check_guild_name=True)
        if not is_valid:
            await send_error_message(ctx, error_msg, ephemeral=True)
            return

        async def _do_skip(uow):
            svc = make_service(uow.session)
            skip_result = await svc.skip_and_rematch(
                ctx.channel.id, ctx.guild.id, ctx.author.id
            )
            if skip_result.old_my_call is not None:
                await svc.unlink_connections(ctx.channel.id)
            if (
                skip_result.rematched
                and skip_result.new_partner_call is not None
                and skip_result.my_call is not None
            ):
                await svc.link_connections(
                    skip_result.my_call.channelId, skip_result.new_partner_call.channelId
                )
            return skip_result

        result = None
        try:
            async with self.bot.db.uow() as uow:
                result = await _do_skip(uow)
        except PoolTimeout:
            logger.error("DB pool exhausted during skip")
            await send_error_message(
                ctx, "Unable to skip right now. Please try again.", ephemeral=ephemeral
            )
            return

        await _redis_call_with_retry(redis_delete_call_cache, ctx.channel.id)
        if result is not None and result.old_partner_call is not None:
            await _redis_call_with_retry(
                redis_delete_call_cache, int(result.old_partner_call.channelId)
            )

        if result is None:
            await send_error_message(
                ctx,
                "Unable to skip the call right now. Please try again.",
                ephemeral=ephemeral,
            )
            return

        if not result.was_in_call:
            await send_error_message(
                ctx, "You need to be in a call before skipping.", ephemeral=ephemeral
            )
        elif result.rematched:
            partner_name = 'Unknown Server'
            if result.new_partner_call is not None:
                partner_guild = self.bot.get_guild(int(result.new_partner_call.guildId))
                if partner_guild:
                    partner_name = partner_guild.name
                    await self._cache_manager.flush_userphone_access_cache(
                        guild_id=ctx.guild.id
                    )
            await ctx.send(f"📞 **Connected to {partner_name}!**")
            asyncio.create_task(_show_random_tip(ctx.channel))

            if result.old_partner_call is not None:
                old_partner_channel = self.bot.get_channel(
                    int(result.old_partner_call.channelId)
                )
                if old_partner_channel:
                    try:
                        await old_partner_channel.send(
                            "❗ **The other server has skipped the connection.**"
                        )
                    except discord.HTTPException:
                        pass

            if result.new_partner_call is not None:
                partner_channel_id = int(result.new_partner_call.channelId)
                await redis_clear_warned(partner_channel_id)
                msg_content = f'📞 **Connected to {ctx.guild.name}!**'
                waiting_msg_id = await redis_get_waiting_msg(partner_channel_id)
                if waiting_msg_id:
                    await redis_delete_waiting_msg(partner_channel_id)
                    partner_channel = self.bot.get_channel(partner_channel_id)
                    if partner_channel:
                        try:
                            partner_msg = await partner_channel.fetch_message(int(waiting_msg_id))
                            await partner_msg.edit(content=msg_content)
                        except discord.HTTPException:
                            pass
                else:
                    partner_channel = self.bot.get_channel(partner_channel_id)
                    if partner_channel:
                        try:
                            await partner_channel.send(msg_content)
                        except discord.HTTPException:
                            pass
        else:
            if result.old_partner_call is not None:
                old_partner_channel = self.bot.get_channel(
                    int(result.old_partner_call.channelId)
                )
                if old_partner_channel:
                    try:
                        await old_partner_channel.send(
                            "❗ **The other server has skipped the connection.**"
                        )
                    except discord.HTTPException:
                        pass
            msg = await ctx.send('⏩ **Skipped! Searching for a new server...**')
            await redis_set_waiting_msg(ctx.channel.id, msg.id)
            await self.notify_queue_join(ctx.author, ctx.guild)
            asyncio.create_task(_show_random_tip(ctx.channel))

    @commands.hybrid_command(
        name="hang",
        description="☎️ - Hangup the phone, and end the connection.",
        aliases=["h", "hangup", "end", "han", "hangg"],
    )
    @commands.guild_only()
    async def hang(self, ctx: commands.Context[Bot]):
        ephemeral = ctx.interaction is not None
        await _redis_call_with_retry(redis_clear_warned, ctx.channel.id)
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(ephemeral=False)
            except discord.HTTPException:
                pass

        is_valid, error_msg = await self._check(ctx)
        if not is_valid:
            await send_error_message(ctx, error_msg, ephemeral=True)
            return

        result = None
        try:
            async with self.bot.db.uow() as uow:
                svc = make_service(uow.session)
                result = await svc.end_call_with_info(ctx.channel.id)
                if result.was_in_call:
                    await svc.unlink_connections(ctx.channel.id)
        except PoolTimeout:
            logger.error("DB pool exhausted during hang")
            await send_error_message(
                ctx,
                "Unable to end the call right now. Please try again.",
                ephemeral=ephemeral,
            )
            return

        await _redis_call_with_retry(redis_delete_call_cache, ctx.channel.id)

        if result is None:
            await send_error_message(
                ctx,
                "Unable to end the call right now. Please try again.",
                ephemeral=ephemeral,
            )
            return

        if result.was_in_call:
            await ctx.send("🔌 **Call ended!** Channel unlinked successfully.")
            await _redis_call_with_retry(redis_delete_waiting_msg, ctx.channel.id)
            if result.paired_call is not None:
                paired_channel_id = int(result.paired_call.channelId)
                await _redis_call_with_retry(redis_delete_call_cache, paired_channel_id)
                paired_channel = self.bot.get_channel(paired_channel_id)
                if paired_channel:
                    try:
                        await paired_channel.send(
                            "❗ **The other server has disconnected.**"
                        )
                    except discord.HTTPException:
                        pass
        else:
            await send_error_message(
                ctx, "You are not currently in a call.", ephemeral=ephemeral
            )

    @commands.hybrid_command(
        name="friendrequest",
        description="🫂 - Send your username to the other party!",
        aliases=["fr", "fq", "freq", "friend", "request", "frequest"],
    )
    @commands.guild_only()
    async def frequest(self, ctx: commands.Context[Bot]):
        ephemeral = ctx.interaction is not None
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(ephemeral=ephemeral)
            except discord.HTTPException:
                pass

        is_valid, error_msg = await self._check(ctx)
        if not is_valid:
            await send_error_message(ctx, error_msg, ephemeral=True)
            return

        error_msg = None
        target_channel_id = None
        target_webhook_url = None

        try:
            async with self.bot.db.uow() as uow:
                svc = make_service(uow.session)
                call = await svc.get_active_call_for_channel(str(ctx.channel.id))

                if call is None:
                    error_msg = "You need to be in a call before using friend request."
                else:
                    paired_call = await svc.get_paired_call(call)
                    if paired_call is None:
                        error_msg = "No paired server is available right now."
                    else:
                        target_channel_id = int(paired_call.channelId)
                        target_channel_tmp = self.bot.get_channel(target_channel_id)
                        if isinstance(
                            target_channel_tmp, (discord.TextChannel, discord.Thread)
                        ):
                            target_webhook_url = await resolve_webhook_for_channel(
                                target_channel_tmp, service=svc
                            )
                            cached_wh = await _redis_call_with_retry(
                                redis_get_webhook, target_channel_id
                            )
                            if target_webhook_url and target_webhook_url != cached_wh:
                                target_connection = await svc.get_connection(
                                    target_channel_id
                                )
                                await svc.ensure_connection(
                                    target_channel_id,
                                    target_channel_tmp.guild.id,
                                    target_webhook_url,
                                    parent_id=target_connection.parentId
                                    if target_connection
                                    else None,
                                )
        except PoolTimeout:
            logger.error("DB pool exhausted during frequest call lookup")
            await send_error_message(
                ctx,
                "Unable to send friend request right now. Please try again.",
                ephemeral=ephemeral,
            )
            return

        if error_msg:
            await send_error_message(ctx, error_msg, ephemeral=ephemeral)
            return

        target_channel = self.bot.get_channel(target_channel_id)
        if target_channel is None:
            try:
                target_channel = await self.bot.fetch_channel(target_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                target_channel = None

        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            await send_error_message(
                ctx, "Could not resolve the paired channel.", ephemeral=ephemeral
            )
            return

        if target_webhook_url is None:
            target_webhook_url = await resolve_webhook_for_channel(target_channel)

        if target_webhook_url is None:
            await send_error_message(
                ctx,
                "I need webhook permissions in the paired channel to send this.",
                ephemeral=ephemeral,
            )
            return

        if self.bot.http_session is None:
            await send_error_message(
                ctx, "HTTP session is not ready.", ephemeral=ephemeral
            )
            return

        embed = discord.Embed(
            title="📬 Friend Request Suggestion",
            description=(
                f"**{ctx.author.display_name}** (`{ctx.author.name}`) from **{ctx.guild.name}** "
                "would like to add someone as a friend!"
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="MeowCall Friend System")
        if ctx.author.display_avatar:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

        webhook = discord.Webhook.from_url(
            target_webhook_url, session=self.bot.http_session
        )
        await send_webhook_with_retry(webhook, embed=embed)
        await ctx.send("✅ **Friend request sent to the other server!**")

    # ==================================================================
    # Report command
    # ==================================================================

    @commands.hybrid_command(
        name="report",
        description="Report inappropriate behavior during a call",
    )
    @discord.app_commands.describe(reason="Reason for reporting this call connection")
    @commands.guild_only()
    async def report(self, ctx: commands.Context[Bot], *, reason: str):
        ephemeral = ctx.interaction is not None
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(ephemeral=ephemeral)
            except discord.HTTPException:
                pass

        error_msg = None
        target_channel_id = None
        call_started_at = None

        is_valid, error_msg_ban = await self._check(ctx)
        if not is_valid:
            await send_error_message(ctx, error_msg_ban, ephemeral=True)
            return

        # UoW 1: call/paired lookup.
        try:
            async with self.bot.db.uow() as uow:
                svc = make_service(uow.session)
                call = await svc.get_active_call_for_channel(str(ctx.channel.id))

                if call is None:
                    error_msg = "You must be in an active call to use `/report`."
                else:
                    paired_call = await svc.get_paired_call(call)
                    if paired_call is None:
                        error_msg = "No paired server is available right now."
                    else:
                        target_channel_id = int(paired_call.channelId)
                        call_started_at = call.createdAt
        except PoolTimeout:
            logger.error("DB pool exhausted during report ban+call lookup")
            await send_error_message(
                ctx,
                "Unable to submit report right now. Please try again.",
                ephemeral=ephemeral,
            )
            return

        if error_msg:
            await send_error_message(ctx, error_msg, ephemeral=ephemeral)
            return

        source_channel = ctx.channel

        # Scope the dedup key to this specific call instance so it can never
        # bleed across calls or fire a false positive from a previous session.
        lo, hi = sorted([source_channel.id, target_channel_id])
        report_key = f"{lo}:{hi}:{call.id}"
        already_reported = await _redis_call_with_retry(redis_is_reported_by_key, report_key)
        if already_reported:
            await send_error_message(
                ctx,
                "This call has already been reported. Thank you!",
                ephemeral=ephemeral,
            )
            return

        target_channel = self.bot.get_channel(target_channel_id)
        if target_channel is None:
            try:
                target_channel = await self.bot.fetch_channel(target_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await send_error_message(
                    ctx, "Could not access the connected channel.", ephemeral=ephemeral
                )
                return

        if not (
            await validate_channel(source_channel)
            and await validate_channel(target_channel)
        ):
            await send_error_message(
                ctx,
                "I don't have permission to access one of the channels!",
                ephemeral=ephemeral,
            )
            return

        reports_channel = self.bot.get_channel(REPORTS_CHANNEL_ID)
        if not reports_channel:
            await send_error_message(
                ctx, "Reporting system is currently unavailable.", ephemeral=ephemeral
            )
            return

        if call_started_at.tzinfo is None:
            call_started_at = call_started_at.replace(tzinfo=datetime.UTC)

        source_label = f"{source_channel.name} ({source_channel.guild.name})"
        target_label = f"{target_channel.name} ({target_channel.guild.name})"

        captured_messages: list[dict] = []
        participant_lines: list[str] = []
        seen_ids: set[str] = set()

        # Prefer the live relay buffer so active-call reports do not depend on
        # the deferred DB flush. Fall back to the current DB query if needed.
        try:
            buffered_messages = await get_buffered_messages_for_channels(
                [source_channel.id, target_channel_id]
            )

            if buffered_messages:
                captured_messages = build_report_replay_messages(
                    buffered_messages, source_channel, target_channel
                )

                for payload in buffered_messages:
                    author_id = str(payload.get("author_id"))
                    if author_id not in seen_ids:
                        seen_ids.add(author_id)
                        guild_name = (
                            source_channel.guild.name
                            if str(payload.get("channel_id")) == str(source_channel.id)
                            else target_channel.guild.name
                        )
                        author_display = payload.get("author_name") or f"User {author_id}"
                        participant_lines.append(
                            f"{author_display} (`{author_id}`) — {guild_name}"
                        )
            else:
                async with self.bot.db.uow() as uow:
                    message_repo = MessageRepository(uow.session)
                    rows = await message_repo.get_recent_with_details_by_channels(
                        [source_channel.id, target_channel_id], call_started_at, limit=60
                    )

                    for db_msg, author, ref_msg, ref_author in rows:
                        msg_data = {
                            "author": author.name if author else f"User {db_msg.authorId}",
                            "author_id": author.id if author else db_msg.authorId,
                            "author_avatar": author.image if author else None,
                            "content": db_msg.content,
                            "attachments": db_msg.imagesUrl or [],
                            "timestamp": db_msg.createdAt.isoformat()
                            if db_msg.createdAt
                            else None,
                            "channel_label": source_label
                            if db_msg.channelId == str(source_channel.id)
                            else target_label,
                        }

                        if ref_msg:
                            msg_data["reply_to"] = {
                                "author": ref_author.name if ref_author else "Unknown",
                                "author_avatar": ref_author.image if ref_author else None,
                                "content": ref_msg.content,
                            }

                        captured_messages.append(msg_data)

                        # Track participants for the embed field
                        author_id = author.id if author else db_msg.authorId
                        if author_id not in seen_ids:
                            seen_ids.add(author_id)
                            guild_name = (
                                source_channel.guild.name
                                if db_msg.channelId == str(source_channel.id)
                                else target_channel.guild.name
                            )
                            author_display = author.name if author else f"User {author_id}"
                            participant_lines.append(
                                f"{author_display} (`{author_id}`) — {guild_name}"
                            )

        except Exception as e:
            logger.error(f"Error fetching messages for report: {e}")
            captured_messages.append({"error": f"Could not fetch messages: {e!s}"})

        participants_value = (
            "\n".join(participant_lines)
            if participant_lines
            else "No messages captured"
        )

        report_embed = discord.Embed(
            title="⚠️ NEW USER REPORT",
            color=discord.Color.red(),
            description=f"**Reason:** {reason}",
            timestamp=datetime.datetime.now(datetime.UTC),
        )
        report_embed.add_field(
            name="Reported by",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False,
        )
        report_embed.add_field(
            name="Source Channel",
            value=f"{source_channel.name} in {source_channel.guild.name}\nChannel ID: `{source_channel.id}` | Guild ID: `{source_channel.guild.id}`",
            inline=False,
        )
        report_embed.add_field(
            name="Connected Channel",
            value=f"{target_channel.name} in {target_channel.guild.name}\nChannel ID: `{target_channel.id}` | Guild ID: `{target_channel.guild.id}`",
            inline=False,
        )
        report_embed.add_field(
            name=f"Participants ({len(participant_lines)})",
            value=participants_value[:1000],
            inline=False,
        )

        action_view = ReportActionView(
            captured_messages=captured_messages
            if captured_messages and "error" not in captured_messages[0]
            else [],
            source_label=source_label,
            target_label=target_label,
        )

        try:
            await reports_channel.send(embed=report_embed, view=action_view)
            await _redis_call_with_retry(redis_set_reported_by_key, report_key)
            try:
                async with self.bot.db.uow() as uow:
                    await flush_channel_messages(uow.session, source_channel.id)
                    await flush_channel_messages(uow.session, target_channel_id)
            except Exception as flush_error:
                logger.error(f"Error flushing report replay buffer: {flush_error}")
            logger.info(
                f"Report submitted successfully for call {source_channel.id} <-> {target_channel_id}"
            )
        except Exception as e:
            logger.error(f"Failed to send report to HQ: {e}")
            await send_error_message(
                ctx,
                "Failed to submit report. Please try again or join our support server.",
                ephemeral=ephemeral,
            )
            return

        # End the active call on both sides immediately after the report is filed.
        end_result = None
        try:
            async with self.bot.db.uow() as uow:
                svc = make_service(uow.session)
                end_result = await svc.end_call_with_info(source_channel.id)
                if end_result and end_result.was_in_call:
                    await svc.unlink_connections(source_channel.id)
        except PoolTimeout:
            logger.error("DB pool exhausted while ending call after report")
        except Exception as e:
            logger.error(f"Unexpected error ending call after report: {e}")

        await _redis_call_with_retry(redis_delete_call_cache, source_channel.id)

        if end_result and end_result.was_in_call:
            # Notify the partner channel that the call was ended due to a report.
            if end_result.paired_call is not None:
                paired_channel_id = int(end_result.paired_call.channelId)
                await _redis_call_with_retry(redis_delete_call_cache, paired_channel_id)
                paired_channel = self.bot.get_channel(paired_channel_id)
                if paired_channel:
                    try:
                        await paired_channel.send("🔌 The other server disconnected.")
                    except discord.HTTPException:
                        pass

        await ctx.send(
            "✅ **Report submitted successfully.** Our staff will review it shortly.\n"
            "📵 The call has been ended.",
            ephemeral=ephemeral,
        )

    #####################################
    # Join queue notification system    #
    #                                   #
    #####################################
    QUEUE_JOIN_BATCH_SIZE = 8
    QUEUE_JOIN_FLUSH_DELAY_SECONDS = 15.0

    async def _resolve_log_channel(self) -> discord.TextChannel | discord.Thread | None:
        channel = self.bot.get_channel(CALL_LOG_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(CALL_LOG_CHANNEL_ID)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                return None

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return None

        if not await validate_channel(channel):
            return None

        return channel

    async def _send_queue_join_batch(
        self, batch: list[tuple[str, str, str, str]]
    ) -> None:
        call_log_channel = await self._resolve_log_channel()
        if call_log_channel is None:
            return

        now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        embed = discord.Embed(
            title="⏳ Server Joined Queue",
            color=discord.Color.blue(),
            timestamp=now,
        )
        embed.description = f"Batch of {len(batch)} servers joined the queue."

        for index, (initiator_name, initiator_id, guild_name, guild_id) in enumerate(
            batch, start=1
        ):
            embed.add_field(
                name=f"Queue Join {index}",
                value=(
                    f"**Initiator:** \n {initiator_name} (ID: `{initiator_id}`)\n"
                    f"**Server:** \n {guild_name} (ID: `{guild_id}`)"
                ),
                inline=False,
            )

        embed.set_footer(text="MeowCall Queue Log")
        try:
            await call_log_channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.debug("Failed to send queue join batch: %s", e)

    async def _flush_queue_join_logs(self) -> None:
        while True:
            async with self._queue_join_buffer_lock:
                if not self._queue_join_buffer:
                    if (
                        self._queue_join_flush_task is not None
                        and self._queue_join_flush_task.done()
                    ):
                        self._queue_join_flush_task = None
                    return

                batch = self._queue_join_buffer[: self.QUEUE_JOIN_BATCH_SIZE]
                del self._queue_join_buffer[: self.QUEUE_JOIN_BATCH_SIZE]

                if (
                    not self._queue_join_buffer
                    and self._queue_join_flush_task is not None
                    and self._queue_join_flush_task.done()
                ):
                    self._queue_join_flush_task = None

            await self._send_queue_join_batch(batch)

    async def _delayed_flush_queue_join_logs(self) -> None:
        try:
            await asyncio.sleep(self.QUEUE_JOIN_FLUSH_DELAY_SECONDS)
            await self._flush_queue_join_logs()
        finally:
            async with self._queue_join_buffer_lock:
                if self._queue_join_flush_task is asyncio.current_task():
                    self._queue_join_flush_task = None

    async def notify_queue_join(
        self, initiator: discord.User | discord.Member, guild: discord.Guild
    ) -> None:
        queue_entry = (
            initiator.display_name,
            str(initiator.id),
            guild.name,
            str(guild.id),
        )
        should_flush_now = False

        async with self._queue_join_buffer_lock:
            self._queue_join_buffer.append(queue_entry)
            should_flush_now = (
                len(self._queue_join_buffer) >= self.QUEUE_JOIN_BATCH_SIZE
            )

            if not should_flush_now and (
                self._queue_join_flush_task is None
                or self._queue_join_flush_task.done()
            ):
                self._queue_join_flush_task = asyncio.create_task(
                    self._delayed_flush_queue_join_logs()
                )

        if should_flush_now:
            await self._flush_queue_join_logs()


async def setup(bot: Bot):
    bot.add_view(ReportActionView())
    await bot.add_cog(Userphone(bot, "☎️"))