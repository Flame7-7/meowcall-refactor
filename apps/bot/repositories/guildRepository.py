from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Unpack

from models import ServerData
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from ._types import ServerDataCreateKwargs, ServerDataUpdateKwargs

from .baseRepository import BaseRepository


def _is_retryable_upsert_error(exc: DBAPIError) -> bool:
    # PostgreSQL SQLSTATE:
    # - 40P01: deadlock_detected
    # - 40001: serialization_failure
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    return sqlstate in {"40P01", "40001"}


class GuildRepository(BaseRepository):
    """Repository for :class:`ServerData` queries."""

    async def get_by_id(self, guild_id: str | int) -> ServerData | None:
        """Fetch a server by its primary key."""
        stmt = select(ServerData).where(ServerData.id == str(guild_id))
        return await self._session.scalar(stmt)

    async def create(
        self, guild_id: str | int, **kwargs: Unpack[ServerDataCreateKwargs]
    ) -> ServerData:
        """Insert a new server row."""
        server = ServerData(id=str(guild_id), **kwargs)
        self._session.add(server)
        await self._session.flush()
        return server

    async def update(
        self, guild_id: str | int, **kwargs: Unpack[ServerDataUpdateKwargs]
    ) -> ServerData | None:
        """Update an existing server with the given keyword attributes.

        Returns the updated :class:`ServerData`, or *None* if not found.
        """
        server = await self.get_by_id(guild_id)
        if server is None:
            return None
        for key, value in kwargs.items():
            setattr(server, key, value)

        self._session.add(server)
        await self._session.flush()
        return server

    async def upsert(
        self,
        guild_id: str | int,
        name: str | None = None,
        icon_url: str | None = None,
        **kwargs: Unpack[ServerDataUpdateKwargs],  # type: ignore[reportGeneralTypeIssues]
    ) -> None:
        """Insert or update a server row using ``ON CONFLICT DO UPDATE``.

        Used when the bot joins a guild or when broadcast processing ensures
        the server record exists.
        """
        values: dict[str, Any] = {"id": guild_id, **kwargs}
        update_set: dict[str, Any] = {}

        if name is not None:
            values["name"] = name
            update_set["name"] = name
        if icon_url is not None:
            values["iconUrl"] = icon_url
            update_set["iconUrl"] = icon_url

        if not update_set:
            stmt = pg_insert(ServerData).values(**values).on_conflict_do_nothing()
        else:
            stmt = (
                pg_insert(ServerData)
                .values(**values)
                .on_conflict_do_update(index_elements=["id"], set_=update_set)
            )
        for attempt in range(3):
            try:
                await self._session.execute(stmt)
                await self._session.flush()
                return
            except DBAPIError as exc:
                if not _is_retryable_upsert_error(exc) or attempt >= 2:
                    raise
                # Reset broken transaction state before retrying.
                await self._session.rollback()
                await asyncio.sleep(0.05 * (2**attempt))

    async def ensure_exists(self, guild_id: str | int, name: str | None = None) -> None:
        """Insert a server row if it doesn't already exist (no-op on conflict)."""
        stmt = (
            pg_insert(ServerData)
            .values(id=str(guild_id), name=name or "Unknown Server")
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)
        await self._session.flush()
