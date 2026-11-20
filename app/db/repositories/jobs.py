"""Job queue queries. Claiming locks the row."""

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.jobs import Job, JobStatus

_STALE = timedelta(minutes=2)
DAILY = "daily_content"


class JobRepository:
    """Insert, claim and inspect jobs. No module rules here."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job: Job) -> Job:
        """Insert a job and flush so it has an id."""
        self._session.add(job)
        await self._session.flush()
        return job

    async def taken_slots(self, chat_ids: list[int]) -> set[tuple[int, str, str]]:
        """Slots already used: chat id, job type and slot."""
        if not chat_ids:
            return set()
        stmt = select(Job).where(
            Job.chat_id.in_(chat_ids),
            Job.status != JobStatus.CANCELED,
        )
        result = await self._session.execute(stmt)
        return _slots(list(result.scalars().all()))

    async def has_slot(self, job_type: str, slot: str) -> bool:
        """True when a non-canceled job already uses this type and slot."""
        stmt = (
            select(Job.id)
            .where(
                Job.type == job_type,
                Job.status != JobStatus.CANCELED,
                Job.payload.contains({"slot": slot}),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_for_content(self, job_type: str, content_item_id: int) -> bool:
        """True when a quiz job for this content item already exists."""
        stmt = (
            select(Job.id)
            .where(
                Job.type == job_type,
                Job.payload.contains({"content_item_id": content_item_id}),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def claim(self, now: datetime) -> Job | None:
        """Lock the next due job, including a stale running row."""
        stale = now - _STALE
        stmt = (
            select(Job)
            .where(
                or_(
                    and_(Job.status == JobStatus.PENDING, Job.run_at <= now),
                    and_(Job.status == JobStatus.RUNNING, Job.locked_at < stale),
                )
            )
            .order_by(Job.run_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.locked_at = now
        await self._session.flush()
        return job

    async def count_pending(self) -> int:
        """How many jobs are waiting to run."""
        stmt = select(func.count()).select_from(Job).where(Job.status == JobStatus.PENDING)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_failed_since(self, since: datetime) -> int:
        """Failed jobs whose finish time is at or after `since`."""
        stmt = (
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.FAILED, Job.finished_at >= since)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())


def _slots(rows: list[Job]) -> set[tuple[int, str, str]]:
    found: set[tuple[int, str, str]] = set()
    for row in rows:
        slot = str((row.payload or {}).get("slot", ""))
        if row.chat_id is not None and slot:
            found.add((row.chat_id, row.type, slot))
    return found
