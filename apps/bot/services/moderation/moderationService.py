from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

import discord
from models import InfractionStatus, InfractionType, ReportStatus
from repositories.moderationRepository import ModerationRepository
from repositories.reportRepository import ReportRepository
from services.baseService import BaseService
from utils import logger, redis_client
from utils.formatting import ms_to_datetime
from utils.redis.cache import CacheManager

if TYPE_CHECKING:
    from models import Blacklist, Infraction, Report, ServerBlacklist, User
    from sqlalchemy.ext.asyncio import AsyncSession

NO_REASON = "No reason provided."


class ModerationService(BaseService):
    def _mod_repo(self) -> ModerationRepository:
        return ModerationRepository(self.session)

    def _report_repo(self) -> ReportRepository:
        return ReportRepository(self.session)

    async def _flush_userphone_access_cache(
        self,
        user_id: str | None = None,
        server_id: str | None = None,
    ) -> None:
        await CacheManager.flush_userphone_access_cache(
            user_id=user_id,
            guild_id=server_id,
        )

    async def notify_user(
        self,
        user: discord.User | discord.Member,
        infraction: Infraction,
    ) -> bool:
        from ui.layouts.commands.moderation.notification import NotificationLayout

        try:
            await user.send(view=NotificationLayout(infraction))
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def get_active_mute(self, user_id: str) -> Infraction | None:
        return await self._mod_repo().get_active_by_type(
            user_id=user_id, guild_id=None, infraction_type=InfractionType.MUTE
        )


    async def create_infraction(
        self,
        mod_id: str,
        user_id: str | None = None,
        server_id: str | None = None,
        server_name: str | None = None,
        infraction_type: InfractionType = InfractionType.BAN,
        reason: str = NO_REASON,
        duration_ms: int | None = None,
    ) -> Infraction:
        if infraction_type in (InfractionType.BAN, InfractionType.MUTE):
            active_infractions = await self._mod_repo().get_active_by_type(
                user_id=user_id, guild_id=server_id, infraction_type=InfractionType.BAN
            )
            if active_infractions:
                raise ValueError("USER_ALREADY_BANNED")
            

        expires_at = ms_to_datetime(duration_ms) if duration_ms else None

        repo = self._mod_repo()
        infraction = await repo.create_infraction(
            moderator_id=mod_id,
            type=infraction_type,
            reason=reason,
            user_id=user_id,
            guild_id=server_id,
            status=InfractionStatus.ACTIVE,
            expiresAt=expires_at,
            serverName=server_name,
        )

        await self.session.flush()
        if infraction_type in (InfractionType.BAN, InfractionType.MUTE):
            await self._flush_userphone_access_cache(user_id, server_id)
        return infraction

    async def list_infractions(
        self,
        filter_type: Literal["users", "servers"] = "users",
        page: int = 0,
        per_page: int = 5,
        specific_user_id: str | None = None,
        specific_server_id: str | None = None,
    ) -> tuple[list[Infraction], int]:
        repo = self._mod_repo()
        infractions, total_count = await repo.list_infractions_with_count(
            filter_type=filter_type,
            specific_user_id=specific_user_id,
            specific_guild_id=specific_server_id,
            page=page,
            per_page=per_page,
        )
        return list(infractions), total_count

    async def revoke_infraction(
        self,
        infraction_id: str,
        mod_id: str,
        reason: str | None = NO_REASON,
    ) -> Infraction | None:
        repo = self._mod_repo()
        infraction = await repo.get_infraction_by_id(infraction_id)

        if not infraction:
            return None

        safe_reason = reason or NO_REASON
        new_reason = infraction.reason + f" | Revoked by {mod_id}: {safe_reason}"
        await repo.update_infraction(
            infraction_id, status=InfractionStatus.REVOKED, reason=new_reason
        )
        await self.session.flush()
        if infraction.type in (InfractionType.BAN, InfractionType.MUTE):
            await self._flush_userphone_access_cache(
                getattr(infraction, "userId", None),
                getattr(infraction, "serverId", None),
            )

        return infraction

    async def delete_infraction(self, infraction_id: str) -> Infraction | None:
        repo = self._mod_repo()
        infraction = await repo.get_infraction_by_id(infraction_id)

        if not infraction:
            return None

        await repo.delete_infraction(infraction_id)
        await self.session.flush()
        if infraction.type in (InfractionType.BAN, InfractionType.MUTE):
            await self._flush_userphone_access_cache(
                getattr(infraction, "userId", None),
                getattr(infraction, "serverId", None),
            )
        return infraction

    async def is_user_banned(self, user_id: str) -> bool:
        infractions = await self._mod_repo().get_active_by_type(user_id=user_id, infraction_type=InfractionType.BAN)
        return bool(infractions)

    async def is_server_banned(self, server_id: str) -> bool:
        infractions = await self._mod_repo().get_active_by_type(guild_id=server_id, infraction_type=InfractionType.BAN)
        return bool(infractions)

    async def create_blacklist_entry(
        self,
        user_id: str,
        mod_id: str,
        reason: str = NO_REASON,
        duration_ms: int | None = None,
    ) -> Blacklist:
        repo = self._mod_repo()
        if await repo.is_user_blacklisted(user_id):
            raise ValueError("DUPLICATE_GLOBAL_BLACKLIST_USER")

        blacklist = await repo.create_blacklist_entry(
            user_id=user_id,
            moderator_id=mod_id,
            reason=reason,
            duration_ms=duration_ms,
        )
        await self.session.flush()
        await redis_client.delete(f"blacklist:{user_id}")
        return blacklist

    async def create_server_blacklist_entry(
        self,
        server_id: str,
        mod_id: str,
        reason: str = NO_REASON,
        duration_ms: int | None = None,
    ) -> ServerBlacklist:
        repo = self._mod_repo()
        if await repo.is_server_blacklisted(server_id):
            raise ValueError("DUPLICATE_GLOBAL_BLACKLIST_SERVER")

        blacklist = await repo.create_server_blacklist_entry(
            server_id=server_id,
            moderator_id=mod_id,
            reason=reason,
            duration_ms=duration_ms,
        )
        await self.session.flush()
        await self._flush_userphone_access_cache(server_id=server_id)
        return blacklist

    async def is_user_blacklisted(self, user_id: str) -> bool:
        return await self._mod_repo().is_user_blacklisted(user_id)

    async def is_server_blacklisted(self, server_id: str) -> bool:
        return await self._mod_repo().is_server_blacklisted(server_id)

    async def delete_blacklist_entry(self, user_id: str) -> bool:
        repo = self._mod_repo()
        deleted = await repo.delete_all_user_blacklists(user_id)

        if not deleted:
            return False

        await self.session.flush()
        await redis_client.delete(f"blacklist:{user_id}")

        pattern = f"access_check:*:{user_id}:*"
        try:
            async for key in redis_client.scan_iter(pattern):
                await redis_client.delete(key)
        except Exception as e:
            logger.debug(f"Failed to clear blacklist cache: {e}")

        return True

    async def delete_server_blacklist_entry(self, server_id: str) -> bool:
        repo = self._mod_repo()
        deleted = await repo.delete_server_blacklist_entry(server_id)

        if not deleted:
            return False

        await self.session.flush()

        pattern = f"access_check:*:*:{server_id}"
        try:
            async for key in redis_client.scan_iter(pattern):
                await redis_client.delete(key)
        except Exception as e:
            logger.debug(f"Failed to clear server blacklist cache: {e}")

        return True

    async def _get_infraction_names(
        self,
        infraction_id: str,
        *,
        session: AsyncSession | None = None,
    ) -> tuple[str, str, str, str] | None:
        repo = ModerationRepository(session) if session else self._mod_repo()
        return await repo.get_infraction_names(infraction_id)

    async def search_blacklisted_targets_autocomplete(
        self,
        current: str,
        *,
        user_limit: int = 12,
        server_limit: int = 13,
    ) -> tuple[Sequence[tuple[str, str | None]], Sequence[tuple[str, str | None]]]:
        return await self._mod_repo().search_blacklisted_targets_autocomplete(
            current, user_limit=user_limit, server_limit=server_limit
        )

    async def search_blacklist_moderators_autocomplete(
        self, current: str, limit: int = 25
    ) -> Sequence[User]:
        return await self._mod_repo().search_blacklist_moderators_autocomplete(
            current, limit=limit
        )

    async def update_report_status(
        self,
        report_id: str,
        *,
        status: ReportStatus,
        handler_id: str | None = None,
        action_taken: str | None = None,
    ) -> Report | None:
        result = await self._report_repo().update_report_status(
            report_id, status=status, handler_id=handler_id, action_taken=action_taken
        )
        await self.session.flush()
        return result

    async def create_report(
        self,
        reporter_id: str,
        reported_user_id: str,
        reported_server_id: str,
        message_id: str | None,
        reason: str,
    ) -> Report:
        repo = self._report_repo()
        report = await repo.create_report(
            reporterId=reporter_id,
            reportedUserId=reported_user_id,
            reportedServerId=reported_server_id,
            messageId=message_id,
            reason=reason,
        )
        await self.session.flush()
        return report

    async def update_report_channel(
        self,
        report_id: str,
        *,
        message_id: str,
        channel_id: str,
    ) -> None:
        report = await self._report_repo().get_report_by_id(report_id)
        if report:
            report.reportMessageId = message_id
            report.reportChannelId = channel_id
            await self.session.flush()
