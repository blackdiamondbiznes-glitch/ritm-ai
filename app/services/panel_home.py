"""Teacher panel home: only what needs attention, read in a fixed number of queries."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.services.clock import TASHKENT, Clock, utcnow

UNMARKED_DAYS = 7
LIST_MAX = 5
OPEN = ("due", "overdue")


class PanelHome:
    """Exceptions for one teacher: today, unmarked attendance, overdue fees, requests, income."""

    def __init__(self, session: AsyncSession, now: Clock | None = None) -> None:
        self._session = session
        self._now = now or utcnow

    async def for_owner(self, owner_id: int) -> dict:
        now = self._now()
        local = now.astimezone(TASHKENT)
        today = local.date()
        start = datetime.combine(today, time.min, tzinfo=TASHKENT)
        return {
            "today": today.isoformat(),
            "lessons": await self._today(owner_id, start, start + timedelta(days=1)),
            "unmarked": await self._unmarked(owner_id, now),
            "overdue": await self._overdue(owner_id, today),
            "requests": await self._requests(owner_id),
            "homework": None,
            "income": await self._income(owner_id, today.replace(day=1)),
        }

    async def _today(self, owner_id: int, start: datetime, end: datetime) -> list[dict]:
        seats = (
            select(func.count(TutorGroupMember.id))
            .where(TutorGroupMember.group_id == TutorLesson.group_id)
            .where(TutorGroupMember.status == "active")
            .correlate(TutorLesson)
            .scalar_subquery()
        )
        stmt = (
            select(TutorLesson, TutorGroup.name, TutorGroup.level, seats, _marked())
            .outerjoin(TutorGroup, TutorGroup.id == TutorLesson.group_id)
            .where(
                TutorLesson.owner_id == owner_id,
                TutorLesson.starts_at >= start,
                TutorLesson.starts_at < end,
                TutorLesson.status != "cancelled",
            )
            .order_by(TutorLesson.starts_at.asc(), TutorLesson.id.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "id": lesson.id,
                "group_id": lesson.group_id,
                "title": name or lesson.title,
                "level": level,
                "starts_at": lesson.starts_at.isoformat(),
                "ends_at": lesson.ends_at.isoformat() if lesson.ends_at else None,
                "students": int(count or 0) if lesson.group_id else 1,
                "meeting_url": lesson.meeting_url,
                "marked": bool(marked),
            }
            for lesson, name, level, count, marked in rows
        ]

    async def _unmarked(self, owner_id: int, now: datetime) -> dict:
        ended = func.coalesce(TutorLesson.ends_at, TutorLesson.starts_at)
        stmt = (
            select(TutorLesson, TutorGroup.name)
            .outerjoin(TutorGroup, TutorGroup.id == TutorLesson.group_id)
            .where(
                TutorLesson.owner_id == owner_id,
                TutorLesson.group_id.is_not(None),
                TutorLesson.status != "cancelled",
                TutorLesson.starts_at >= now - timedelta(days=UNMARKED_DAYS),
                ended < now,
                ~_marked(),
            )
            .order_by(TutorLesson.starts_at.desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return {
            "count": len(rows),
            "items": [
                {
                    "id": lesson.id,
                    "title": name or lesson.title,
                    "starts_at": lesson.starts_at.isoformat(),
                }
                for lesson, name in rows[:LIST_MAX]
            ],
        }

    async def _overdue(self, owner_id: int, today: date) -> dict:
        late = or_(
            TutorInvoice.status == "overdue",
            and_(TutorInvoice.status == "due", TutorInvoice.due_on < today),
        )
        stmt = (
            select(
                func.count(TutorInvoice.id),
                func.coalesce(func.sum(TutorInvoice.amount_uzs - TutorInvoice.paid_uzs), 0),
            )
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .where(TutorGroup.owner_id == owner_id, late)
        )
        count, total = (await self._session.execute(stmt)).one()
        return {"count": int(count), "sum_uzs": int(total)}

    async def _requests(self, owner_id: int) -> dict:
        stmt = (
            select(TutorStudent.name, TutorGroup.name)
            .select_from(TutorGroupMember)
            .join(TutorGroup, TutorGroup.id == TutorGroupMember.group_id)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .where(TutorGroup.owner_id == owner_id, TutorGroupMember.status == "pending")
            .order_by(TutorGroupMember.created_at.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        first = rows[0] if rows else None
        return {
            "count": len(rows),
            "first": {"student": first[0], "group": first[1]} if first else None,
        }

    async def _income(self, owner_id: int, month_start: date) -> dict:
        stmt = (
            select(
                func.coalesce(func.sum(TutorFeePayment.amount_uzs), 0),
                func.count(TutorFeePayment.id),
            )
            .join(TutorInvoice, TutorInvoice.id == TutorFeePayment.invoice_id)
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .where(TutorGroup.owner_id == owner_id, TutorFeePayment.paid_on >= month_start)
        )
        total, count = (await self._session.execute(stmt)).one()
        return {"month": month_start.isoformat()[:7], "sum_uzs": int(total), "payments": int(count)}


def _marked():
    return exists().where(TutorAttendance.lesson_id == TutorLesson.id)
