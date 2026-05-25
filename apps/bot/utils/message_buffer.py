"""In-memory message buffering for batching DB inserts during calls.

Buffers are keyed by channel id. Call sites should `buffer_message_for_channel`
as messages arrive and ensure `flush_channel_messages` is invoked when the
call ends (or periodically) to persist messages in a single DB statement.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from repositories.messageRepository import MessageRepository
from repositories.userRepository import UserRepository


# Simple in-memory buffers. Keys are channel id strings.
_buffers: dict[str, list[dict]] = {}
# Track per-channel author counts: channel_id -> {author_id: count}
_author_counts: dict[str, dict[str, int]] = {}
# Protect concurrent access to buffers
_lock = asyncio.Lock()


async def buffer_message_for_channel(channel_id: int, payload: dict[str, Any]) -> None:
    """Append a message payload to the channel buffer.

    *payload* is a dict with keys matching those used by
    :meth:`MessageRepository.insert_pending_message_if_new`.
    """
    key = str(channel_id)
    async with _lock:
        _buffers.setdefault(key, []).append(payload)
        authors = _author_counts.setdefault(key, {})
        aid = str(payload.get("author_id"))
        authors[aid] = authors.get(aid, 0) + 1


async def get_buffered_messages_for_channels(
    channel_ids: Iterable[int | str],
) -> list[dict[str, Any]]:
    """Return a chronological snapshot of buffered messages for *channel_ids*.

    The returned payloads are shallow copies so callers can safely enrich or
    reshape them for report replay without mutating the live buffer.
    """
    keys = {str(channel_id) for channel_id in channel_ids}
    async with _lock:
        messages = [
            dict(message)
            for channel_key in keys
            for message in _buffers.get(channel_key, [])
        ]

    messages.sort(key=lambda payload: str(payload.get("timestamp") or ""))
    return messages


def build_report_replay_messages(
    buffered_messages: list[dict[str, Any]],
    source_channel: Any,
    target_channel: Any,
) -> list[dict[str, Any]]:
    """Shape buffered relay payloads into the report replay format."""
    source_label = f"{source_channel.name} ({source_channel.guild.name})"
    target_label = f"{target_channel.name} ({target_channel.guild.name})"

    messages_by_id = {
        str(message.get("id")): message for message in buffered_messages if message.get("id")
    }
    captured_messages: list[dict[str, Any]] = []

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


async def flush_channel_messages(session, channel_id: int) -> int:
    """Persist buffered messages for *channel_id* using *session*.

    Returns the number of messages inserted.
    """
    key = str(channel_id)
    async with _lock:
        messages = _buffers.pop(key, [])
        author_counts = _author_counts.pop(key, {})

    if not messages:
        return 0

    # Ensure referredMessageId existence: query existing referred ids
    referred_ids = [
        str(m["referred_message_id"]) for m in messages if m.get("referred_message_id")
    ]
    existing_referred = set()
    if referred_ids:
        try:
            # Lazy import here to avoid top-level DB model import cycles
            from models import Message
            from sqlalchemy import select as _select

            result = await session.execute(_select(Message.id).where(Message.id.in_(referred_ids)))
            existing_referred = {r[0] for r in result if r[0]}
        except Exception:
            existing_referred = set()

    # Sanitize payloads: if referred id isn't present in DB, set to None
    sanitized = []
    for m in messages:
        referred = m.get("referred_message_id")
        if referred is not None and str(referred) not in existing_referred:
            m["referred_message_id"] = None
        sanitized.append(m)

    # Bulk insert messages
    msg_repo = MessageRepository(session)
    inserted = await msg_repo.bulk_create_messages(sanitized)

    # Bulk increment user message counts by collected amounts
    if author_counts:
        user_repo = UserRepository(session)
        await user_repo.bulk_increment_message_counts(author_counts)

    # Ensure users exist for these author ids (insert-on-conflict-do-nothing)
    try:
        from models import User
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        user_ids = list({str(m.get("author_id")) for m in messages if m.get("author_id")})
        if user_ids:
            payloads = [{"id": uid} for uid in user_ids]
            await session.execute(pg_insert(User).values(payloads).on_conflict_do_nothing(index_elements=["id"]))
            await session.flush()
    except Exception:
        # Don't fail the whole flush if user upsert fails; counts/messages were already attempted
        pass

    return inserted
