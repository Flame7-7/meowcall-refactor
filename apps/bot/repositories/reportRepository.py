from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack

from models import Report
from sqlalchemy import select

if TYPE_CHECKING:
    from ._types import ReportCreateKwargs

from .baseRepository import BaseRepository


class ReportRepository(BaseRepository):
    """Repository for :class:`Report` queries."""

    async def get_report_by_id(self, report_id: str) -> Report | None:
        stmt = select(Report).where(Report.id == report_id)
        return await self._session.scalar(stmt)

    async def create_report(self, **kwargs: Unpack[ReportCreateKwargs]) -> Report:
        report = Report(**kwargs)
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_reports_referencing_message(
        self, message_id: str
    ) -> Sequence[Report]:
        """Messages referenced by reports cannot be cleaned up. Used by
        ``dataCleanup`` to protect them from deletion."""
        stmt = select(Report).where(Report.messageId == message_id)
        return (await self._session.execute(stmt)).scalars().all()

    async def get_protected_message_ids(self, message_ids: Sequence[str]) -> set[str]:
        """Return the subset of *message_ids* referenced by at least one report."""
        if not message_ids:
            return set()
        stmt = (
            select(Report.messageId)
            .where(Report.messageId.isnot(None))
            .where(Report.messageId.in_(message_ids))
            .distinct()
        )
        results: list[str] = (await self._session.execute(stmt)).scalars().all()  # type: ignore[assignment]
        return set(results)
