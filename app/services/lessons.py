"""Tutor cabinet lessons, optionally tied to one of the owner's students."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.students import StudentRepository
from app.services.clock import TASHKENT
from app.services.workspaces import WorkspaceService

STATUSES = frozenset({"scheduled", "done", "cancelled"})
TITLE_MAX = 120
NOTE_MAX = 300
AMOUNT_MAX = 1_000_000_000
_SPACE = re.compile(r"\s+")
_WHEN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})$")


class LessonError(Exception):
    """Invalid lesson input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LessonInput:
    """Validated lesson fields."""

    title: str
    student_id: int | None
    status: str
    amount_uzs: int
    starts_at: datetime | None
    note: str | None


class LessonService:
    """Create, edit and list lessons for one owner."""

    def __init__(
        self,
        lessons: LessonRepository,
        students: StudentRepository,
        spaces: WorkspaceService | None = None,
    ) -> None:
        self._lessons = lessons
        self._students = students
        self._spaces = spaces

    async def list(self, owner_id: int) -> dict:
        """Every lesson of this owner, plus the students that can be attached."""
        lessons = await self._lessons.list_for_owner(owner_id)
        students = await self._students.list_for_owner(owner_id)
        return _payload(lessons, students)

    async def create(self, owner_id: int, body: dict) -> dict:
        """Store a new lesson. A missing status starts as scheduled."""
        parsed = parse_lesson(body)
        await self._owned_student(owner_id, parsed.student_id)
        now = datetime.now(UTC)
        workspace_id = await self._spaces.id_for(owner_id) if self._spaces is not None else 0
        await self._lessons.add(
            TutorLesson(
                owner_id=owner_id,
                workspace_id=workspace_id,
                student_id=parsed.student_id,
                title=parsed.title,
                status=parsed.status,
                source="manual",
                amount_uzs=parsed.amount_uzs,
                starts_at=parsed.starts_at,
                note=parsed.note,
                created_at=now,
                updated_at=now,
            )
        )
        return await self.list(owner_id)

    async def update(self, owner_id: int, lesson_id: int, body: dict) -> dict:
        """Change the fields present in `body`. Other fields stay as they are."""
        row = await self._lessons.get_owned(owner_id, lesson_id)
        if row is None:
            raise LessonError("missing")
        parsed = parse_lesson(body, current=row)
        await self._owned_student(owner_id, parsed.student_id)
        row.title = parsed.title
        row.student_id = parsed.student_id
        row.status = parsed.status
        row.amount_uzs = parsed.amount_uzs
        row.starts_at = parsed.starts_at
        row.note = parsed.note
        row.updated_at = datetime.now(UTC)
        await self._lessons.save(row)
        return await self.list(owner_id)

    async def remove(self, owner_id: int, lesson_id: int) -> dict:
        """Delete one of this owner's lessons."""
        row = await self._lessons.get_owned(owner_id, lesson_id)
        if row is None:
            raise LessonError("missing")
        await self._lessons.delete(row)
        return await self.list(owner_id)

    async def _owned_student(self, owner_id: int, student_id: int | None) -> None:
        if student_id is None:
            return
        if await self._students.get_owned(owner_id, student_id) is None:
            raise LessonError("student")


def parse_lesson(body: dict, current: TutorLesson | None = None) -> LessonInput:
    """Validate a create body, or a partial update when `current` is set."""
    if "title" in body or current is None:
        title = _title(body.get("title"))
    else:
        title = current.title
    if "student_id" in body or current is None:
        student_id = _student_id(body.get("student_id"))
    else:
        student_id = current.student_id
    if "status" in body or current is None:
        status = _status(body.get("status", "scheduled"))
    else:
        status = current.status
    if "amount_uzs" in body:
        amount = _amount(body["amount_uzs"])
    elif current is None:
        amount = 0
    else:
        amount = current.amount_uzs
    if "starts_at" in body or current is None:
        starts_at = _when(body.get("starts_at"))
    else:
        starts_at = current.starts_at
    if "note" in body or current is None:
        note = _note(body.get("note"))
    else:
        note = current.note
    return LessonInput(
        title=title,
        student_id=student_id,
        status=status,
        amount_uzs=amount,
        starts_at=starts_at,
        note=note,
    )


def _payload(lessons: list[TutorLesson], students: list[TutorStudent]) -> dict:
    names = {row.id: row.name for row in students}
    counts = {"scheduled": 0, "done": 0, "cancelled": 0}
    items = []
    for row in lessons:
        counts[row.status] = counts.get(row.status, 0) + 1
        items.append(
            {
                "id": row.id,
                "title": row.title,
                "student_id": row.student_id,
                "student_name": names.get(row.student_id) if row.student_id else None,
                "status": row.status,
                "amount_uzs": row.amount_uzs,
                "starts_at": row.starts_at.isoformat() if row.starts_at else None,
                "note": row.note,
            }
        )
    brief = [{"id": row.id, "name": row.name} for row in students]
    brief.sort(key=lambda item: item["name"].casefold())
    return {"lessons": items, "counts": counts, "students": brief}


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise LessonError("empty")
    text = _SPACE.sub(" ", value).strip()
    if not text:
        raise LessonError("empty")
    if len(text) > TITLE_MAX:
        raise LessonError("long")
    return text


def _student_id(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LessonError("student")
    return value


def _status(value: object) -> str:
    if not isinstance(value, str) or value not in STATUSES:
        raise LessonError("choice")
    return value


def _amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LessonError("amount")
    if value < 0 or value > AMOUNT_MAX:
        raise LessonError("amount")
    return value


def _when(value: object) -> datetime | None:
    """Read a Tashkent wall time `YYYY-MM-DDTHH:MM` and store it in UTC."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise LessonError("when")
    match = _WHEN.fullmatch(value.strip())
    if match is None:
        raise LessonError("when")
    year, month, day, hour, minute = (int(part) for part in match.groups())
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=TASHKENT)
    except ValueError as exc:
        raise LessonError("when") from exc
    return local.astimezone(UTC)


def _note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LessonError("note")
    text = value.strip()
    if not text:
        return None
    if len(text) > NOTE_MAX:
        raise LessonError("note")
    return text
