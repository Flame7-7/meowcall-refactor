from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Unpack

from models import Message, MessageReaction, MessageStatus, User
from repositories.messageRepository import MessageRepository
from services.baseService import BaseService

if TYPE_CHECKING:
    from repositories._types import MessageCreateKwargs
    from sqlalchemy.ext.asyncio import AsyncSession


class MessageService(BaseService):
    """Service layer for Message business logic."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.message_repo = MessageRepository(session)

    # ---------------------------------------------------------
    # Single-row Lookups
    # ---------------------------------------------------------
    async def get_message_by_id(self, message_id: str | int) -> Message | None:
        """Fetch a message by ID, excluding deleted messages."""
        return await self.message_repo.get_by_id(message_id)

    async def get_message_with_user(
        self, message_id: str | int
    ) -> tuple[Message, User] | None:
        """Fetch a message along with its author."""
        return await self.message_repo.get_with_user(message_id)

    async def get_message_any_status(self, message_id: str | int) -> Message | None:
        """Fetch a message by ID regardless of status."""
        return await self.message_repo.get_by_id_any_status(message_id)

    # ---------------------------------------------------------
    # Creation & Modification
    # ---------------------------------------------------------
    async def create_message(
        self,
        author_id: str | int,
        guild_id: str | int,
        **kwargs: Unpack[MessageCreateKwargs],
    ) -> Message:
        """Insert a new message row."""
        return await self.message_repo.create(author_id, guild_id, **kwargs)

    async def create_message_if_new(
        self,
        author_id: str | int,
        guild_id: str | int,
        **kwargs: Unpack[MessageCreateKwargs],
    ) -> None:
        """Insert a new message row using ON CONFLICT DO NOTHING."""
        await self.message_repo.create_with_conflict_ignore(
            author_id, guild_id, **kwargs
        )

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
        status: MessageStatus = MessageStatus.ACTIVE,
        retention_until: datetime | None = None,
    ) -> bool:
        """Insert a message using ON CONFLICT DO NOTHING with detailed fields."""
        return await self.message_repo.insert_pending_message_if_new(
            message_id=message_id,
            content=content,
            images_url=images_url,
            channel_id=channel_id,
            guild_id=guild_id,
            author_id=author_id,
            referred_message_id=referred_message_id,
            status=status,
            retention_until=retention_until,
        )

    async def update_message_status(
        self, message_id: str | int, status: MessageStatus
    ) -> None:
        """Update a message's status."""
        await self.message_repo.update_status(message_id, status)

    async def update_message_content(self, message_id: str | int, content: str) -> None:
        """Update the text content of a message."""
        await self.message_repo.update_content(str(message_id), content)

    # ---------------------------------------------------------
    # Bulk & Collections
    # ---------------------------------------------------------
    async def get_recent_messages_by_channel(
        self,
        channel_id: str | int,
        since: datetime,
        fallback_limit: int = 50,
    ) -> Sequence[Message]:
        """Fetch recent messages from a channel."""
        return await self.message_repo.get_recent_by_channel(
            channel_id, since, fallback_limit
        )

    async def get_unprotected_messages_older_than(
        self, timestamp: datetime, limit: int = 500
    ) -> Sequence[Message]:
        """Fetch messages created before a specific timestamp that are NOT protected."""
        return await self.message_repo.get_unprotected_messages_older_than(
            timestamp, limit
        )

    async def get_protected_message_ids(self, message_ids: list[str | int]) -> set[str]:
        """Identify which message IDs cannot be deleted."""
        return await self.message_repo.get_protected_message_ids(message_ids)

    async def bulk_delete_messages(self, message_ids: list[str | int]) -> int:
        """Delete messages in bulk, avoiding foreign key errors."""
        return await self.message_repo.bulk_delete_messages(message_ids)

    async def is_message_in_deletion_queue(self, message_id: str | int) -> bool:
        """Check if a message is queued for deletion."""
        return await self.message_repo.is_in_deletion_queue(message_id)

    # ---------------------------------------------------------
    # Reactions
    # ---------------------------------------------------------
    async def get_message_with_specific_reaction(
        self, message_id: str | int, emoji_id: str | int
    ) -> tuple[Message, MessageReaction | None] | None:
        """Fetch a message alongside a specific reaction if it exists."""
        return await self.message_repo.get_with_specific_reaction(message_id, emoji_id)

    async def get_message_with_reactions_loaded(
        self, message_id: str | int
    ) -> Message | None:
        """Fetch a message with its reactions eagerly loaded."""
        return await self.message_repo.get_with_reactions_loaded(message_id)

    async def add_reaction(
        self, message_id: str | int, emoji: str, users: list[str | int] | None = None
    ) -> MessageReaction:
        """Add a reaction to a message."""
        return await self.message_repo.add_reaction(message_id, emoji, users)

    async def delete_reaction(self, reaction: MessageReaction) -> None:
        """Delete a reaction."""
        await self.message_repo.delete_reaction(reaction)

    async def update_reaction_users(
        self, reaction: MessageReaction, users: list[str | int]
    ) -> None:
        """Update the list of users who reacted with a specific emoji."""
        await self.message_repo.update_reaction_users(reaction, users)
