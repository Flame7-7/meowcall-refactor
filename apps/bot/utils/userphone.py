from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from models import MessageStatus

from repositories.connectionRepository import ConnectionRepository
from repositories.moderationRepository import ModerationRepository
from services.userphone.userphoneService import UserphoneService
from utils import logger, redis_client
from utils.helpers import get_or_create_webhook
from utils.message_buffer import buffer_message_for_channel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from core.bot import Bot
    from services.userphone.validationService import ValidationService
    from utils.redis.cache import CacheManager


@dataclass
class ValidationCtx:
    author: discord.Member | discord.User
    guild: discord.Guild


_CALL_CACHE_TTL = 600

# Semaphore to prevent Redis connection pool exhaustion during startup bursts
# and other high-concurrency moments. Caps concurrent Redis ops to 20.
_redis_semaphore = asyncio.Semaphore(20)


async def redis_set_waiting_msg(channel_id: int, msg_id: int) -> None:
    try:
        await redis_client.set(f"waiting_msg:{channel_id}", str(msg_id), ex=300)
    except Exception as e:
        logger.error(f"Redis error setting waiting_msg:{channel_id}: {e}")


async def redis_get_waiting_msg(channel_id: int) -> str | None:
    try:
        return await redis_client.get(f"waiting_msg:{channel_id}")
    except Exception as e:
        logger.error(f"Redis error getting waiting_msg:{channel_id}: {e}")
        return None


async def redis_delete_waiting_msg(channel_id: int) -> None:
    try:
        await redis_client.delete(f"waiting_msg:{channel_id}")
    except Exception as e:
        logger.error(f"Redis error deleting waiting_msg:{channel_id}: {e}")


async def redis_set_warned(channel_id: int) -> None:
    try:
        await redis_client.set(f"warned:{channel_id}", "1", ex=30)
    except Exception as e:
        logger.error(f"Redis error setting warned:{channel_id}: {e}")


async def redis_is_warned(channel_id: int) -> bool:
    try:
        return bool(await redis_client.exists(f"warned:{channel_id}"))
    except Exception as e:
        logger.error(f"Redis error checking warned:{channel_id}: {e}")
        return False


async def redis_clear_warned(channel_id: int) -> None:
    try:
        await redis_client.delete(f"warned:{channel_id}")
    except Exception as e:
        logger.error(f"Redis error clearing warned:{channel_id}: {e}")


# ---------------------------------------------------------------------------
# Report helpers — keyed by call ID so keys are scoped to a single call
# session and can never bleed across calls or expire mid-session.
# ---------------------------------------------------------------------------


async def redis_set_reported_by_key(key: str) -> None:
    try:
        await redis_client.set(f"reported:{key}", "1", ex=3600)
    except Exception as e:
        logger.error(f"Redis error setting reported key {key}: {e}")


async def redis_is_reported_by_key(key: str) -> bool:
    try:
        return bool(await redis_client.exists(f"reported:{key}"))
    except Exception as e:
        logger.error(f"Redis error checking reported key {key}: {e}")
        return False


async def redis_get_webhook(channel_id: int) -> str | None:
    # Gated by semaphore — hot path called by every shard on startup
    async with _redis_semaphore:
        try:
            return await redis_client.get(f"webhook:{channel_id}")
        except Exception as e:
            logger.error(f"Redis error getting webhook:{channel_id}: {e}")
            return None


async def redis_set_webhook(channel_id: int, url: str) -> None:
    try:
        await redis_client.set(f"webhook:{channel_id}", url, ex=3600)
    except Exception as e:
        logger.error(f"Redis error setting webhook:{channel_id}: {e}")


async def redis_delete_webhook(channel_id: int) -> None:
    try:
        await redis_client.delete(f"webhook:{channel_id}")
    except Exception as e:
        logger.error(f"Redis error deleting webhook:{channel_id}: {e}")


async def redis_get_active_call(channel_id: int) -> dict | None:
    # Gated by semaphore — called for every channel on shard ready, causing the
    # "Too many connections" burst seen in logs when all shards come online at once.
    async with _redis_semaphore:
        try:
            raw = await redis_client.get(f"call:active:{channel_id}")
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.error(f"Redis error getting call:active:{channel_id}: {e}")
            return None


async def redis_get_call_state(channel_id: int) -> tuple[dict | None, dict | None]:
    # Batch the active and paired reads for the hottest relay path.
    async with _redis_semaphore:
        try:
            active_key = f"call:active:{channel_id}"
            paired_key = f"call:paired:{channel_id}"
            active_raw, paired_raw = await redis_client.mget(active_key, paired_key)
            active_call = json.loads(active_raw) if active_raw else None
            paired_call = json.loads(paired_raw) if paired_raw else None
            return active_call, paired_call
        except Exception as e:
            logger.error(f"Redis error getting call state for {channel_id}: {e}")
            return None, None


async def redis_set_active_call(channel_id: int, call_data: dict) -> None:
    try:
        await redis_client.set(
            f"call:active:{channel_id}", json.dumps(call_data), ex=_CALL_CACHE_TTL
        )
    except Exception as e:
        logger.error(f"Redis error setting call:active:{channel_id}: {e}")


async def redis_get_paired_call(channel_id: int) -> dict | None:
    # Gated by semaphore — called alongside redis_get_active_call on every message
    async with _redis_semaphore:
        try:
            raw = await redis_client.get(f"call:paired:{channel_id}")
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.error(f"Redis error getting call:paired:{channel_id}: {e}")
            return None


async def redis_set_paired_call(channel_id: int, call_data: dict) -> None:
    try:
        await redis_client.set(
            f"call:paired:{channel_id}", json.dumps(call_data), ex=_CALL_CACHE_TTL
        )
    except Exception as e:
        logger.error(f"Redis error setting call:paired:{channel_id}: {e}")


async def redis_refresh_call_cache(channel_id: int) -> None:
    try:
        async with redis_client.pipeline(transaction=False) as pipe:
            pipe.expire(f"call:active:{channel_id}", _CALL_CACHE_TTL)
            pipe.expire(f"call:paired:{channel_id}", _CALL_CACHE_TTL)
            await pipe.execute()
    except Exception as e:
        logger.error(f"Redis error refreshing call cache for {channel_id}: {e}")


async def redis_delete_call_cache(*channel_ids: int) -> None:
    try:
        keys = []
        for cid in channel_ids:
            keys += [f"call:active:{cid}", f"call:paired:{cid}"]
        if keys:
            await redis_client.delete(*keys)
    except Exception as e:
        logger.error(f"Redis error deleting call cache for {channel_ids}: {e}")


def make_service(session: AsyncSession) -> UserphoneService:
    from repositories.userphoneRepository import UserphoneRepository

    return UserphoneService(UserphoneRepository(session), ConnectionRepository(session))


async def ensure_connection_webhook(
    service: UserphoneService,
    channel: discord.TextChannel | discord.Thread,
    force_refresh: bool = False,
) -> str | None:
    if not force_refresh:
        cached = await redis_get_webhook(channel.id)
        if cached:
            return cached
    connection = await service.get_connection(channel.id)
    if connection and connection.webhookURL:
        await redis_set_webhook(channel.id, connection.webhookURL)
        return connection.webhookURL
    return None


async def create_connection_webhook(
    channel: discord.TextChannel | discord.Thread,
) -> str | None:
    webhook = await get_or_create_webhook(channel)
    if webhook is None or webhook.url is None:
        return None
    url = str(webhook.url)
    await redis_set_webhook(channel.id, url)
    return url


async def resolve_webhook_for_channel(
    channel: discord.TextChannel | discord.Thread,
    service: UserphoneService | None = None,
) -> str | None:
    url = await redis_get_webhook(channel.id)
    if url:
        return url
    if service is not None:
        url = await ensure_connection_webhook(service, channel)
        if url:
            return url
    return await create_connection_webhook(channel)


async def check_validation_only(
    ctx: ValidationCtx | discord.Message,
    cache_manager: CacheManager,
    validation_service: ValidationService | None,
    check_username: bool = True,
    check_guild_name: bool = True,
) -> tuple[bool, str | None]:
    if isinstance(ctx, discord.Message):
        author = ctx.author
        guild = ctx.guild
    else:
        author = ctx.author
        guild = ctx.guild

    if check_username and validation_service:
        cached_validations = await cache_manager.get_multiple(
            [
                ("validation", str(author.id), str(guild.id)),
                ("guild_data", str(guild.id), "validation"),
            ]
        )
        cached_user_validation = cached_validations.get(
            f"validation:{author.id}:{guild.id}"
        )
        if not cached_user_validation:
            user_validation = validation_service.validate_username(author)
            if not user_validation.valid:
                # Do not cache failures so the user can immediately retry if they update their name
                return False, user_validation.reason
            await cache_manager.set(
                "user_data",
                str(author.id),
                str(guild.id),
                "validation",
                value={"valid": True},
                ttl=cache_manager.LONG_TTL,
            )

        cached_guild_validation = cached_validations.get(
            f"guild_data:{guild.id}:validation"
        )
    else:
        cached_guild_validation = None

    if check_guild_name and validation_service:
        if not cached_guild_validation:
            guild_validation = validation_service.validate_forbidden_guild_name(guild)
            if not guild_validation.valid:
                # Do not cache failures so the guild can immediately retry if they update their name
                return False, guild_validation.reason
            await cache_manager.set(
                "guild_data",
                str(guild.id),
                "validation",
                value={"valid": True},
                ttl=cache_manager.LONG_TTL,
            )

    return True, None


async def check_bans_and_validation(
    ctx: ValidationCtx | discord.Message,
    session: AsyncSession | None,
    cache_manager: CacheManager,
    validation_service: ValidationService | None,
    bot: Bot,
    check_username: bool = True,
    check_guild_name: bool = True,
) -> tuple[bool, str | None]:
    is_valid, reason = await check_validation_only(
        ctx, cache_manager, validation_service, check_username, check_guild_name
    )
    if not is_valid:
        return is_valid, reason

    if isinstance(ctx, discord.Message):
        author = ctx.author
        guild = ctx.guild
    else:
        author = ctx.author
        guild = ctx.guild

    cached_access_restriction = await cache_manager.get(
        "user_data", str(author.id), str(guild.id), "access_restriction"
    )
    if cached_access_restriction is None:
        if session is not None:
            moderation_repo = ModerationRepository(session)
            has_access_restriction = await moderation_repo.has_any_access_restriction(
                author.id, guild.id
            )
            await cache_manager.set(
                "user_data",
                str(author.id),
                str(guild.id),
                "access_restriction",
                value={"restricted": has_access_restriction},
                ttl=cache_manager.MEDIUM_TTL,
            )
        else:
            has_access_restriction = False
            try:
                await cache_manager.set(
                    "user_data",
                    str(author.id),
                    str(guild.id),
                    "access_restriction",
                    value={"restricted": False},
                    ttl=cache_manager.MEDIUM_TTL,
                )
            except Exception:
                pass
    else:
        has_access_restriction = cached_access_restriction.get("restricted", False)

    if has_access_restriction:
        return False, "Your account or server has been restricted from using userphone."

    return True, None


async def save_message_to_db(
    message: discord.Message,
    session: AsyncSession | None = None,
    referred_message_id: str | None = None,
) -> bool:
    try:
        # Buffer the message for later bulk insertion. The flush will ensure
        # users exist and increment counts in bulk as well.
        images_url = None
        if message.attachments:
            images_url = [
                attachment.url
                for attachment in message.attachments
                if (attachment.content_type or "").startswith("image/")
            ]

        payload = {
            "id": str(message.id),
            "author_name": message.author.name,
            "author_avatar": str(message.author.display_avatar.url)
            if getattr(message.author, "display_avatar", None)
            else None,
            "content": message.content or "",
            "images_url": images_url,
            "channel_id": str(message.channel.id),
            "guild_id": str(message.guild.id),
            "author_id": str(message.author.id),
            "referred_message_id": referred_message_id,
            "status": MessageStatus.ACTIVE,
            "retention_until": None,
            "timestamp": (
                message.created_at.astimezone(UTC).isoformat()
                if message.created_at is not None
                else datetime.now(UTC).isoformat()
            ),
        }
        # This function buffers the message in-memory; persisting is handled
        # later by `flush_channel_messages(session, channel_id)` which will be
        # invoked when the call ends. The optional *session* parameter is kept
        # for API compatibility but is not required by the buffering path.
        await buffer_message_for_channel(message.channel.id, payload)
        return True
    except Exception as e:
        logger.error(f"Error buffering userphone message: {e}")
        return False