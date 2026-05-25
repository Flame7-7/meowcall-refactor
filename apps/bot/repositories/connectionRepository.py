from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Unpack

from models import (
    Connection,
)
from sqlalchemy import delete, or_, select

if TYPE_CHECKING:
    from ._types import ConnectionCreateKwargs, ConnectionUpdateKwargs

from .baseRepository import BaseRepository


class ConnectionRepository(BaseRepository):
    """Repository for :class:`Connection` queries."""

    # Single-row lookups

    async def get_by_channel(self, channel_id: str | int) -> Connection | None:
        """Fetch a connection by its unique channel ID."""
        stmt = select(Connection).where(Connection.channelId == str(channel_id))
        return await self._session.scalar(stmt)

    async def get_by_id(self, connection_id: str) -> Connection | None:
        """Fetch a connection by its primary key ID."""
        stmt = select(Connection).where(Connection.id == connection_id)
        return await self._session.scalar(stmt)

    async def exists_by_channel(self, channel_id: str | int) -> bool:
        """Check if a connection exists for a channel."""
        stmt = (
            select(Connection.id)
            .where(Connection.channelId == str(channel_id))
            .limit(1)
        )
        return (await self._session.scalar(stmt)) is not None

    async def find_existing_connection(
        self, guild_id: str | int, channel_id: str | int
    ) -> Connection | None:
        """Check for existing connection by server OR by channel.

        Used during the connect flow to detect duplicates.
        """
        stmt = select(Connection).where(
            or_(
                Connection.serverId == str(guild_id),
                Connection.channelId == str(channel_id),
            )
        )
        return await self._session.scalar(stmt)

    # Multi-row queries

    async def get_by_server(self, server_id: str | int) -> Sequence[Connection]:
        """Return all connections for a server."""
        stmt = select(Connection).where(Connection.serverId == str(server_id))
        return (await self._session.execute(stmt)).scalars().all()

    # CUD

    async def create(
        self,
        channel_id: str | int,
        guild_id: str | int,
        **kwargs: Unpack[ConnectionCreateKwargs],
    ) -> Connection:
        """Insert a new connection row."""
        connection = Connection(
            channelId=str(channel_id), serverId=str(guild_id), **kwargs
        )
        self._session.add(connection)
        await self._session.flush()
        return connection

    async def update(
        self, channel_id: str | int, **kwargs: Unpack[ConnectionUpdateKwargs]
    ) -> Connection | None:
        """Update an existing connection by channel ID.

        Returns the updated :class:`Connection`, or *None* if not found.
        """
        connection = await self.get_by_channel(str(channel_id))
        if connection is None:
            return None
        for key, value in kwargs.items():
            setattr(connection, key, value)
        self._session.add(connection)
        await self._session.flush()
        return connection

    async def upsert(
        self,
        channel_id: str | int,
        guild_id: str | int,
        **kwargs: Unpack[ConnectionUpdateKwargs],
    ) -> Connection:
        """Create a connection row or update the existing one."""
        connection = await self.get_by_channel(channel_id)
        if connection is None:
            return await self.create(channel_id, guild_id, **kwargs)

        if connection.serverId != str(guild_id):
            connection.serverId = str(guild_id)

        for key, value in kwargs.items():
            setattr(connection, key, value)

        self._session.add(connection)
        await self._session.flush()
        return connection

    async def touch(
        self, channel_id: str | int, *, last_active: datetime | None = None
    ) -> Connection | None:
        """Update the ``lastActive`` timestamp for a connection."""
        return await self.update(
            channel_id, lastActive=last_active or datetime.now(UTC)
        )

    async def set_parent(
        self, channel_id: str | int, parent_id: str | None
    ) -> Connection | None:
        """Set the paired parent channel id."""
        return await self.update(channel_id, parentId=parent_id)

    async def clear_parent(self, channel_id: str | int) -> Connection | None:
        """Clear the paired parent channel id."""
        return await self.update(channel_id, parentId=None)

    async def update_by_id(
        self, connection_id: str, **kwargs: Unpack[ConnectionUpdateKwargs]
    ) -> Connection | None:
        """Update a connection by its primary key ID.

        Returns the updated :class:`Connection`, or *None* if not found.
        """
        connection = await self.get_by_id(connection_id)
        if connection is None:
            return None
        for key, value in kwargs.items():
            setattr(connection, key, value)
        self._session.add(connection)
        await self._session.flush()
        return connection

    async def delete(self, channel_id: str | int) -> bool:
        """Delete a connection by channel ID. Returns *True* if a row was removed."""
        connection = await self.get_by_channel(str(channel_id))
        if connection is None:
            return False
        await self._session.delete(connection)
        await self._session.flush()
        return True

    async def delete_by_server(self, guild_id: str | int) -> None:
        """Delete all connection rows for a server."""
        stmt = delete(Connection).where(Connection.serverId == str(guild_id))
        await self._session.execute(stmt)
        await self._session.flush()

    async def link_both(
        self,
        channel_id: str | int,
        parent_channel_id: str | int,
    ) -> tuple[Connection | None, Connection | None]:
        """Write a two-way parent link between two channels in one flush."""
        left = await self.get_by_channel(channel_id)
        right = await self.get_by_channel(parent_channel_id)

        if left is not None:
            left.parentId = str(parent_channel_id)
            self._session.add(left)

        if right is not None:
            right.parentId = str(channel_id)
            self._session.add(right)

        await self._session.flush()
        return left, right

    async def unlink_both(
        self,
        channel_id: str | int,
        partner_channel_id: str | None,
    ) -> tuple[Connection | None, Connection | None]:
        """Clear a two-way parent link for a channel pair in one flush."""
        left = await self.get_by_channel(channel_id)
        right = None

        if left is not None:
            left.parentId = None
            self._session.add(left)

        if partner_channel_id is not None:
            right = await self.get_by_channel(partner_channel_id)
            if right is not None:
                right.parentId = None
                self._session.add(right)

        await self._session.flush()
        return left, right
