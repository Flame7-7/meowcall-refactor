from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from repositories.userRepository import UserRepository
from services.baseService import BaseService

if TYPE_CHECKING:
    from models import User


class UserService(BaseService):
    def _user_repo(self) -> UserRepository:
        return UserRepository(self.session)

    # ═══════════════════════════════════════════════════════════════════════
    # USER CRUD
    # ═══════════════════════════════════════════════════════════════════════

    async def get_user_by_id(self, user_id: int | str) -> User | None:
        """Get user by ID. Returns None if not found."""
        return await self._user_repo().get_by_id(str(user_id))

    async def upsert_user(
        self, user: discord.User | discord.Member | discord.ClientUser
    ) -> User:
        """
        Create user if they don't exist, or update their profile info if they do.
        Safe to use within larger transactions — does not commit.
        """
        return await self._user_repo().upsert(
            str(user.id),
            name=user.name,
            image=user.display_avatar.url,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # LOCALE
    # ═══════════════════════════════════════════════════════════════════════

    async def get_locale(self, user_id: int | str) -> str:
        """Get user's locale with fallback to 'en'."""
        user = await self._user_repo().get_by_id(str(user_id))
        return user.locale if user and user.locale else "en"

    async def update_locale(self, user_id: int | str, locale: str) -> None:
        """Update user's preferred locale."""
        await self._user_repo().update(str(user_id), locale=locale)
        await self.session.flush()

    # ═══════════════════════════════════════════════════════════════════════
    # STATS & ACTIVITY
    # ═══════════════════════════════════════════════════════════════════════

    async def increment_message_count(self, user_id: int | str) -> bool:
        """Increment user's message count. Returns False if user not found."""
        # Check if user exists first
        exists = await self._user_repo().exists(str(user_id))
        if not exists:
            return False
        
        # Use bulk operation to avoid fetching the whole user object
        updated = await self._user_repo().bulk_increment_message_count([str(user_id)])
        return updated > 0
    
    async def bulk_increment_message_count(self, user_ids: list[str | int]) -> int:
        """Bulk increment message count for multiple users.
        
        Returns the number of users updated.
        """
        if not user_ids:
            return 0
        return await self._user_repo().bulk_increment_message_count(user_ids)

    async def get_leaderboard(self, limit: int = 10) -> list[User]:
        """Return top users by messageCount descending."""
        return list(await self._user_repo().get_top_by_message_count(limit))

    async def get_user_rank(self, user_id: int | str) -> int | None:
        """Return 1-based rank by messageCount. Returns None if user not found."""
        return await self._user_repo().get_rank_by_message_count(str(user_id))

    # ═══════════════════════════════════════════════════════════════════════
    # PREFERENCES
    # ═══════════════════════════════════════════════════════════════════════

    async def update_mention_on_reply(self, user_id: int | str, enabled: bool) -> None:
        """Update user's mention-on-reply preference."""
        await self._user_repo().update(str(user_id), mentionOnReply=enabled)
        await self.session.flush()

    # ═══════════════════════════════════════════════════════════════════════
    # VOTERS
    # ═══════════════════════════════════════════════════════════════════════

    async def fetch_voters(self, exclude_ids: set[int] = frozenset()) -> list[User]:
        """Return all users who have voted in the last 8 hours"""
        return list(await self._user_repo().fetch_voters(exclude_ids=exclude_ids))
