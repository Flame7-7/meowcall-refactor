from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Unpack

from models import (
    Appeal,
    AppealStatus,
    Blacklist,
    Infraction,
    InfractionStatus,
    InfractionType,
    ServerData,
    User,
)
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import aliased, joinedload, selectinload

if TYPE_CHECKING:
    from ._types import AppealCreateKwargs, InfractionCreateKwargs

from .baseRepository import BaseRepository


class ModerationRepository(BaseRepository):
    """Repository for moderation-related queries (infractions, appeals, blacklists)."""

    # ══════════════════════════════════════════════════════════════════════
    # Infractions
    # ══════════════════════════════════════════════════════════════════════

    async def get_infraction_by_id(
        self,
        infraction_id: str,
        *,
        with_appeals: bool = False,
    ) -> Infraction | None:
        stmt = select(Infraction).where(Infraction.id == infraction_id)
        if with_appeals:
            stmt = stmt.options(selectinload(Infraction.appeals))
        return await self._session.scalar(stmt)

    async def get_active_by_type(
        self,
        user_id: str | int | None,
        guild_id: str | int | None,
        infraction_type: InfractionType,
    ) -> Infraction | None:
        now = datetime.now(UTC)
        conditions = [
            Infraction.type == infraction_type,
            Infraction.status == InfractionStatus.ACTIVE,
            or_(Infraction.expiresAt.is_(None), Infraction.expiresAt > now),
        ]
        if user_id:
            conditions.append(Infraction.userId == str(user_id))
        if guild_id:
            conditions.append(Infraction.serverId == str(guild_id))

        stmt = select(Infraction).where(and_(*conditions)).limit(1)
        return await self._session.scalar(stmt)

    async def create_infraction(
        self,
        moderator_id: str | int,
        type: InfractionType,
        reason: str,
        *,
        user_id: str | int | None = None,
        guild_id: str | int | None = None,
        **kwargs: Unpack[InfractionCreateKwargs],
    ) -> Infraction:
        infraction = Infraction(
            userId=str(user_id) if user_id is not None else None,
            serverId=str(guild_id) if guild_id is not None else None,
            moderatorId=str(moderator_id),
            type=type,
            reason=reason,
            **kwargs,
        )
        self._session.add(infraction)
        await self._session.flush()
        return infraction

    async def revoke_infraction(self, infraction_id: str) -> bool:
        infraction = await self.get_infraction_by_id(infraction_id)
        if infraction is None:
            return False
        infraction.status = InfractionStatus.REVOKED
        await self._session.flush()
        return True

    async def delete_infraction(self, infraction_id: str) -> Infraction | None:
        infraction = await self.get_infraction_by_id(infraction_id)
        if infraction is None:
            return None
        await self._session.delete(infraction)
        await self._session.flush()
        return infraction

    async def update_infraction(
        self,
        infraction_id: str,
        *,
        status: InfractionStatus | None = None,
        reason: str | None = None,
    ) -> Infraction | None:
        infraction = await self.get_infraction_by_id(infraction_id)
        if infraction is None:
            return None
        if status is not None:
            infraction.status = status
        if reason is not None:
            infraction.reason = reason
        await self._session.flush()
        return infraction

    async def update_infraction_notified(self, infraction_id: str) -> None:
        infraction = await self.get_infraction_by_id(infraction_id)
        if infraction is not None:
            infraction.notified = True
            await self._session.flush()

    async def list_infractions(
        self,
        *,
        user_id: str | int | None = None,
        guild_id: str | int | None = None,
        page: int = 0,
        per_page: int = 10,
    ) -> Sequence[Infraction]:
        conditions: list = []
        if user_id:
            conditions.append(Infraction.userId == str(user_id))
        if guild_id:
            conditions.append(Infraction.serverId == str(guild_id))

        stmt = (
            select(Infraction)
            .where(and_(*conditions))
            .options(
                joinedload(Infraction.moderator),
            )
            .order_by(Infraction.createdAt.desc())
            .offset(page * per_page)
            .limit(per_page)
        )
        return (await self._session.execute(stmt)).scalars().unique().all()

    async def list_infractions_with_count(
        self,
        *,
        filter_type: str = "users",
        specific_user_id: str | int | None = None,
        specific_guild_id: str | int | None = None,
        page: int = 0,
        per_page: int = 5,
    ) -> tuple[Sequence[Infraction], int]:
        base_filter: list = []

        if specific_user_id:
            base_filter.append(Infraction.userId == str(specific_user_id))
        elif specific_guild_id:
            base_filter.append(Infraction.serverId == str(specific_guild_id))
        elif filter_type == "users":
            base_filter.append(Infraction.userId.is_not(None))
        else:
            base_filter.append(Infraction.serverId.is_not(None))

        count_stmt = select(func.count(Infraction.id)).where(and_(*base_filter))
        total_count = (await self._session.execute(count_stmt)).scalar_one()

        options = [joinedload(Infraction.moderator)]
        if filter_type == "users" or specific_user_id:
            options.append(joinedload(Infraction.user))

        stmt = (
            select(Infraction)
            .where(and_(*base_filter))
            .options(*options)
            .order_by(Infraction.createdAt.desc())
            .offset(page * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all(), total_count

    async def get_infraction_names(
        self, infraction_id: str
    ) -> tuple[str, str, str, str] | None:
        user_alias = aliased(User)
        mod_alias = aliased(User)

        result = await self._session.execute(
            select(
                user_alias.name,
                mod_alias.name,
                ServerData.name,
            )
            .select_from(Infraction)
            .where(Infraction.id == infraction_id)
            .outerjoin(user_alias, user_alias.id == Infraction.userId)
            .outerjoin(mod_alias, mod_alias.id == Infraction.moderatorId)
            .outerjoin(ServerData, ServerData.id == Infraction.serverId)
        )

        row = result.first()
        if not row:
            return None

        return (
            row[0],
            row[1] or "Unknown User",
            row[2] or "Unknown Moderator",
            row[3] or "Unknown Server",
        )

    async def get_appealable_infractions(
        self, user_id: str | int
    ) -> Sequence[Infraction]:
        stmt = (
            select(Infraction)
            .where(
                and_(
                    Infraction.userId == str(user_id),
                    Infraction.status == InfractionStatus.ACTIVE,
                    or_(
                        Infraction.type == InfractionType.BAN,
                        Infraction.type == InfractionType.MUTE,
                    ),
                    or_(
                        Infraction.expiresAt.is_(None),
                        Infraction.expiresAt > datetime.now(UTC),
                    ),
                )
            )
            .options(
                selectinload(Infraction.hub),
                selectinload(Infraction.appeals),
            )
            .order_by(Infraction.createdAt.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def reserve_infraction_notification(self, infraction_id: str) -> bool:
        from sqlalchemy import update

        stmt = (
            update(Infraction)
            .where(
                and_(
                    Infraction.id == infraction_id,
                    Infraction.notified.is_(False),
                )
            )
            .values(notified=True)
            .returning(Infraction.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_any_access_restriction(
        self,
        user_id: str | int,
        guild_id: str | int,
    ) -> bool:
        now = datetime.now(UTC)
        bannable = [InfractionType.BAN, InfractionType.MUTE]

        user_infraction = exists().where(
            and_(
                Infraction.userId == str(user_id),
                Infraction.status == InfractionStatus.ACTIVE,
                Infraction.type.in_(bannable),
                or_(Infraction.expiresAt.is_(None), Infraction.expiresAt > now),
            )
        )
        server_infraction = exists().where(
            and_(
                Infraction.serverId == str(guild_id),
                Infraction.status == InfractionStatus.ACTIVE,
                Infraction.type.in_(bannable),
                or_(Infraction.expiresAt.is_(None), Infraction.expiresAt > now),
            )
        )
        # Blacklist now uses status instead of just expiresAt
        user_blacklist = exists().where(
            and_(
                Blacklist.userId == str(user_id),
                Blacklist.status == InfractionStatus.ACTIVE,
                or_(Blacklist.expiresAt.is_(None), Blacklist.expiresAt > now),
            )
        )
        server_blacklist = exists().where(
            and_(
                Blacklist.serverId == str(guild_id),
                Blacklist.status == InfractionStatus.ACTIVE,
                or_(Blacklist.expiresAt.is_(None), Blacklist.expiresAt > now),
            )
        )

        row = await self._session.scalar(
            select(1).where(
                or_(
                    user_infraction, server_infraction, user_blacklist, server_blacklist
                )
            )
        )
        return row is not None

    async def has_active_infraction(
        self,
        user_id: str | int | None,
        guild_id: str | int | None,
        infraction_type: InfractionType,
    ) -> bool:
        now = datetime.now(UTC)
        conditions = [
            Infraction.type == infraction_type,
            Infraction.status == InfractionStatus.ACTIVE,
            or_(Infraction.expiresAt.is_(None), Infraction.expiresAt > now),
        ]
        if user_id:
            conditions.append(Infraction.userId == str(user_id))
        if guild_id:
            conditions.append(Infraction.serverId == str(guild_id))

        stmt = select(Infraction.id).where(and_(*conditions)).limit(1)
        return (await self._session.scalar(stmt)) is not None

    # ══════════════════════════════════════════════════════════════════════
    # Appeals
    # ══════════════════════════════════════════════════════════════════════

    async def get_appeal_by_id(
        self,
        appeal_id: str,
        *,
        with_infraction: bool = False,
    ) -> Appeal | None:
        stmt = select(Appeal).where(Appeal.id == appeal_id)
        if with_infraction:
            stmt = stmt.options(joinedload(Appeal.infraction))
        return await self._session.scalar(stmt)

    async def create_appeal(
        self,
        infraction_id: str,
        user_id: str | int,
        reason: str,
        **kwargs: Unpack[AppealCreateKwargs],
    ) -> Appeal:
        appeal = Appeal(
            infractionId=infraction_id,
            userId=str(user_id),
            reason=reason,
            **kwargs,
        )
        self._session.add(appeal)
        await self._session.flush()
        return appeal

    async def update_appeal_status(self, appeal_id: str, status: AppealStatus) -> bool:
        appeal = await self.get_appeal_by_id(appeal_id)
        if appeal is None:
            return False
        appeal.status = status
        await self._session.flush()
        return True

    # ══════════════════════════════════════════════════════════════════════
    # Blacklists
    # ══════════════════════════════════════════════════════════════════════

    def _active_blacklist_conditions(
        self, *, user_id: str | None = None, guild_id: str | None = None
    ) -> list:
        """Shared conditions for an active (non-revoked) blacklist entry."""
        conditions: list = [Blacklist.status == InfractionStatus.ACTIVE]
        conditions: list = [
            Blacklist.status == InfractionStatus.ACTIVE,
            or_(
                Blacklist.expiresAt.is_(None),
                Blacklist.expiresAt > datetime.now(UTC)
            )
        ]
        if user_id is not None:
            conditions.append(Blacklist.userId == user_id)
        if guild_id is not None:
            conditions.append(Blacklist.serverId == guild_id)
        return conditions

    async def get_blacklist(self, user_id: str | int) -> Blacklist | None:
        """Return the active blacklist entry for a user, if any."""
        stmt = (
            select(Blacklist)
            .where(and_(*self._active_blacklist_conditions(user_id=str(user_id))))
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def get_server_blacklist(self, guild_id: str | int) -> Blacklist | None:
        """Return the active blacklist entry for a server, if any."""
        stmt = (
            select(Blacklist)
            .where(and_(*self._active_blacklist_conditions(guild_id=str(guild_id))))
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def get_active_blacklists(self) -> Sequence[Blacklist]:
        """Return all active blacklist entries (users and servers)."""
        stmt = select(Blacklist).where(Blacklist.status == InfractionStatus.ACTIVE)
        stmt = select(Blacklist).where(
            and_(
                Blacklist.status == InfractionStatus.ACTIVE,
                or_(
                    Blacklist.expiresAt.is_(None),  # Permanent restrictions
                    Blacklist.expiresAt > datetime.now(UTC)       # Active temporary restrictions
                )
            )
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def is_user_blacklisted(self, user_id: str | int) -> bool:
        return (await self.get_blacklist(str(user_id))) is not None

    async def is_server_blacklisted(self, guild_id: str | int) -> bool:
        return (await self.get_server_blacklist(str(guild_id))) is not None

    async def create_blacklist_entry(
        self,
        moderator_id: str | int,
        reason: str,
        *,
        user_id: str | int | None = None,
        guild_id: str | int | None = None,
        server_name: str | None = None,
        duration_ms: int | None = None,
    ) -> Blacklist:
        """Create a new blacklist entry for a user or server."""
        expires_at = None
        if duration_ms:
            from datetime import timedelta

            expires_at = datetime.now(UTC) + timedelta(milliseconds=duration_ms)

        entry = Blacklist(
            moderatorId=str(moderator_id),
            reason=reason,
            userId=str(user_id) if user_id is not None else None,
            serverId=str(guild_id) if guild_id is not None else None,
            serverName=server_name,
            expiresAt=expires_at,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def delete_blacklist_entry(self, user_id: str | int) -> bool:
        """Revoke the active user blacklist entry. Returns *True* if found."""
        entry = await self.get_blacklist(str(user_id))
        if entry is None:
            return False
        entry.status = InfractionStatus.REVOKED
        await self._session.flush()
        return True

    async def delete_server_blacklist_entry(self, guild_id: str | int) -> bool:
        """Revoke the active server blacklist entry. Returns *True* if found."""
        entry = await self.get_server_blacklist(str(guild_id))
        if entry is None:
            return False
        entry.status = InfractionStatus.REVOKED
        await self._session.flush()
        return True

    async def delete_all_user_blacklists(self, user_id: str | int) -> bool:
        """Revoke *all* blacklist entries for a user. Returns *True* if any were found."""
        stmt = select(Blacklist).where(Blacklist.userId == str(user_id))
        entries = (await self._session.execute(stmt)).scalars().all()
        if not entries:
            return False
        for entry in entries:
            entry.status = InfractionStatus.REVOKED
        await self._session.flush()
        return True

    # Blacklist records (staff records browser)

    async def get_blacklist_records(
        self,
        *,
        target: str | int | None = None,
        moderator: str | int | None = None,
        query: str | None = None,
        include_servers: bool = True,
    ) -> Sequence[Blacklist]:
        """Fetch blacklist records with optional filters and eager loads."""
        stmt = select(Blacklist).options(
            selectinload(Blacklist.user),
            selectinload(Blacklist.moderator),
            selectinload(Blacklist.server),
        )
        if target:
            stmt = stmt.where(
                or_(Blacklist.userId == str(target), Blacklist.serverId == str(target))
            )
        if moderator:
            stmt = stmt.where(Blacklist.moderatorId == str(moderator))
        if not include_servers:
            stmt = stmt.where(Blacklist.serverId.is_(None))
        if query:
            stmt = stmt.where(
                or_(
                    Blacklist.reason.ilike(f"%{query}%"),
                    Blacklist.userId.ilike(f"%{query}%"),
                    Blacklist.serverId.ilike(f"%{query}%"),
                    Blacklist.serverName.ilike(f"%{query}%"),
                )
            )
        return (await self._session.execute(stmt)).scalars().all()

    async def count_blacklist_records(
        self,
        *,
        target: str | int | None = None,
        moderator: str | int | None = None,
        query: str | None = None,
    ) -> int:
        stmt = select(func.count(Blacklist.id))
        if target:
            stmt = stmt.where(
                or_(Blacklist.userId == str(target), Blacklist.serverId == str(target))
            )
        if moderator:
            stmt = stmt.where(Blacklist.moderatorId == str(moderator))
        if query:
            stmt = stmt.where(
                or_(
                    Blacklist.reason.ilike(f"%{query}%"),
                    Blacklist.userId.ilike(f"%{query}%"),
                    Blacklist.serverId.ilike(f"%{query}%"),
                    Blacklist.serverName.ilike(f"%{query}%"),
                )
            )
        return (await self._session.scalar(stmt)) or 0

    # Blacklist autocomplete helpers

    async def search_blacklisted_targets_autocomplete(
        self,
        current: str,
        *,
        user_limit: int = 12,
        server_limit: int = 13,
    ) -> tuple[Sequence[tuple[str, str | None]], Sequence[tuple[str, str | None]]]:
        """Return blacklisted users and servers for autocomplete.

        Returns ``(user_rows, server_rows)`` where each row is ``(id, name)``.
        """
        user_stmt = (
            select(Blacklist.userId, User.name)
            .join(User, Blacklist.userId == User.id)
            .where(Blacklist.userId.is_not(None))
            .distinct(Blacklist.userId)
        )
        if current:
            user_stmt = user_stmt.where(
                or_(
                    User.name.ilike(f"%{current}%"),
                    Blacklist.userId.ilike(f"%{current}%"),
                )
            )
        user_stmt = user_stmt.limit(user_limit)
        user_rows = (await self._session.execute(user_stmt)).all()

        server_stmt = (
            select(Blacklist.serverId, Blacklist.serverName)
            .where(Blacklist.serverId.is_not(None))
            .distinct(Blacklist.serverId)
        )
        if current:
            server_stmt = server_stmt.where(
                or_(
                    Blacklist.serverName.ilike(f"%{current}%"),
                    Blacklist.serverId.ilike(f"%{current}%"),
                )
            )
        server_stmt = server_stmt.limit(server_limit)
        server_rows = (await self._session.execute(server_stmt)).all()

        return user_rows, server_rows  # type: ignore[return-value]

    async def search_blacklist_moderators_autocomplete(
        self,
        current: str,
        limit: int = 25,
    ) -> Sequence[User]:
        """Return moderators who have issued blacklists, for autocomplete."""
        mod_ids_stmt = select(Blacklist.moderatorId).distinct()
        mod_ids = (await self._session.execute(mod_ids_stmt)).scalars().all()

        if not mod_ids:
            return []

        users_stmt = select(User).where(User.id.in_(mod_ids))
        if current:
            users_stmt = users_stmt.where(User.name.ilike(f"%{current}%"))
        users_stmt = users_stmt.limit(limit)
        return (await self._session.execute(users_stmt)).scalars().all()
