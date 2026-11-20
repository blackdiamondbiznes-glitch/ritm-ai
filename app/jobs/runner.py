"""Claim one job per tick. Business rules live in the handler, not the clock."""

import logging
from datetime import timedelta

from app.ai.errors import AIConfigError, AITransient
from app.db.models.jobs import Job, JobStatus
from app.db.repositories.jobs import JobRepository
from app.db.repositories.schedules import DueRow, ScheduleRepository
from app.jobs.collect import Row, collect_due
from app.logging_setup import set_correlation
from app.services.clock import Clock, utcnow

logger = logging.getLogger(__name__)
_BACKOFF = 30


class JobCancel(Exception):
    """A permanent skip: quota, missing profile, dead chat."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JobRunner:
    """Enqueue due slots, then finish a single claimed job."""

    def __init__(
        self,
        schedules: ScheduleRepository,
        jobs: JobRepository,
        handlers: dict[str, object],
        now: Clock | None = None,
    ) -> None:
        self._schedules = schedules
        self._jobs = jobs
        self._handlers = handlers
        self._now = now or utcnow

    async def run_once(self) -> None:
        """One scheduler wake-up."""
        now = self._now()
        await self._enqueue(now)
        job = await self._jobs.claim(now)
        if job is None:
            return
        set_correlation(f"job:{job.id}")
        try:
            await self._finish(job, now)
        finally:
            set_correlation("-")

    async def _enqueue(self, now: object) -> None:
        rows = await self._schedules.list_due_rows()
        taken = await self._jobs.taken_slots([row.chat_id for row in rows])
        modules = {row.module for row in rows}
        for module in modules:
            subset = [row for row in rows if row.module == module]
            used = {(chat_id, slot) for chat_id, kind, slot in taken if kind == module}
            due = collect_due(now, [_row(row) for row in subset], used)  # type: ignore[arg-type]
            for slot in due:
                job = _pending(slot.chat_id, slot.schedule_id, slot.slot, module, now)
                await self._jobs.add(job)
                logger.info("queued type=%s chat_id=%s slot=%s", module, slot.chat_id, slot.slot)

    async def _finish(self, job: Job, now: object) -> None:
        try:
            handler = self._handlers.get(job.type)
            if handler is None:
                raise JobCancel("type")
            await handler.handle(job)  # type: ignore[attr-defined]
        except JobCancel as exc:
            _cancel(job, exc.code, now)
            logger.info("job canceled id=%s code=%s", job.id, exc.code)
        except AIConfigError as exc:
            _cancel(job, exc.code, now)
            logger.info("job canceled id=%s code=%s error=AIConfigError", job.id, exc.code)
        except AITransient as exc:
            _retry(job, exc, now)
            logger.info("job retry id=%s error=%s", job.id, type(exc).__name__)
        except Exception as exc:
            _retry(job, exc, now)
            logger.info("job retry id=%s error=%s", job.id, type(exc).__name__)
        else:
            job.status = JobStatus.DONE
            job.finished_at = now  # type: ignore[assignment]
            job.last_error = None
            logger.info("job done id=%s type=%s", job.id, job.type)


def _row(row: DueRow) -> Row:
    return Row(row.schedule_id, row.chat_id, row.timezone, row.time_of_day, row.days)


def _pending(chat_id: int, schedule_id: int, slot: str, module: str, now: object) -> Job:
    return Job(
        chat_id=chat_id,
        type=module,
        payload={"slot": slot, "schedule_id": schedule_id},
        run_at=now,  # type: ignore[arg-type]
        status=JobStatus.PENDING,
        attempts=0,
        max_attempts=5,
    )


def _cancel(job: Job, code: str, now: object) -> None:
    job.status = JobStatus.CANCELED
    job.last_error = code[:500]
    job.finished_at = now  # type: ignore[assignment]
    job.locked_at = None


def _retry(job: Job, exc: Exception, now: object) -> None:
    job.attempts = int(job.attempts) + 1
    job.last_error = type(exc).__name__[:500]
    job.locked_at = None
    if job.attempts >= int(job.max_attempts):
        job.status = JobStatus.FAILED
        job.finished_at = now  # type: ignore[assignment]
        return
    job.status = JobStatus.PENDING
    job.run_at = now + timedelta(seconds=_BACKOFF * job.attempts)  # type: ignore[operator]
