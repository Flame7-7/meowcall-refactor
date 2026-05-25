from __future__ import annotations

import asyncio
import datetime
import logging
import random
import re
import unicodedata
from collections import deque

import discord
from cachetools import TTLCache

from utils.runtime.constants import MOD_ROLE_NAMES, TRUSTED_DOMAINS, banned_words_regex

# Matches bare and full Discord invite links, including common shortlink services.
DISCORD_INVITE_REGEX = re.compile(
    r"(?:discord(?:\.gg|app\.com/invite|\.com/invite)|dsc\.gg|discord\.io|invite\.gg)"
    r"[/\\]+[a-zA-Z0-9\-]+",
    re.IGNORECASE,
)


def _strip_invisible(text: str) -> str:
    """Remove zero-width and invisible Unicode characters used to bypass filters."""
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def is_mod(member: discord.Member) -> bool:
    if not member or not member.guild:
        return False
    return (
        any(role.name in MOD_ROLE_NAMES for role in member.roles)
        or member.guild_permissions.administrator
    )


async def delete_message_safe(message) -> None:
    try:
        await message.delete()
    except discord.Forbidden:
        pass
    except discord.NotFound:
        pass


def check_banned_words(message) -> bool:
    return banned_words_regex.search(message.content.lower()) is not None


def check_disallowed_links(content: str) -> bool:
    clean = _strip_invisible(content)
    if DISCORD_INVITE_REGEX.search(clean):
        return True
    clean_lower = clean.lower()
    if any(trigger in clean_lower for trigger in ["http://", "https://", "www."]):
        return not any(domain in clean_lower for domain in TRUSTED_DOMAINS)
    return False


logger = logging.getLogger(__name__)
webhook_cache = TTLCache(maxsize=75, ttl=1800)
webhook_warning_cooldown = TTLCache(maxsize=200, ttl=300)


async def get_or_create_webhook(channel):
    try:
        if channel is None:
            return None

        cached = webhook_cache.get(channel.id)
        if cached and cached.token:
            return cached

        if not channel.permissions_for(channel.guild.me).manage_webhooks:
            return None

        webhooks = await channel.webhooks()
        webhook = next(
            (wh for wh in webhooks if wh.name == "MeowCall-Webhook" and wh.token), None
        )

        if not webhook:
            # Delete any stale MeowCall webhooks without tokens
            for wh in webhooks:
                if wh.name == "MeowCall-Webhook" and not wh.token:
                    try:
                        await wh.delete(reason="Stale webhook without token")
                    except Exception:
                        pass
            webhook = await channel.create_webhook(
                name="MeowCall-Webhook", reason="Created for MeowCall"
            )

        webhook_cache[channel.id] = webhook
        return webhook
    except Exception as e:
        logger.debug(
            "Failed to get/create webhook for channel %s: %s",
            getattr(channel, "id", None),
            e,
        )
        return None


async def send_webhook_with_retry(webhook, **kwargs):
    # Discord rejects payloads with no content/embeds/files.
    has_renderable_payload = any(
        kwargs.get(k)
        for k in ("content", "embed", "embeds", "file", "files", "view", "poll")
    )
    if not has_renderable_payload:
        logger.debug(
            "Skipped webhook send with empty payload for webhook %s",
            getattr(webhook, "id", None),
        )
        return None

    kwargs["wait"] = True
    last_exc = None
    for attempt in range(3):
        try:
            return await webhook.send(**kwargs)
        except ValueError:
            # "This webhook does not have a token" — evict from cache and bail
            webhook_cache.pop(getattr(webhook, "channel_id", None), None)
            raise
        except discord.DiscordServerError as e:
            last_exc = e
            if attempt < 2:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            raise
        except discord.HTTPException as e:
            last_exc = e
            if e.status == 429:
                wait_time = getattr(e, "retry_after", 5)
                await asyncio.sleep(wait_time)
                continue
            if e.status >= 500 and attempt < 2:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            raise
    if last_exc:
        raise last_exc


async def show_random_tip(channel):

    from utils.runtime.constants import TIPS

    if random.random() < 0.99:
        try:
            await channel.send(random.choice(TIPS))
        except Exception:
            logger.debug("Failed to send random tip in channel %s", getattr(channel, "id", None), exc_info=True)


async def record_warning(user_id, reason, channel_id, guild_id):
    pass


def parse_duration(duration_str: str):
    if not duration_str:
        return None
    pattern = re.match(r"^(\d+)\s*(mo|[smhdwy])$", duration_str.strip().lower())
    if not pattern:
        return None
    value, unit = int(pattern.group(1)), pattern.group(2)
    return {
        "s": datetime.timedelta(seconds=value),
        "m": datetime.timedelta(minutes=value),
        "h": datetime.timedelta(hours=value),
        "d": datetime.timedelta(days=value),
        "w": datetime.timedelta(weeks=value),
        "mo": datetime.timedelta(days=value * 30),
        "y": datetime.timedelta(days=value * 365),
    }.get(unit)


def parse_duration_ms(duration_str: str) -> int | None:
    """Parse a human duration string (e.g. '1h', '2d', '3w') into milliseconds.

    Returns None if the string is empty or cannot be parsed.
    """
    td = parse_duration(duration_str)
    if td is None:
        return None
    return int(td.total_seconds() * 1000)


def format_expiry(expires_at_iso: str | None) -> str:
    if not expires_at_iso:
        return "Permanent"
    try:
        dt = datetime.datetime.fromisoformat(expires_at_iso)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "Unknown"


recent_pairings = deque(maxlen=50)


def is_recent_pairing(guild_id_a: int, guild_id_b: int) -> bool:
    pair = (min(guild_id_a, guild_id_b), max(guild_id_a, guild_id_b))
    return pair in recent_pairings


def record_pairing(guild_id_a: int, guild_id_b: int) -> None:
    pair = (min(guild_id_a, guild_id_b), max(guild_id_a, guild_id_b))
    if pair not in recent_pairings:
        recent_pairings.append(pair)


async def validate_channel(channel) -> bool:
    if not channel:
        return False
    return channel.permissions_for(channel.guild.me).send_messages


waiting_queue = []
waiting_queue_lock = asyncio.Lock()
