"""Tutor reminders: the owner writes one, and one job delivers it."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models.jobs import Job, JobStatus
from app.db.models.reminders import TutorReminder
from app.db.models.students import TutorStudent
from app.db.repositories.jobs import JobRepository
from app.db.repositories.reminders import ReminderRepository
from app.db.repositories.students import StudentRepository
from app.services.clock import TASHKENT, utcnow

REMINDER = "tutor_reminder"
TEXT_MAX = 300
_SPACE = re.compile(r"\s+")
_WHEN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})$")


class ReminderError(Exception):
    """Invalid reminder input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ReminderInput:
    """Validated reminder fields."""

    text: str
    student_id: int | None
    send_at: datetime


class ReminderService:
    """Save reminders and queue each one once."""

    def __init__(
        self,
        reminders: ReminderRepository,
        students: StudentRepository,
        jobs: JobRepository | None = None,
        now=utcnow,
    ) -> None:
        self._reminders = reminders
        self._students = students
        self._jobs = jobs
        self._now = now

    async def list(self, owner_id: int) -> dict:
        """Every reminder of this owner, plus students that can be attached."""
        rows = await self._reminders.list_for_owner(owner_id)
        students = await self._students.list_for_owner(owner_id)
        return _payload(rows, students)

    async def create(self, owner_id: int, body: dict) -> dict:
        """Store a reminder. The job is created later, when it is due."""
        parsed = parse_reminder(body)
        await self._owned_student(owner_id, parsed.student_id)
        await self._reminders.add(
            TutorReminder(
                owner_id=owner_id,
                student_id=parsed.student_id,
                text=parsed.text,
                send_at=parsed.send_at,
            )
        )
        return await self.list(owner_id)

    async def remove(self, owner_id: int, reminder_id: int) -> dict:
        """Delete one of this owner's reminders."""
        row = await self._reminders.get_owned(owner_id, reminder_id)
        if row is None:
            raise ReminderError("missing")
        await self._reminders.delete(row)
        return await self.list(owner_id)

    async def enqueue_due(self, now: datetime | None = None) -> int:
        """Queue each due reminder once. A second call adds nothing."""
        if self._jobs is None:
            return 0
        moment = now or self._now()
        made = 0
        for row in await self._reminders.due(moment):
            await self._jobs.add(
                Job(
                    chat_id=None,
                    type=REMINDER,
                    payload={"reminder_id": row.id},
                    run_at=moment,
                    status=JobStatus.PENDING,
                    attempts=0,
                    max_attempts=5,
                )
            )
            row.queued_at = moment
            await self._reminders.save(row)
            made += 1
        return made

    async def _owned_student(self, owner_id: int, student_id: int | None) -> None:
        if student_id is None:
            return
        if await self._students.get_owned(owner_id, student_id) is None:
            raise ReminderError("student")


def parse_reminder(body: dict) -> ReminderInput:
    """Validate a new reminder. The time is a Tashkent wall clock."""
    text = _text(body.get("text"))
    student_id = _student_id(body.get("student_id")) if "student_id" in body else None
    if "send_at" not in body or body.get("send_at") in (None, ""):
        raise ReminderError("when")
    return ReminderInput(text=text, student_id=student_id, send_at=_when(body.get("send_at")))


def _payload(rows: list[TutorReminder], students: list[TutorStudent]) -> dict:
    names = {row.id: row.name for row in students}
    items = [
        {
            "id": row.id,
            "text": row.text,
            "student_id": row.student_id,
            "student_name": names.get(row.student_id) if row.student_id else None,
            "send_at": row.send_at.isoformat(),
            "sent": row.sent_at is not None,
        }
        for row in rows
    ]
    brief = [{"id": row.id, "name": row.name} for row in students]
    brief.sort(key=lambda item: item["name"].casefold())
    return {"reminders": items, "students": brief}


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ReminderError("empty")
    text = _SPACE.sub(" ", value).strip()
    if not text:
        raise ReminderError("empty")
    if len(text) > TEXT_MAX:
        raise ReminderError("long")
    return text


def _student_id(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReminderError("student")
    return value


def _when(value: object) -> datetime:
    if not isinstance(value, str):
        raise ReminderError("when")
    match = _WHEN.fullmatch(value.strip())
    if match is None:
        raise ReminderError("when")
    year, month, day, hour, minute = (int(part) for part in match.groups())
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=TASHKENT)
    except ValueError as exc:
        raise ReminderError("when") from exc
    return local.astimezone(UTC)
