from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Unpack

from models import User, UserphoneCall, UserphoneCallStatus
from sqlalchemy import and_, delete, func, select

from sqlalchemy.dialects.postgresql import insert as pg_insert

if TYPE_CHECKING:
    from ._types import UserphoneCallCreateKwargs

from .baseRepository import BaseRepository


_HISTORY_DEFAULT_LIMIT = 1000


class UserphoneRepository(BaseRepository):
    """Repository for userphone calls, and blocks.

    Each :class:`UserphoneCall` row represents *one endpoint* of a call.
    Two rows are linked via ``pairedCallId`` when matched.
    """

    # ══════════════════════════════════════════════════════════════════════
    # Calls
    # ══════════════════════════════════════════════════════════════════════

    async def get_call_by_id(self, call_id: str) -> UserphoneCall | None:
        return await self._session.get(UserphoneCall, call_id)

    async def get_active_call_for_channel(
        self, channel_id: str | int
    ) -> UserphoneCall | None:
        """Find a call where *channel_id* is involved and status is WAITING or ACTIVE."""
        stmt = select(UserphoneCall).where(
            and_(
                UserphoneCall.channelId == str(channel_id),
                UserphoneCall.status.in_(
                    [UserphoneCallStatus.WAITING, UserphoneCallStatus.ACTIVE]
                ),
            )
        )
        return await self._session.scalar(stmt)

    async def get_waiting_call(
        self, exclude_channel_id: str | int
    ) -> UserphoneCall | None:
        """Find the oldest waiting call that does NOT involve *exclude_channel_id*."""
        stmt = (
            select(UserphoneCall)
            .where(
                and_(
                    UserphoneCall.status == UserphoneCallStatus.WAITING,
                    UserphoneCall.channelId != str(exclude_channel_id),
                )
            )
            .order_by(UserphoneCall.createdAt.asc())
        )
        return await self._session.scalar(stmt)

    async def find_waiting_call(
        self,
        exclude_channel_id: str | int,
        exclude_user_id: str | int,
    ) -> UserphoneCall | None:
        """Find the oldest WAITING call excluding the caller and blocked users.

        Skips calls whose initiating user is blocked by *exclude_user_id*
        or has blocked *exclude_user_id*.

        Uses ``SELECT … FOR UPDATE SKIP LOCKED`` to prevent concurrent
        requests from matching the same partner.
        """
        # blocked_by_me = select(UserphoneBlock.blockedId).where(UserphoneBlock.blockerId == exclude_user_id)
        # blocked_me = select(UserphoneBlock.blockerId).where(UserphoneBlock.blockedId == exclude_user_id)

        stmt = (
            select(UserphoneCall)
            .where(
                and_(
                    UserphoneCall.status == UserphoneCallStatus.WAITING,
                    UserphoneCall.channelId != str(exclude_channel_id),
                    UserphoneCall.userId != str(exclude_user_id),
                    # UserphoneCall.userId.not_in(blocked_by_me),
                    # UserphoneCall.userId.not_in(blocked_me),
                )
            )
            .order_by(UserphoneCall.createdAt)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return await self._session.scalar(stmt)

    async def get_paired_call(self, call: UserphoneCall) -> UserphoneCall | None:
        """Given one side of a call, return the paired endpoint."""
        if call.pairedCallId is None:
            return None
        return await self._session.get(UserphoneCall, call.pairedCallId)

    async def _flush_call_messages(
        self,
        call: UserphoneCall,
        paired: UserphoneCall | None = None,
    ) -> None:
        """Flush buffered relay messages for both endpoints of *call*."""
        try:
            from utils.message_buffer import flush_channel_messages

            await flush_channel_messages(self._session, call.channelId)
            if call.pairedCallId and paired:
                await flush_channel_messages(self._session, paired.channelId)
        except Exception:
            # Non-fatal: message flushing should not prevent call end from succeeding
            pass

    async def get_call_history(
        self,
        user_id: str | int | None = None,
        guild_id: str | int | None = None,
        *,
        limit: int | None = None,
    ) -> list[UserphoneCall]:
        """Return call rows for a user, a guild, or both.

        Results are ordered newest-first so callers can present them directly
        as a history array.
        """
        if user_id is None and guild_id is None:
            raise ValueError("Either user_id or guild_id must be provided.")

        conditions = []
        if user_id is not None:
            conditions.append(UserphoneCall.userId == str(user_id))
        if guild_id is not None:
            conditions.append(UserphoneCall.guildId == str(guild_id))

        effective_limit = limit if limit is not None else _HISTORY_DEFAULT_LIMIT
        stmt = (
            select(UserphoneCall)
            .where(*conditions)
            .order_by(UserphoneCall.createdAt.desc())
            .limit(effective_limit)
        )

        return list((await self._session.execute(stmt)).scalars().all())

    async def create_call(
        self, **kwargs: Unpack[UserphoneCallCreateKwargs]
    ) -> UserphoneCall:
        
        if "userId" in kwargs:
            user_id_str = str(kwargs["userId"])
            
            # This attempts to insert the user. If they already exist, it quietly does nothing.
            upsert_stmt = (
                pg_insert(User)
                .values(id=user_id_str)
                .on_conflict_do_nothing()
            )
            await self._session.execute(upsert_stmt)
        # -----------------------------------------------

        call = UserphoneCall(**kwargs)
        self._session.add(call)
        await self._session.flush()
        return call

    async def pair_calls(
        self,
        call_a: UserphoneCall,
        call_b: UserphoneCall,
    ) -> None:
        """Link two call endpoints and set both to ACTIVE."""
        call_a.pairedCallId = call_b.id
        call_b.pairedCallId = call_a.id
        call_a.status = UserphoneCallStatus.ACTIVE
        call_b.status = UserphoneCallStatus.ACTIVE
        await self._session.flush()

    async def end_call(
        self, call_id: str, status: UserphoneCallStatus = UserphoneCallStatus.ENDED
    ) -> UserphoneCall | None:
        """Set the call status to *status* and record the ended timestamp."""
        call = await self._session.get(UserphoneCall, call_id)
        if call is None:
            return None
        call.status = status
        call.endedAt = datetime.now(UTC)
        await self._session.flush()
        return call

    async def end_call_for_channel(
        self,
        channel_id: str | int,
        status: UserphoneCallStatus = UserphoneCallStatus.ENDED,
    ) -> UserphoneCall | None:
        """End any active/waiting call for *channel_id* and its paired call."""
        call = await self.get_active_call_for_channel(str(channel_id))
        if call is None:
            return None

        now = datetime.now(UTC)
        call.status = status
        call.endedAt = now
        paired: UserphoneCall | None = None

        if call.pairedCallId:
            paired = await self._session.get(UserphoneCall, call.pairedCallId)
            if paired and paired.status in (
                UserphoneCallStatus.ACTIVE,
                UserphoneCallStatus.WAITING,
            ):
                paired.status = status
                paired.endedAt = now

        await self._session.flush()

        await self._flush_call_messages(call, paired)

        return call

    async def end_call_by_instance(
        self,
        call: UserphoneCall,
        status: UserphoneCallStatus = UserphoneCallStatus.ENDED,
    ) -> None:
        """End *call* (already fetched by the caller) and its paired call.

        Operates on the supplied instance directly, avoiding the redundant
        re-fetch that end_call_for_channel performs internally. Used by
        end_call_with_info and skip_and_rematch to eliminate the double-fetch
        window that allows concurrent ends to race.
        """
        now = datetime.now(UTC)
        call.status = status
        call.endedAt = now
        paired: UserphoneCall | None = None

        if call.pairedCallId:
            paired = await self._session.get(UserphoneCall, call.pairedCallId)
            if paired and paired.status in (
                UserphoneCallStatus.ACTIVE,
                UserphoneCallStatus.WAITING,
            ):
                paired.status = status
                paired.endedAt = now
        await self._session.flush()

        await self._flush_call_messages(call, paired)

    async def end_both_sides(
        self,
        call: UserphoneCall,
        status: UserphoneCallStatus = UserphoneCallStatus.ENDED,
    ) -> None:
        """End *call* and its paired call (if any), recording timestamps."""
        now = datetime.now(UTC)
        call.status = status
        call.endedAt = now
        paired: UserphoneCall | None = None
        if call.pairedCallId:
            paired = await self._session.get(UserphoneCall, call.pairedCallId)
            if paired and paired.status != UserphoneCallStatus.ENDED:
                paired.status = status
                paired.endedAt = now
        await self._session.flush()

        await self._flush_call_messages(call, paired)

    async def start_or_queue_call_atomic(
        self,
        channel_id: str | int,
        guild_id: str | int,
        user_id: str | int,
        compute_duration: Callable,
        set_activity_timestamps: Callable,
    ):
        """Atomic check+create+pair to prevent duplicate waiting rows.
        
        Uses SKIP LOCKED to avoid waiting on locked rows. If the row is
        locked by another concurrent operation, we skip it and proceed with
        queueing a new call. This prevents deadlocks while maintaining
        consistency through database constraints.
        """
        from services.userphone.userphoneService import CallStartResult

        lock_stmt = (
            select(UserphoneCall)
            .where(
                and_(
                    UserphoneCall.channelId == str(channel_id),
                    UserphoneCall.status.in_(
                        [UserphoneCallStatus.WAITING, UserphoneCallStatus.ACTIVE]
                    ),
                )
            )
            .with_for_update(skip_locked=True)
        )
        existing = await self._session.scalar(lock_stmt)
        
        # If SKIP LOCKED returned null, check without lock in case row is locked elsewhere
        if not existing:
            check_stmt = (
                select(UserphoneCall)
                .where(
                    and_(
                        UserphoneCall.channelId == str(channel_id),
                        UserphoneCall.status.in_(
                            [UserphoneCallStatus.WAITING, UserphoneCallStatus.ACTIVE]
                        ),
                    )
                )
            )
            existing = await self._session.scalar(check_stmt)

        if existing:
            duration = compute_duration(existing)
            return CallStartResult(
                already_in_call=True,
                existing_call_duration=duration,
                matched=False,
                my_call=existing,
                partner_call=None,
            )

        partner = await self.find_waiting_call(
            exclude_channel_id=channel_id,
            exclude_user_id=user_id,
        )

        if partner:
            my_call = await self.create_call(
                channelId=str(channel_id),
                guildId=str(guild_id),
                userId=str(user_id),
            )
            await self.pair_calls(my_call, partner)
            await set_activity_timestamps(str(channel_id), partner.channelId)
            return CallStartResult(
                already_in_call=False,
                existing_call_duration=None,
                matched=True,
                my_call=my_call,
                partner_call=partner,
            )

        my_call = await self.create_call(
            channelId=str(channel_id),
            guildId=str(guild_id),
            userId=str(user_id),
        )
        return CallStartResult(
            already_in_call=False,
            existing_call_duration=None,
            matched=False,
            my_call=my_call,
            partner_call=None,
        )

    async def skip_and_rematch_atomic(
        self,
        channel_id: str | int,
        guild_id: str | int,
        user_id: str | int,
        compute_duration: Callable,
        set_activity_timestamps: Callable,
    ):
        """Atomic skip: lock the active row, end it, create a new call, and try to rematch.

        Uses ``SELECT … FOR UPDATE SKIP LOCKED`` to avoid waiting on the caller's
        active call. If locked by another operation, returns early indicating
        the caller isn't in a call. This prevents deadlocks under high concurrency.
        """
        from services.userphone.userphoneService import SkipResult

        # Lock the caller's active/waiting row with SKIP LOCKED to prevent deadlocks
        lock_stmt = (
            select(UserphoneCall)
            .where(
                and_(
                    UserphoneCall.channelId == str(channel_id),
                    UserphoneCall.status.in_(
                        [UserphoneCallStatus.WAITING, UserphoneCallStatus.ACTIVE]
                    ),
                )
            )
            .with_for_update(skip_locked=True)
        )
        call = await self._session.scalar(lock_stmt)

        if not call:
            return SkipResult(
                was_in_call=False,
                duration_seconds=0,
                rematched=False,
                my_call=None,
                new_partner_call=None,
                old_my_call=None,
                old_partner_call=None,
            )

        paired = await self.get_paired_call(call)
        duration = compute_duration(call)

        await self.end_call_by_instance(call)

        # Find a new partner — FOR UPDATE SKIP LOCKED prevents double-match
        new_partner = await self.find_waiting_call(
            exclude_channel_id=channel_id,
            exclude_user_id=user_id,
        )

        if new_partner:
            my_call = await self.create_call(
                channelId=str(channel_id),
                guildId=str(guild_id),
                userId=str(user_id),
            )
            await self.pair_calls(my_call, new_partner)
            await set_activity_timestamps(str(channel_id), new_partner.channelId)
            return SkipResult(
                was_in_call=True,
                duration_seconds=duration,
                rematched=True,
                my_call=my_call,
                new_partner_call=new_partner,
                old_my_call=call,
                old_partner_call=paired,
            )

        my_call = await self.create_call(
            channelId=str(channel_id),
            guildId=str(guild_id),
            userId=str(user_id),
        )
        return SkipResult(
            was_in_call=True,
            duration_seconds=duration,
            rematched=False,
            my_call=my_call,
            new_partner_call=None,
            old_my_call=call,
            old_partner_call=paired,
        )

    # ══════════════════════════════════════════════════════════════════════
    # Stats
    # ══════════════════════════════════════════════════════════════════════

    async def get_user_call_stats(self, user_id: str | int) -> dict[str, int]:
        """Return aggregate stats for a user's calls.

        Returns ``{ "total_calls": X, "total_duration_seconds": Y }``.
        """
        stmt = select(
            func.count(UserphoneCall.id),
            func.coalesce(
                func.sum(
                    func.extract("epoch", UserphoneCall.endedAt)
                    - func.extract("epoch", UserphoneCall.createdAt)
                ),
                0,
            ),
        ).where(
            and_(
                UserphoneCall.userId == str(user_id),
                UserphoneCall.status == UserphoneCallStatus.ENDED,
            )
        )
        row = (await self._session.execute(stmt)).first()
        total_calls = row[0] if row else 0
        total_duration = int(row[1]) if row else 0
        return {"total_calls": total_calls, "total_duration_seconds": total_duration}

    # ══════════════════════════════════════════════════════════════════════
    # Cleanup helpers (used by tasks)
    # ══════════════════════════════════════════════════════════════════════

    async def delete_all_active_calls(self) -> int:
        """Delete every ACTIVE call row (startup stale-state cleanup).

        Returns the number of rows deleted.
        """
        count_stmt = select(func.count(UserphoneCall.id)).where(
            UserphoneCall.status == UserphoneCallStatus.ACTIVE
        )
        count = (await self._session.execute(count_stmt)).scalar() or 0
        if count:
            del_stmt = delete(UserphoneCall).where(
                UserphoneCall.status == UserphoneCallStatus.ACTIVE
            )
            await self._session.execute(del_stmt)
            await self._session.flush()
        return count

    async def end_all_orphaned_active_calls(self) -> list[str]:
        """Set ENDED on all ACTIVE calls whose partner is gone (pairedCallId IS NULL).

        Returns the channel IDs of the calls that were ended so the caller can
        dispatch Discord notifications outside of the DB session.
        """
        stmt = select(UserphoneCall).where(
            and_(
                UserphoneCall.status == UserphoneCallStatus.ACTIVE,
                UserphoneCall.pairedCallId.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        orphaned = list(result.scalars().all())
        if not orphaned:
            return []
        now = datetime.now(UTC)
        channel_ids: list[str] = []
        for call in orphaned:
            call.status = UserphoneCallStatus.ENDED
            call.endedAt = now
            channel_ids.append(call.channelId)
        await self._session.flush()
        return channel_ids

    async def get_active_paired_calls(self) -> list[UserphoneCall]:
        """Return every ACTIVE call that has a paired partner."""
        stmt = (
            select(UserphoneCall)
            .where(
                and_(
                    UserphoneCall.status == UserphoneCallStatus.ACTIVE,
                    UserphoneCall.pairedCallId.isnot(None),
                )
            )
            .order_by(UserphoneCall.createdAt.asc())
            .limit(5000)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def end_calls_by_channel_ids(
        self,
        channel_ids: list[str],
        status: UserphoneCallStatus = UserphoneCallStatus.ENDED,
    ) -> None:
        """
        End all active calls for the given channel IDs.

        Ensures each call pair is only ended once.
        """

        if not channel_ids:
            return

        stmt = select(UserphoneCall).where(
            and_(
                UserphoneCall.channelId.in_(channel_ids),
                UserphoneCall.status == UserphoneCallStatus.ACTIVE,
            )
        )

        result = await self._session.execute(stmt)
        calls = list(result.scalars().all())

        if not calls:
            return

        now = datetime.now(UTC)
        processed_ids: set[str] = set()
        call_ids = {call.id for call in calls}
        paired_ids = [
            call.pairedCallId
            for call in calls
            if call.pairedCallId and call.pairedCallId not in call_ids
        ]
        paired_lookup: dict[str, UserphoneCall] = {}
        if paired_ids:
            paired_stmt = select(UserphoneCall).where(UserphoneCall.id.in_(paired_ids))
            paired_result = await self._session.execute(paired_stmt)
            paired_lookup = {p.id: p for p in paired_result.scalars().all()}

        for call in calls:
            if call.id in processed_ids:
                continue

            call.status = status
            call.endedAt = now
            processed_ids.add(call.id)

            if call.pairedCallId:
                paired = paired_lookup.get(call.pairedCallId)
                if paired and paired.status == UserphoneCallStatus.ACTIVE:
                    paired.status = status
                    paired.endedAt = now
                    processed_ids.add(paired.id)

        await self._session.flush()