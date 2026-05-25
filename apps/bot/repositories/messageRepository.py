from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Unpack

from models import Message, MessageReaction, MessageStatus, Report, User
from sqlalchemy import and_, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from ._types import MessageCreateKwargs

from .baseRepository import BaseRepository


class MessageRepository(BaseRepository):
    """Repository for :class:`Message` queries"""

    # Single-row lookups

    async def get_by_id(self, message_id: str | int) -> Message | None:
        """Fetch a message by ID, excluding deleted messages."""
        stmt = select(Message).where(
            and_(Message.id == str(message_id), Message.status != MessageStatus.DELETED)
        )
        return await self._session.scalar(stmt)

    async def get_with_user(self, message_id: str | int) -> tuple[Message, User] | None:
        """Return ``(Message, User)`` for a message"""
        stmt = (
            select(Message, User)
            .join(User, Message.authorId == User.id)
            .where(
                and_(
                    Message.id == message_id,
                    Message.status != MessageStatus.DELETED,
                )
            )
        )
        result = (await self._session.execute(stmt)).tuples().first()
        if result is not None:
            return result  # type: ignore[return-value]

        return (await self._session.execute(stmt)).tuples().first()  # type: ignore[return-value]

    # CUD

    async def create(
        self,
        author_id: str | int,
        guild_id: str | int,
        **kwargs: Unpack[MessageCreateKwargs],
    ) -> Message:
        """Insert a new message row."""
        message = Message(authorId=str(author_id), guildId=str(guild_id), **kwargs)
        self._session.add(message)
        await self._session.flush()
        return message

    async def create_with_conflict_ignore(
        self,
        author_id: str | int,
        guild_id: str | int,
        **kwargs: Unpack[MessageCreateKwargs],
    ) -> None:
        """Insert a new message row using ``ON CONFLICT DO NOTHING``."""
        values = {"authorId": str(author_id), "guildId": str(guild_id), **kwargs}
        stmt = pg_insert(Message).values(**values).on_conflict_do_nothing()
        await self._session.execute(stmt)
        await self._session.flush()

    async def update_status(self, message_id: str | int, status: MessageStatus) -> None:
        """Update a message's status"""
        stmt = (
            update(Message).where(Message.id == str(message_id)).values(status=status)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    # Cleanup

    async def get_recent_by_channel(
        self,
        channel_id: str | int,
        since: datetime,
        fallback_limit: int = 50,
    ) -> Sequence[Message]:
        """Return messages from *channel_id* created after *since*.

        Falls back to the most recent *fallback_limit* messages for that
        channel when no messages match the time window, so the caller
        always gets a non-empty result when messages exist.
        """
        stmt = (
            select(Message)
            .where(Message.channelId == str(channel_id), Message.createdAt >= since)
            .order_by(Message.createdAt.desc())
        )
        messages = (await self._session.execute(stmt)).scalars().all()
        if messages:
            return messages
        stmt = (
            select(Message)
            .where(Message.channelId == str(channel_id))
            .order_by(Message.createdAt.desc())
            .limit(fallback_limit)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get_recent_with_details_by_channels(
        self,
        channel_ids: list[str | int],
        since: datetime,
        limit: int = 100,
    ) -> Sequence[tuple[Message, User, Message | None, User | None]]:
        """Fetch messages from multiple channels with authors and referred message details.

        Returns a sequence of (Message, Author, ReferredMessage, ReferredAuthor) tuples.
        """
        from sqlalchemy.orm import aliased

        Author = aliased(User)
        ReferredMessage = aliased(Message)
        ReferredAuthor = aliased(User)

        channel_ids = [str(cid) for cid in channel_ids]

        stmt = (
            select(Message, Author, ReferredMessage, ReferredAuthor)
            .outerjoin(Author, Message.authorId == Author.id)
            .outerjoin(ReferredMessage, Message.referredMessageId == ReferredMessage.id)
            .outerjoin(ReferredAuthor, ReferredMessage.authorId == ReferredAuthor.id)
            .where(
                and_(
                    Message.channelId.in_(channel_ids),
                    Message.createdAt >= since,
                    Message.status != MessageStatus.DELETED,
                )
            )
            .order_by(Message.createdAt.asc())
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        return result.tuples().all()

    async def get_protected_message_ids(self, message_ids: list[str | int]) -> set[str]:
        """Return message IDs from *message_ids* that are referenced by other
        messages or reports and should not be deleted.
        """
        message_ids = [str(mid) for mid in message_ids]
        protected: set[str] = set()

        result = await self._session.execute(
            select(Message.referredMessageId)
            .where(Message.referredMessageId.in_(message_ids))
            .distinct()
        )
        protected.update(row[0] for row in result if row[0])

        result = await self._session.execute(
            select(Report.messageId).where(Report.messageId.in_(message_ids)).distinct()
        )
        protected.update(row[0] for row in result if row[0])

        result = await self._session.execute(
            select(Report.messageId).where(Report.messageId.in_(message_ids)).distinct()
        )
        protected.update(row[0] for row in result if row[0])

        return protected

    async def get_unprotected_messages_older_than(
        self, timestamp: datetime, limit: int = 500
    ) -> Sequence[Message]:
        """Fetch messages created before a specific timestamp that are NOT protected."""
        from sqlalchemy.orm import aliased

        MessageAlias = aliased(Message)

        stmt = (
            select(Message)
            .where(
                and_(
                    Message.createdAt < timestamp,
                    ~Message.id.in_(
                        select(MessageAlias.referredMessageId).where(
                            MessageAlias.referredMessageId.is_not(None)
                        )
                    ),
                    ~Message.id.in_(
                        select(Report.messageId).where(Report.messageId.is_not(None))
                    ),
                )
            )
            .limit(limit)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def bulk_delete_messages(self, message_ids: list[str | int]) -> int:
        """Delete messages and their broadcasts in bulk.

        Clears referredMessageId links first to avoid FK violations.
        Returns the number of messages deleted.
        """
        message_ids = [str(mid) for mid in message_ids]

        if not message_ids:
            return 0

        # PostgreSQL has a limit of 65535 parameters per statement.
        # We chunk into sizes of 5000 to be perfectly safe.
        chunk_size = 5000
        for i in range(0, len(message_ids), chunk_size):
            chunk = message_ids[i : i + chunk_size]

            await self._session.execute(
                update(Message)
                .where(Message.referredMessageId.in_(chunk))
                .values(referredMessageId=None)
            )

            await self._session.execute(delete(Message).where(Message.id.in_(chunk)))

        await self._session.flush()
        return len(message_ids)

    async def insert_pending_message_if_new(
        self,
        *,
        message_id: str | int,
        content: str | None,
        images_url: list[str] | None,
        channel_id: str | int,
        guild_id: str | int,
        author_id: str | int,
        referred_message_id: str | int | None,
        status: MessageStatus,
        retention_until: datetime | None,
    ) -> bool:
        """Insert a message using ``ON CONFLICT DO NOTHING``.

        Returns *True* if the row was inserted, *False* if it already existed
        (duplicate detection).
        """
        if referred_message_id is not None:
            exists = await self._session.scalar(
                select(1).where(Message.id == str(referred_message_id))
            )
            if not exists:
                referred_message_id = None

        stmt = (
            pg_insert(Message)
            .values(
                id=str(message_id),
                content=content,
                imagesUrl=images_url,
                channelId=str(channel_id),
                guildId=str(guild_id),
                authorId=str(author_id),
                referredMessageId=str(referred_message_id)
                if referred_message_id is not None
                else None,
                status=status,
                deletionQueuedAt=None,
                retentionUntil=retention_until,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[union-attr]

    async def bulk_create_messages(self, messages: list[dict]) -> int:
        """Insert multiple messages using a single statement with conflict ignore.

        Each dict in *messages* must contain keys matching the Message columns
        used by `insert_pending_message_if_new`. Returns the number of rows
        inserted (best-effort; may be driver-dependent).
        """
        if not messages:
            return 0

        # Ensure ids are strings and prepare payloads
        payloads = []
        for m in messages:
            payloads.append(
                {
                    "id": str(m.get("id")),
                    "content": m.get("content"),
                    "imagesUrl": m.get("images_url"),
                    "channelId": str(m.get("channel_id")),
                    "guildId": str(m.get("guild_id")),
                    "authorId": str(m.get("author_id")),
                    "referredMessageId": (
                        str(m.get("referred_message_id"))
                        if m.get("referred_message_id") is not None
                        else None
                    ),
                    "status": m.get("status"),
                    "deletionQueuedAt": None,
                    "retentionUntil": m.get("retention_until"),
                }
            )

        stmt = pg_insert(Message).values(payloads).on_conflict_do_nothing(
            index_elements=["id"]
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        # Some asyncpg/SQLAlchemy backends may not populate rowcount reliably
        try:
            return int(result.rowcount or 0)
        except Exception:
            return 0

    async def get_by_id_any_status(self, message_id: str | int) -> Message | None:
        """Fetch a message by ID regardless of status (including DELETED)."""
        stmt = select(Message).where(Message.id == str(message_id))
        return await self._session.scalar(stmt)

    async def is_in_deletion_queue(self, message_id: str | int) -> bool:
        """Check if a message is marked as DELETED (pending cleanup)."""
        stmt = (
            select(Message.id)
            .where(
                and_(
                    Message.id == str(message_id),
                    Message.status == MessageStatus.DELETED,
                )
            )
            .limit(1)
        )
        return (await self._session.scalar(stmt)) is not None

    # Reaction helpers

    async def get_with_specific_reaction(
        self, message_id: str | int, emoji_id: str | int
    ) -> tuple[Message, MessageReaction | None] | None:
        """Return ``(Message, HubMessageReaction | None)`` for a message and emoji.

        Falls back to the broadcast table when the direct lookup misses.
        """
        stmt = (
            select(Message, MessageReaction)
            .outerjoin(
                MessageReaction,
                (Message.id == MessageReaction.messageId)
                & (MessageReaction.emoji == str(emoji_id)),
            )
            .where(Message.id == message_id)
        )
        row = (await self._session.execute(stmt)).first()
        if row:
            return (row[0], row[1])

        row = (await self._session.execute(stmt)).first()
        if row:
            return (row[0], row[1])
        return None

    async def get_with_reactions_loaded(self, message_id: str | int) -> Message | None:
        """Return a message with reactions eagerly loaded, using broadcast fallback.

        Excludes deleted messages.
        """
        stmt = (
            select(Message)
            .where(
                and_(
                    Message.id == str(message_id),
                    Message.status != MessageStatus.DELETED,
                )
            )
            .options(selectinload(Message.reactions))
        )
        message = await self._session.scalar(stmt)
        if message:
            return message

        return await self._session.scalar(stmt)

    async def add_reaction(
        self, message_id: str | int, emoji: str, users: list[str | int] | None = None
    ) -> MessageReaction:
        """Create a new reaction entry for a message."""
        if users:
            users = [str(uid) for uid in users]
        reaction = MessageReaction(
            messageId=str(message_id), emoji=emoji, users=users or []
        )
        self._session.add(reaction)
        await self._session.flush()
        return reaction

    async def delete_reaction(self, reaction: MessageReaction) -> None:
        """Delete a reaction entry."""
        await self._session.delete(reaction)
        await self._session.flush()

    async def update_reaction_users(
        self, reaction: MessageReaction, users: list[str | int]
    ) -> None:
        """Update the users list on a reaction entry."""
        users = [str(uid) for uid in users]
        reaction.users = users
        self._session.add(reaction)
        await self._session.flush()

    # Edit support

    async def update_content(self, message_id: str, content: str) -> None:
        """Update the text content of a message row."""
        stmt = update(Message).where(Message.id == message_id).values(content=content)
        await self._session.execute(stmt)
        await self._session.flush()
