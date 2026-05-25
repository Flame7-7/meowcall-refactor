import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from repositories.connectionRepository import ConnectionRepository
from repositories.userphoneRepository import UserphoneRepository
from utils import logger, redis_client

if TYPE_CHECKING:
    from models import Connection, UserphoneCall


# Data Classes


@dataclass(frozen=True, slots=True)
class CallStartResult:
    """Returned by :meth:`UserphoneService.start_or_queue_call`."""

    already_in_call: bool
    existing_call_duration: int | None
    matched: bool
    my_call: UserphoneCall | None
    partner_call: UserphoneCall | None


@dataclass(frozen=True, slots=True)
class CallEndResult:
    """Returned by :meth:`UserphoneService.start_or_queue_call`."""

    was_in_call: bool
    duration_seconds: int
    my_call: UserphoneCall | None
    paired_call: UserphoneCall | None


@dataclass(frozen=True, slots=True)
class SkipResult:
    """Returned by :meth:`UserphoneService.skip_and_rematch`."""

    was_in_call: bool
    duration_seconds: int
    rematched: bool
    my_call: UserphoneCall | None
    new_partner_call: UserphoneCall | None
    old_my_call: UserphoneCall | None
    old_partner_call: UserphoneCall | None


@dataclass(frozen=True, slots=True)
class UserphoneStats:
    """Returned by :meth:`UserphoneService.get_user_stats`."""

    total_calls: int
    total_duration_seconds: int


class UserphoneService:
    def __init__(
        self,
        userphone_repository: UserphoneRepository,
        connection_repository: ConnectionRepository,
    ) -> None:
        self._userphone_repository = userphone_repository
        self._connection_repository = connection_repository

    async def get_active_call_for_channel(
        self, channel_id: str
    ) -> UserphoneCall | None:
        """Return the WAITING or ACTIVE call for a channel, if any."""
        return await self._userphone_repository.get_active_call_for_channel(channel_id)

    async def find_waiting_call(
        self,
        exclude_channel_id: str | int,
        exclude_user_id: str | int,
    ) -> UserphoneCall | None:
        """Find the oldest WAITING call that isn't owned by this user/channel.

        Also skips calls whose initiating user is blocked by *exclude_user_id*
        or who has blocked *exclude_user_id*.
        """
        return await self._userphone_repository.find_waiting_call(
            exclude_channel_id, exclude_user_id
        )

    async def create_waiting_call(
        self,
        channel_id: str | int,
        guild_id: str | int,
        user_id: str | int,
    ) -> UserphoneCall:
        """Add this channel to the connection pool."""
        return await self._userphone_repository.create_call(
            channelId=str(channel_id),
            guildId=str(guild_id),
            userId=str(user_id),
        )

    async def pair_calls(
        self,
        call_a: UserphoneCall,
        call_b: UserphoneCall,
    ) -> None:
        """Pair two waiting calls and mark them both ACTIVE."""
        await self._userphone_repository.pair_calls(call_a, call_b)

    async def end_call_for_channel(self, channel_id: str | int) -> UserphoneCall | None:
        """End the active call for a channel and return the call record (or None)."""
        return await self._userphone_repository.end_call_for_channel(channel_id)

    async def end_calls_by_channel_ids(self, channel_ids: list[str | int]) -> None:
        await self._userphone_repository.end_calls_by_channel_ids(channel_ids)

    async def get_paired_call(self, call: UserphoneCall) -> UserphoneCall | None:
        """Return the call paired with this one, if any."""
        return await self._userphone_repository.get_paired_call(call)

    async def get_call_by_id(self, call_id: str) -> UserphoneCall | None:
        """Return a single call row by its id."""
        return await self._userphone_repository.get_call_by_id(call_id)

    async def get_call_history(
        self,
        user_id: str | int | None = None,
        guild_id: str | int | None = None,
        *,
        limit: int | None = None,
    ) -> list[UserphoneCall]:
        """Return a history array of call rows for a user, guild, or both."""
        return await self._userphone_repository.get_call_history(
            user_id=user_id,
            guild_id=guild_id,
            limit=limit,
        )

    # Connection persistence -------------------------------------------------

    async def get_connection(self, channel_id: str | int) -> Connection | None:
        return await self._connection_repository.get_by_channel(channel_id)

    async def ensure_connection(
        self,
        channel_id: str | int,
        guild_id: str | int,
        webhook_url: str,
        *,
        parent_id: str | None = None,
    ) -> Connection:
        """Create or update the persistent connection row for a channel."""
        kwargs: dict[str, str | datetime] = {
            "webhookURL": webhook_url,
            "lastActive": datetime.now(UTC),
        }
        if parent_id is not None:
            kwargs["parentId"] = parent_id

        from repositories.guildRepository import GuildRepository

        guild_repo = GuildRepository(self._connection_repository._session)
        # !! [issue] : [critical]
        # Calling ensure_exists(guild_id) inserts into ServerData without a `name`.
        # why its a problem
        # The `ServerData` table has a `name` column that is NOT NULL. Inserting only the ID without providing the name
        # raises a `NotNullViolationError`, causing database operations for the connection to fail entirely.
        await guild_repo.ensure_exists(guild_id)

        return await self._connection_repository.upsert(channel_id, guild_id, **kwargs)

    async def touch_connection(self, channel_id: str | int) -> Connection | None:
        return await self._connection_repository.touch(channel_id)

    async def link_connections(
        self, channel_id: str | int, parent_channel_id: str | int
    ) -> tuple[Connection | None, Connection | None]:
        """Store a two-way link between paired channels."""
        return await self._connection_repository.link_both(
            channel_id, str(parent_channel_id)
        )

    async def unlink_connections(
        self, channel_id: str | int
    ) -> tuple[Connection | None, Connection | None]:
        """Remove a two-way link for a channel, if one exists."""
        connection = await self._connection_repository.get_by_channel(channel_id)
        if connection is None:
            return None, None

        partner = None
        if connection.parentId:
            partner = await self._connection_repository.get_by_channel(
                connection.parentId
            )

        partner_channel_id = partner.channelId if partner is not None else None
        return await self._connection_repository.unlink_both(
            channel_id, partner_channel_id
        )

    @staticmethod
    def compute_call_duration(call: UserphoneCall) -> int:
        """Return elapsed seconds since the call was created."""
        created_at = call.createdAt
        now = datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return int((now - created_at).total_seconds())

    @staticmethod
    async def set_activity_timestamps(*channel_ids: str) -> None:
        """Set Redis activity timestamps for the given channels."""
        now = str(int(time.time()))
        try:
            async with redis_client.pipeline(transaction=False) as pipe:
                for cid in channel_ids:
                    await pipe.set(
                        f"userphone:activity:{cid}",
                        now,
                        ex=30 * 60,
                    )
                await pipe.execute()
        except Exception:
            logger.debug(
                f"Failed to set activity timestamps for channels {channel_ids}"
            )

    async def start_or_queue_call(
        self,
        channel_id: str | int,
        guild_id: str | int,
        user_id: str | int,
    ) -> CallStartResult:
        """Try to start a call or add the channel to the waiting pool.

        Handles duplicate prevention, partner matching, pairing, activity
        timestamps, and the session commit.
        """
        return await self._userphone_repository.start_or_queue_call_atomic(
            channel_id=channel_id,
            guild_id=guild_id,
            user_id=user_id,
            compute_duration=self.compute_call_duration,
            set_activity_timestamps=self.set_activity_timestamps,
        )

    async def end_call_with_info(self, channel_id: str | int) -> CallEndResult:
        """End the call for *channel_id* and return structured info.

        Commits the session internally.
        """
        call = await self.get_active_call_for_channel(channel_id)
        if not call:
            return CallEndResult(
                was_in_call=False, duration_seconds=0, my_call=None, paired_call=None
            )

        paired = await self.get_paired_call(call)
        duration = self.compute_call_duration(call)

        await self._userphone_repository.end_call_by_instance(call)

        return CallEndResult(
            was_in_call=True,
            duration_seconds=duration,
            my_call=call,
            paired_call=paired,
        )

    async def skip_and_rematch(
        self,
        channel_id: str | int,
        guild_id: str | int,
        user_id: str | int,
    ) -> SkipResult:
        """End the current call and try to immediately match a new partner.

        Uses ``SELECT … FOR UPDATE`` on the active call row to prevent
        concurrent skip/call operations from racing.  Commits the session
        internally.
        """
        return await self._userphone_repository.skip_and_rematch_atomic(
            channel_id=channel_id,
            guild_id=guild_id,
            user_id=user_id,
            compute_duration=self.compute_call_duration,
            set_activity_timestamps=self.set_activity_timestamps,
        )

    async def get_user_stats(self, user_id: str | int) -> UserphoneStats:
        """Aggregate call statistics for a user."""
        stats = await self._userphone_repository.get_user_call_stats(str(user_id))
        return UserphoneStats(
            total_calls=stats["total_calls"],
            total_duration_seconds=stats["total_duration_seconds"],
        )

    # Cleanup helpers (used by tasks)

    async def cleanup_all_active_calls(self) -> int:
        """Delete all ACTIVE calls (startup stale-state cleanup).

        Commits the session.  Returns the number of calls deleted.
        """
        return await self._userphone_repository.delete_all_active_calls()

    async def end_orphaned_calls(self) -> list[str]:
        """End every ACTIVE call whose partner has gone away.

        Commits the session.  Returns the channel IDs of ended calls so the
        caller can dispatch Discord notifications outside of the DB session.
        """
        return await self._userphone_repository.end_all_orphaned_active_calls()

    async def get_active_paired_calls(self) -> list[UserphoneCall]:
        """Return all ACTIVE calls that have a paired partner."""
        return await self._userphone_repository.get_active_paired_calls()
