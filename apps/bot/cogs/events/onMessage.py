from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from models.base import Badges
from redis.exceptions import MaxConnectionsError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from core.cogs import CogBase
from repositories.userRepository import UserRepository
from services.userphone.validationService import ValidationService
from utils import logger, redis_client
from utils.helpers import send_webhook_with_retry
from utils.patterns import Patterns
from utils.redis.cache import CacheManager
from utils.userphone import (
    check_bans_and_validation,
    create_connection_webhook,
    ensure_connection_webhook,
    make_service,
    redis_delete_call_cache,
    redis_delete_webhook,
    redis_get_call_state,
    redis_get_webhook,
    redis_is_warned,
    redis_refresh_call_cache,
    redis_set_active_call,
    redis_set_paired_call,
    redis_set_warned,
    save_message_to_db,
)
from utils.message_buffer import (
    get_buffered_messages_for_channels,
    build_report_replay_messages,
)
from utils.runtime.constants import REPORTS_CHANNEL_ID
from cogs.userphone import ReportActionView

if TYPE_CHECKING:
    from core.bot import Bot


def _sanitize_username(name: str) -> str:
    """
    Sanitize usernames to prevent Discord Webhook 50035 Bad Request errors.
    Removes invisible formatting characters and zalgo-like marks that Discord blocks.
    """
    cleaned = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u0eca]", "", name).strip()
    if not cleaned or cleaned.lower() == "clyde":
        return "User"
    return cleaned[:80]


async def _redis_get_with_retry(coro_fn, *args, retries: int = 3, backoff: float = 0.1):
    """
    Call a Redis coroutine function with retries on MaxConnectionsError.
    Returns None on failure so callers can fall back to the DB path gracefully.
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
                    f"{getattr(coro_fn, '__name__', repr(coro_fn))}({args}) — falling back to DB path"
                )
                return None
        except Exception as e:
            logger.error(
                f"Unexpected Redis error calling "
                f"{getattr(coro_fn, '__name__', repr(coro_fn))}({args}): {e}"
            )
            return None


class OnMessage(CogBase):
    _MAX_RELAY_ATTEMPTS = 3
    _RETRY_BACKOFF = (0.0, 1.0, 2.0)
    _DB_READ_SEMAPHORE_SIZE = 64
    _DB_READ_SEMAPHORE_TIMEOUT = 0.2
    _INACTIVE_CALL_CACHE_TTL = 15
    _LOOKUP_THROTTLE_CACHE_TTL = 5
    _VOTER_DB_CHECK_SEMAPHORE_SIZE = 32
    _VOTER_DB_CHECK_TIMEOUT = 0.2

    def __init__(self, bot: Bot):
        super().__init__(bot, None)
        self._cache_manager = CacheManager()
        self._db_read_semaphore = asyncio.Semaphore(self._DB_READ_SEMAPHORE_SIZE)
        self._voter_db_check_semaphore = asyncio.Semaphore(
            self._VOTER_DB_CHECK_SEMAPHORE_SIZE
        )
        self._validation_service: ValidationService | None = (
            ValidationService(bot.http_session) if bot.http_session else None
        )
        self._automod_keyword_pattern: re.Pattern[str] | None = None

    async def cog_load(self) -> None:
        if self._validation_service is None and self.bot.http_session:
            self._validation_service = ValidationService(self.bot.http_session)
        self._automod_keyword_pattern = re.compile(
            r"\b(meowcall|stolen|stole)\b", re.IGNORECASE
        )

    async def _recreate_webhook_and_retry(
        self,
        target_channel: discord.TextChannel | discord.Thread,
        source_channel_id: int,
        webhook_params: dict,
    ) -> None:
        new_webhook_url = await create_connection_webhook(target_channel)

        if new_webhook_url is not None:
            try:
                async with self.bot.db.uow() as uow:
                    svc = make_service(uow.session)
                    target_connection = await svc.get_connection(target_channel.id)
                    await svc.ensure_connection(
                        target_channel.id,
                        target_channel.guild.id,
                        new_webhook_url,
                        parent_id=target_connection.parentId
                        if target_connection
                        else None,
                    )
            except PoolTimeout:
                logger.error("DB pool exhausted while updating recreated webhook")
            except Exception as e:
                logger.error(
                    f"Error persisting recreated webhook for channel {target_channel.id}: {e}"
                )

            try:
                if self.bot.http_session:
                    new_webhook = discord.Webhook.from_url(
                        new_webhook_url, session=self.bot.http_session
                    )
                    await send_webhook_with_retry(new_webhook, **webhook_params)
                    logger.debug(
                        f"Relayed userphone message after webhook recreation | to_channel={target_channel.id}"
                    )
            except Exception as retry_e:
                logger.error(
                    f"Error relaying after webhook recreation for channel {target_channel.id}: {retry_e}"
                )
        else:
            logger.warning(
                f"Could not recreate webhook in target channel {target_channel.id}. Ending call."
            )
            result = None
            try:
                async with self.bot.db.uow() as uow:
                    svc = make_service(uow.session)
                    result = await svc.end_call_with_info(source_channel_id)
                    if result and result.was_in_call:
                        await svc.unlink_connections(source_channel_id)
            except PoolTimeout:
                logger.error(
                    "DB pool exhausted while ending call after webhook recreation failure"
                )
            except Exception as e:
                logger.error(f"Error ending call after webhook recreation failure: {e}")

            await redis_delete_call_cache(source_channel_id, target_channel.id)

            if result and result.was_in_call:
                source_channel = self.bot.get_channel(source_channel_id)
                if source_channel:
                    try:
                        await source_channel.send(
                            "⚠️ The other party's webhook was deleted and could not be recreated. The call has ended."
                        )
                    except discord.HTTPException:
                        pass

    async def _send_automod_report(
        self, message: discord.Message, paired_channel_id: int | None
    ) -> None:
        """Send an automod-style report to the reports channel without altering call state."""
        try:
            # Dedupe per message id so we don't spam reports for the same message
            try:
                await redis_client.set(f"automod_reported:{message.id}", "1", ex=3600)
            except Exception:
                # Non-fatal; continue even if Redis isn't available
                pass

            reports_channel = self.bot.get_channel(1508249962335703231)
            if reports_channel is None:
                try:
                    reports_channel = await self.bot.fetch_channel(1508249962335703231)
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    return

            if not isinstance(reports_channel, (discord.TextChannel, discord.Thread)):
                return

            # Gather buffered messages for replay (best-effort)
            channel_ids = [message.channel.id]
            if paired_channel_id:
                channel_ids.append(paired_channel_id)

            buffered = []
            try:
                buffered = await get_buffered_messages_for_channels(channel_ids)
            except Exception:
                buffered = []

            captured_messages = []
            participants = []
            if buffered:
                try:
                    # Reuse the same shaping function as the report command
                    paired_channel = self.bot.get_channel(paired_channel_id) if paired_channel_id else None
                    captured_messages = build_report_replay_messages(
                        buffered, message.channel, paired_channel or message.channel
                    )

                    seen = set()
                    for payload in buffered:
                        aid = str(payload.get("author_id"))
                        if aid not in seen:
                            seen.add(aid)
                            display = payload.get("author_name") or f"User {aid}"
                            guild_name = (
                                message.channel.guild.name
                                if str(payload.get("channel_id")) == str(message.channel.id)
                                else (paired_channel.guild.name if paired_channel else "Unknown")
                            )
                            participants.append(f"{display} (`{aid}`) — {guild_name}")
                except Exception:
                    captured_messages = []

            participants_value = "\n".join(participants) if participants else "No messages captured"

            report_embed = discord.Embed(
                title="⚠️ AUTOMOD: Keyword detected",
                color=discord.Color.red(),
                description=f"**Detected in message:** {message.content or ''}",
                timestamp=discord.utils.utcnow(),
            )
            report_embed.add_field(
                name="Reported by",
                value=f"MeowCall Automod (Bot) (ID: {self.bot.user.id if self.bot.user else 'bot'})",
                inline=False,
            )
            report_embed.add_field(
                name="Source Channel",
                value=f"{message.channel.name} in {message.channel.guild.name}\nChannel ID: `{message.channel.id}` | Guild ID: `{message.channel.guild.id}`",
                inline=False,
            )
            if paired_channel_id:
                target_ch = self.bot.get_channel(paired_channel_id)
                if target_ch:
                    report_embed.add_field(
                        name="Connected Channel",
                        value=f"{target_ch.name} in {target_ch.guild.name}\nChannel ID: `{target_ch.id}` | Guild ID: `{target_ch.guild.id}`",
                        inline=False,
                    )

            report_embed.add_field(
                name=f"Participants ({len(participants)})",
                value=participants_value[:1000],
                inline=False,
            )

            action_view = ReportActionView(
                captured_messages=captured_messages if captured_messages else [],
                source_label=f"{message.channel.name} ({message.channel.guild.name})",
                target_label=(f"{target_ch.name} ({target_ch.guild.name})" if paired_channel_id and (target_ch := self.bot.get_channel(paired_channel_id)) else "Connected Channel"),
            )

            try:
                await reports_channel.send(embed=report_embed, view=action_view)
                logger.info(f"Automod report posted for message {message.id}")
            except Exception as e:
                logger.error(f"Failed to send automod report: {e}")
        except Exception as e:
            logger.error(f"Unexpected automod report error: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Relay messages between paired userphone channels with image support."""
        if not message or message.webhook_id or message.author.bot or not message.guild:
            return
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid or message.content.startswith(("/", "!")):
            return

        paired_channel_id: int | None = None
        target_webhook_url: str | None = None

        _cached = await _redis_get_with_retry(
            redis_get_call_state, message.channel.id
        )
        if _cached is None:
            cached_active = cached_paired = None
        else:
            cached_active, cached_paired = _cached

        if cached_active and cached_paired:
            paired_channel_id = int(cached_paired.get("channelId", 0)) or None

            if paired_channel_id:
                target_webhook_url = await _redis_get_with_retry(
                    redis_get_webhook, paired_channel_id
                )

            is_valid, error_reason = await check_bans_and_validation(
                message,
                None,
                self._cache_manager,
                self._validation_service,
                self.bot,
            )
            if not is_valid:
                logger.debug(
                    f"Userphone message rejected: {error_reason} | user={message.author.id}"
                )
                return

            try:
                await redis_refresh_call_cache(message.channel.id)
            except MaxConnectionsError:
                logger.warning(
                    f"Redis pool exhausted refreshing call cache for {message.channel.id} — skipping refresh"
                )
            except Exception as e:
                logger.error(f"Unexpected error refreshing call cache: {e}")

            if target_webhook_url is None and paired_channel_id:
                target_channel_tmp = self.bot.get_channel(paired_channel_id)
                if isinstance(
                    target_channel_tmp, (discord.TextChannel, discord.Thread)
                ):
                    try:
                        async with self.bot.db.uow() as uow_wh:
                            svc = make_service(uow_wh.session)
                            target_webhook_url = await ensure_connection_webhook(
                                svc, target_channel_tmp
                            )
                    except PoolTimeout:
                        logger.error(
                            "DB pool exhausted resolving webhook on cache-hit path"
                        )
        else:
            # Cache-miss path - optimize to minimize connection holding time
            try:
                cache_state = await self._cache_manager.get_multiple(
                    [
                        (
                            "connection",
                            str(message.channel.id),
                            "inactive_call",
                        ),
                        (
                            "connection",
                            str(message.channel.id),
                            "lookup_throttled",
                        ),
                    ]
                )

                inactive_call_cached = cache_state.get(
                    f"connection:{message.channel.id}:inactive_call"
                )
                if inactive_call_cached and inactive_call_cached.get("inactive"):
                    return

                lookup_throttled_cached = cache_state.get(
                    f"connection:{message.channel.id}:lookup_throttled"
                )
                if lookup_throttled_cached and lookup_throttled_cached.get(
                    "throttled"
                ):
                    return

                # Check cache first for validation result
                cached_validation = await self._cache_manager.get_user_validation(
                    message.author.id, message.guild.id
                )
                if cached_validation is not None:
                    is_valid = cached_validation.get("valid", False)
                    error_reason = cached_validation.get("reason")
                    if not is_valid:
                        logger.debug(
                            f"Userphone message rejected (cached): {error_reason} | user={message.author.id}"
                        )
                        return
                else:
                    # Run validation without DB UoW first
                    is_valid, error_reason = await check_bans_and_validation(
                        message,
                        None,  # No session for first pass
                        self._cache_manager,
                        self._validation_service,
                        self.bot,
                    )
                    if not is_valid:
                        logger.debug(
                            f"Userphone message rejected: {error_reason} | user={message.author.id}"
                        )
                        # Cache the validation failure
                        await self._cache_manager.set_user_validation(
                            message.author.id, message.guild.id, False, error_reason
                        )
                        return
                    # Cache the validation success
                    await self._cache_manager.set_user_validation(
                        message.author.id, message.guild.id, True
                    )

                # Minimal DB UoW - only fetch call data
                try:
                    try:
                        await asyncio.wait_for(
                            self._db_read_semaphore.acquire(),
                            timeout=self._DB_READ_SEMAPHORE_TIMEOUT,
                        )
                    except TimeoutError:
                        logger.warning(
                            "on_message DB read path saturated; skipping relay lookup to protect pool"
                        )
                        await self._cache_manager.set(
                            "connection",
                            str(message.channel.id),
                            "lookup_throttled",
                            value={"throttled": True},
                            ttl=self._LOOKUP_THROTTLE_CACHE_TTL,
                        )
                        return

                    try:
                        async with self.bot.db.uow() as uow_read:
                            svc = make_service(uow_read.session)
                            call = await svc.get_active_call_for_channel(
                                str(message.channel.id)
                            )
                            if call is None:
                                await self._cache_manager.set(
                                    "connection",
                                    str(message.channel.id),
                                    "inactive_call",
                                    value={"inactive": True},
                                    ttl=self._INACTIVE_CALL_CACHE_TTL,
                                )
                                return

                            paired_call = await svc.get_paired_call(call)
                            if paired_call is None:
                                await self._cache_manager.set(
                                    "connection",
                                    str(message.channel.id),
                                    "inactive_call",
                                    value={"inactive": True},
                                    ttl=self._INACTIVE_CALL_CACHE_TTL,
                                )
                                return

                            paired_channel_id = int(paired_call.channelId)

                            # Batch set cache operations while in UoW
                            cache_ops = [
                                (
                                    redis_set_active_call,
                                    (
                                        message.channel.id,
                                        {
                                            "channelId": str(message.channel.id),
                                            "id": str(call.id),
                                        },
                                    ),
                                ),
                                (
                                    redis_set_paired_call,
                                    (
                                        message.channel.id,
                                        {
                                            "channelId": str(paired_call.channelId),
                                            "id": str(paired_call.id),
                                        },
                                    ),
                                ),
                            ]

                            target_channel_tmp = self.bot.get_channel(paired_channel_id)
                            if isinstance(
                                target_channel_tmp, (discord.TextChannel, discord.Thread)
                            ):
                                target_webhook_url = await ensure_connection_webhook(
                                    svc, target_channel_tmp
                                )
                            else:
                                target_webhook_url = None
                    finally:
                        self._db_read_semaphore.release()
                except PoolTimeout:
                    logger.error("DB pool exhausted during on_message read UoW")
                    return

                # Cache writes outside of UoW to avoid holding connection
                for coro_fn, coro_args in cache_ops:
                    try:
                        await coro_fn(*coro_args)
                    except MaxConnectionsError:
                        logger.warning(
                            f"Redis pool exhausted writing call cache ({coro_fn.__name__}) "
                            f"for channel {message.channel.id} — continuing without cache"
                        )
                    except Exception as e:
                        logger.error(
                            f"Unexpected Redis error in {coro_fn.__name__}: {e}"
                        )
                        
            except Exception as e:
                logger.error(f"Unexpected error in on_message cache-miss path: {e}")
                return

        if paired_channel_id is None:
            return

        if paired_channel_id == message.channel.id:
            logger.warning(
                f"on_message: paired_channel_id == source channel {message.channel.id} — "
                f"refusing relay to prevent loop. Purging stale call cache."
            )
            await redis_delete_call_cache(message.channel.id)
            return

        target_channel = self.bot.get_channel(paired_channel_id)
        if target_channel is None:
            try:
                target_channel = await self.bot.fetch_channel(paired_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            return

        if target_webhook_url is None:
            target_webhook_url = await _redis_get_with_retry(
                redis_get_webhook, target_channel.id
            )

        if target_webhook_url is None:
            return

        has_images = bool(
            message.attachments
            or (message.content and Patterns.IMAGE_URL_MARKER.search(message.content))
            or (message.content and Patterns.GIF_URL_MARKER.search(message.content))
        )

        is_voter = await self._cache_manager.is_voter(message.author.id)
        if not is_voter:
            try:
                topgg_key_exists = await redis_client.exists(
                    f"topgg:voters:{message.author.id}"
                )
                if topgg_key_exists:
                    is_voter = True
                    await self._cache_manager.set_voter_state(message.author.id, True)
            except Exception:
                pass
        if not is_voter:
            try:
                try:
                    await asyncio.wait_for(
                        self._voter_db_check_semaphore.acquire(),
                        timeout=self._VOTER_DB_CHECK_TIMEOUT,
                    )
                except TimeoutError:
                    logger.debug(
                        "Skipping voter badge DB check due to load for user %s",
                        message.author.id,
                    )
                else:
                    try:
                        async with self.bot.db.uow() as uow:
                            user_repo = UserRepository(uow.session)
                            is_voter = await user_repo.has_badge(
                                str(message.author.id), Badges.VOTER
                            )
                            if is_voter:
                                await self._cache_manager.set_voter_state(
                                    message.author.id, True
                                )
                    finally:
                        self._voter_db_check_semaphore.release()
            except Exception as e:
                logger.error(f"Error checking voter badge for {message.author.id}: {e}")
                is_voter = False

            # Cache negative result to avoid repeated DB checks on every message.
            # Only cache when the DB check completed without raising an exception.
            try:
                if not is_voter:
                    await self._cache_manager.set_voter_state(message.author.id, False)
            except Exception:
                # Don't let cache failures affect message relay.
                pass

        if has_images and not is_voter:
            warned = await _redis_get_with_retry(redis_is_warned, message.channel.id)
            if not warned:
                try:
                    await message.channel.send(
                        f"⚠️ {message.author.mention}, only voters can send images or gifs in userphone. "
                        f"Vote on **[top.gg](https://top.gg/bot/1355389597818945639/vote)** to unlock!",
                        delete_after=10,
                    )
                    try:
                        await redis_set_warned(message.channel.id)
                    except MaxConnectionsError:
                        logger.warning(
                            f"Redis pool exhausted setting warned state for {message.channel.id}"
                        )
                except discord.HTTPException:
                    pass
            return

        async def send_warning(reason: str):
            warned = await _redis_get_with_retry(redis_is_warned, message.channel.id)
            if not warned:
                try:
                    await message.channel.send(
                        f"⚠️ {message.author.mention}, your message was blocked: **{reason}**",
                        delete_after=10,
                    )
                    try:
                        await redis_set_warned(message.channel.id)
                    except MaxConnectionsError:
                        logger.warning(
                            f"Redis pool exhausted setting warned state for {message.channel.id}"
                        )
                except discord.HTTPException:
                    pass

        if self.bot.http_session is None:
            return

        validation_service = self._validation_service
        if validation_service is None:
            self._validation_service = ValidationService(self.bot.http_session)
            validation_service = self._validation_service

        validation_result = await validation_service.validate_message(
            message, is_voter=is_voter
        )
        if not validation_result.valid:
            await send_warning(validation_result.reason)
            return

        reply_content = ""
        reply_embed = None
        if message.reference and message.reference.message_id:
            try:
                if message.reference.cached_message:
                    ref_msg = message.reference.cached_message
                else:
                    ref_msg = await message.channel.fetch_message(
                        message.reference.message_id
                    )

                ref_validation = await validation_service.validate_message(ref_msg)
                if not ref_validation.valid:
                    reply_content = f"> **{ref_msg.author.display_name}**: [Content removed by filter]\n"
                else:
                    ref_text = (ref_msg.content or "")[:250]
                    reply_embed = discord.Embed(
                        description=ref_text,
                        color=discord.Color.light_grey(),
                    )
                    ref_name = _sanitize_username(ref_msg.author.display_name)
                    reply_embed.set_author(
                        name=f"Replying to {ref_name}",
                        icon_url=str(ref_msg.author.display_avatar.url),
                    )
                    reply_content = ""
            except (discord.NotFound, discord.HTTPException):
                reply_content = "> *Original message deleted*\n"

        content = (message.content or "").strip()
        if reply_content:
            content = f"{reply_content}{content}"

        webhook_params = {
            "content": content or None,
            "username": _sanitize_username(message.author.display_name),
            "avatar_url": str(message.author.display_avatar.url),
            "allowed_mentions": discord.AllowedMentions.none(),
        }

        if reply_embed:
            webhook_params["embeds"] = [reply_embed]

        if message.attachments:
            attachment_urls = "\n".join(
                attachment.url for attachment in message.attachments
            )
            if content:
                webhook_params["content"] = (
                    f"{webhook_params.get('content', '')}\n{attachment_urls}"
                )
            else:
                webhook_params["content"] = attachment_urls

        webhook_params = {k: v for k, v in webhook_params.items() if v is not None}

        if not webhook_params.get("content"):
            return

        referred_message_id = None
        if message.reference and message.reference.message_id:
            referred_message_id = str(message.reference.message_id)

        _MAX_RELAY_ATTEMPTS = 3
        _RETRY_BACKOFF = (0.0, 1.0, 2.0)

        relay_succeeded = False
        for attempt in range(_MAX_RELAY_ATTEMPTS):
            try:
                if _RETRY_BACKOFF[attempt]:
                    await asyncio.sleep(_RETRY_BACKOFF[attempt])
                webhook = discord.Webhook.from_url(
                    target_webhook_url, session=self.bot.http_session
                )
                await send_webhook_with_retry(webhook, **webhook_params)
                relay_succeeded = True
                break
            except discord.HTTPException as e:
                if getattr(e, "code", None) == 10015:  # Unknown Webhook
                    await redis_delete_webhook(target_channel.id)
                    task = asyncio.create_task(
                        self._recreate_webhook_and_retry(
                            target_channel=target_channel,
                            source_channel_id=message.channel.id,
                            webhook_params=webhook_params,
                        )
                    )
                    task.add_done_callback(
                        lambda t: t.exception() if not t.cancelled() else None
                    )
                    return
                elif e.status == 429:  # Rate limited
                    retry_after = float(
                        getattr(e, "retry_after", None) or 2.0 * (attempt + 1)
                    )
                    logger.warning(
                        f"Webhook rate limited for channel {target_channel.id}, "
                        f"retrying in {retry_after:.1f}s (attempt {attempt + 1}/{_MAX_RELAY_ATTEMPTS})"
                    )
                    if attempt < _MAX_RELAY_ATTEMPTS - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    logger.error(
                        f"Webhook rate limit exceeded after {_MAX_RELAY_ATTEMPTS} attempts for "
                        f"channel {target_channel.id}, dropping message."
                    )
                    return
                else:
                    logger.error(f"Error relaying userphone message: {e}")
                    return
            except Exception as e:
                logger.error(f"Error relaying userphone message: {e}")
                return

        if not relay_succeeded:
            return

        try:
            # Buffer message for later bulk flush — no DB session required here.
            await save_message_to_db(
                message, None, referred_message_id=referred_message_id
            )
        except Exception as e:
            logger.error(f"Error buffering relayed userphone message: {e}")
        else:
            # Automod trigger: detect keywords and schedule a report task (non-blocking)
            try:
                pattern = self._automod_keyword_pattern
                if pattern is not None and pattern.search(message.content or ""):
                    try:
                        already = await redis_client.exists(f"automod_reported:{message.id}")
                    except Exception:
                        already = False
                    if not already:
                        asyncio.create_task(self._send_automod_report(message, paired_channel_id))
            except Exception as e:
                logger.error(f"Automod scheduling error: {e}")


async def setup(bot: Bot):
    await bot.add_cog(OnMessage(bot))
