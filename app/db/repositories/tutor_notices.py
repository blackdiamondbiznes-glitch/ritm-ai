"""Tutor notice rows and the scans that find work. No send rules here."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.groups import TutorGroup
from app.db.models.invoices import TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.tutor_notices import TutorNotice


class TutorNoticeRepository:
    """Claim one delivery and list the lessons and invoices the planner reads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self, kind: str, ref_id: int, target: str, target_id: int, status: str
    ) -> int | None:
        """Insert the row once. A conflict means this event already has a delivery."""
        stmt = (
            insert(TutorNotice)
            .values(kind=kind, ref_id=ref_id, target=target, target_id=target_id, status=status)
            .on_conflict_do_nothing(index_elements=["kind", "ref_id", "target", "target_id"])
            .returning(TutorNotice.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get(self, notice_id: int) -> TutorNotice | None:
        """One delivery row."""
        result = await self._session.execute(select(TutorNotice).where(TutorNotice.id == notice_id))
        return result.scalar_one_or_none()

    async def save(self, row: TutorNotice) -> TutorNotice:
        """Flush a status change."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def lessons_soon(
        self, now: datetime, until: datetime
    ) -> list[tuple[TutorLesson, TutorGroup]]:
        """Scheduled group sessions that start inside the longest reminder window."""
        stmt = (
            select(TutorLesson, TutorGroup)
            .join(TutorGroup, TutorGroup.id == TutorLesson.group_id)
            .where(
                TutorLesson.status == "scheduled",
                TutorLesson.starts_at.is_not(None),
                TutorLesson.starts_at > now,
                TutorLesson.starts_at <= until,
                TutorGroup.remind_lesson_min.is_not(None),
            )
            .order_by(TutorLesson.starts_at.asc(), TutorLesson.id.asc())
        )
        result = await self._session.execute(stmt)
        return [(lesson, group) for lesson, group in result.all()]

    async def lessons_started(
        self, start: datetime, end: datetime
    ) -> list[tuple[TutorLesson, TutorGroup]]:
        """Group sessions that began in [start, end], for the teacher's roll card."""
        stmt = (
            select(TutorLesson, TutorGroup)
            .join(TutorGroup, TutorGroup.id == TutorLesson.group_id)
            .where(
                TutorLesson.group_id.is_not(None),
                TutorLesson.starts_at.is_not(None),
                TutorLesson.starts_at >= start,
                TutorLesson.starts_at <= end,
                TutorLesson.status.in_(("scheduled", "done")),
            )
            .order_by(TutorLesson.starts_at.asc(), TutorLesson.id.asc())
        )
        result = await self._session.execute(stmt)
        return [(lesson, group) for lesson, group in result.all()]

    async def fee_groups(self) -> list[TutorGroup]:
        """Groups that still want a fee reminder."""
        stmt = select(TutorGroup).where(TutorGroup.remind_fee_days.is_not(None))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def open_invoices(self, group_ids: list[int]) -> list[TutorInvoice]:
        """Unpaid invoices for these groups."""
        if not group_ids:
            return []
        stmt = select(TutorInvoice).where(
            TutorInvoice.group_id.in_(group_ids),
            TutorInvoice.status.notin_(("paid", "waived")),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
