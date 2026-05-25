from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Unpack

from models import Badges, User
from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from ._types import UserCreateKwargs, UserUpdateKwargs

from .baseRepository import BaseRepository


class UserRepository(BaseRepository):
    """Repository for :class:`User` queries."""

    async def get_by_id(self, user_id: str | int, eager_load: bool = False) -> User | None:
        """Fetch a user by its primary key.
        
        Args:
            user_id: User ID to fetch
            eager_load: If True, eagerly load badges and related data
        """
        stmt = select(User).where(User.id == str(user_id))
        if eager_load:
            stmt = stmt.options(selectinload(User.badges))
        return await self._session.scalar(stmt)

    async def get_locale(self, user_id: str | int) -> str | None:
        """Return only the locale column for the user or *None*."""
        stmt = select(User.locale).where(User.id == str(user_id))
        return await self._session.scalar(stmt)

    async def exists(self, user_id: str | int) -> bool:
        """Check whether a user row exists."""
        stmt = select(User.id).where(User.id == str(user_id))
        return (await self._session.scalar(stmt)) is not None

    async def create(
        self, user_id: str | int, **kwargs: Unpack[UserCreateKwargs]
    ) -> User:
        """Insert a new user row."""
        kwargs.setdefault("badges", [])
        if kwargs.get("badges") is list:
            kwargs["badges"] = []
        kwargs.setdefault("lastMessageAt", datetime.now(UTC))
        user = User(id=str(user_id), **kwargs)
        self._session.add(user)
        await self._session.flush()
        return user

    async def update(
        self, user_id: str | int, **kwargs: Unpack[UserUpdateKwargs]
    ) -> User | None:
        """Update an existing user with the given keyword attributes.

        Returns the updated :class:`User`, or *None* if not found.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        for key, value in kwargs.items():
            setattr(user, key, value)

        self._session.add(user)
        await self._session.flush()
        return user

    async def upsert(
        self,
        user_id: str | int,
        **kwargs: Unpack[UserUpdateKwargs],  # type: ignore[reportGeneralTypeIssues]
    ) -> User:
        """Atomically create or update a user row.

        Uses PostgreSQL ``ON CONFLICT`` to avoid race conditions when concurrent
        requests upsert the same user at the same time.
        """
        payload = dict(kwargs)
        payload.setdefault("badges", [])
        if payload.get("badges") is list:
            payload["badges"] = []
        payload.setdefault("lastMessageAt", datetime.now(UTC))

        stmt = insert(User).values(id=str(user_id), **payload)

        update_values = dict(kwargs)
        if update_values:
            stmt = stmt.on_conflict_do_update(
                index_elements=[User.id],
                set_=update_values,
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=[User.id])

        result = await self._session.execute(stmt.returning(User))
        user = result.scalar_one_or_none()

        if user is None:
            user = await self.get_by_id(user_id)
            if user is None:
                msg = f"Failed to upsert user {user_id}"
                raise RuntimeError(msg)

        await self._session.flush()
        return user

    # Badges

    async def has_badge(self, user_id: str, badge: Badges) -> bool:
        """Check whether a user has a specific badge."""
        stmt = select(User.badges).where(User.id == user_id)
        badges = await self._session.scalar(stmt)
        if badges is None:
            return False
        return badge in badges

    async def bulk_increment_message_count(self, user_ids: list[str | int]) -> int:
        """Bulk increment message count for multiple users in a single query.
        
        Returns the number of rows updated.
        """
        if not user_ids:
            return 0
        
        now = datetime.now(UTC)
        stmt = (
            update(User)
            .where(User.id.in_([str(uid) for uid in user_ids]))
            .values(
                messageCount=User.messageCount + 1,
                lastMessageAt=now
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount or 0

    async def bulk_increment_message_counts(self, user_counts: dict[str | int, int]) -> int:
        """Bulk increment messageCount by arbitrary counts per user.

        *user_counts* maps user_id -> increment_amount. Returns number of
        rows updated.
        """
        if not user_counts:
            return 0

        now = datetime.now(UTC)
        ids = [str(uid) for uid in user_counts.keys()]

        # Build a CASE expression to increment by different amounts per id
        from sqlalchemy import case

        whens = {str(k): v for k, v in user_counts.items()}
        case_stmt = case(whens, value=User.id, else_=0)

        stmt = (
            update(User)
            .where(User.id.in_(ids))
            .values(messageCount=User.messageCount + case_stmt, lastMessageAt=now)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount or 0

    async def remove_expired_voter_badges(self, cutoff: datetime) -> int:
        """Remove VOTER badge from users who haven't voted since *cutoff*.

        Returns the number of users updated.
        """
        stmt = select(User).where(
            and_(
                User.badges.contains([Badges.VOTER]),
                User.lastVoted < cutoff,
            )
        )
        result = await self._session.execute(stmt)
        updated = 0
        for user in result.scalars():
            user.badges = [b for b in user.badges if b != Badges.VOTER]
            updated += 1
        if updated:
            await self._session.flush()
        return updated

    async def fetch_voters(self, exclude_ids: set[int] = frozenset()) -> Sequence[User]:
        """Returns all users who have voted in the last 8 hours"""

        stmt = select(User).where(
            User.lastVoted >= datetime.now(UTC) - timedelta(hours=8)
        )
        if exclude_ids:
            stmt = stmt.where(User.id.not_in([str(i) for i in exclude_ids]))

        return (await self._session.execute(stmt)).scalars().all()

    async def get_top_by_call_count(self, limit: int = 10) -> Sequence[User]:
        """Return the top users ordered by call count (global leaderboard)."""
        stmt = select(User).order_by(User.callCount.desc()).limit(limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_top_by_message_count(self, limit: int = 10) -> Sequence[User]:
        """Return the top users ordered by message count (global leaderboard)."""
        stmt = select(User).order_by(User.messageCount.desc()).limit(limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_rank_by_call_count(self, user_id: str | int) -> int | None:
        """Return the 1-based rank of a user by call count, or *None*."""
        user = await self._session.get(User, str(user_id))
        if user is None:
            return None
        count = (
            await self._session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.callCount > (user.callCount or 0))
            )
        ) or 0
        return count + 1

    async def get_rank_by_message_count(self, user_id: str | int) -> int | None:
        """Return the 1-based rank of a user by message count, or *None*."""
        user = await self._session.get(User, str(user_id))
        if user is None:
            return None
        count = (
            await self._session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.messageCount > (user.messageCount or 0))
            )
        ) or 0
        return count + 1
