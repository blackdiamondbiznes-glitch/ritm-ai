"""Group attendance.

The rate is (present + late) / marked sessions. Excused counts as marked
but not attended. A session with no mark is left out of both numbers.
An empty status clears the mark.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.db.models.attendance import TutorAttendance
from app.db.models.lessons import TutorLesson
from app.db.models.users import User
from app.db.repositories.attendance import AttendanceRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.services.clock import TASHKENT, Clock, utcnow

STATUSES = frozenset({"present", "absent", "late", "excused"})
ATTENDED = frozenset({"present", "late"})
NOTE_MAX = 200
HISTORY = 30
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


class AttendanceError(Exception):
    """Invalid attendance input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def attendance_rate(statuses: list[str | None]) -> dict:
    """Return attended, marked, and the rate.

    Excused increments marked and does not increment attended.
    """
    marked = 0
    attended = 0
    for status in statuses:
        if status not in STATUSES:
            continue
        marked += 1
        if status in ATTENDED:
            attended += 1
    rate = None if marked == 0 else attended / marked
    return {"attended": attended, "marked": marked, "rate": rate}


class AttendanceService:
    """Mark a session, summarise a month, and show one student their history."""

    def __init__(
        self,
        marks: AttendanceRepository,
        lessons: LessonRepository,
        groups: GroupRepository,
        now: Clock | None = None,
    ) -> None:
        self._marks = marks
        self._lessons = lessons
        self._groups = groups
        self._now = now or utcnow

    async def sheet(self, owner_id: int, lesson_id: int) -> dict:
        """Active members of the lesson's group, with the current mark or null."""
        lesson = await self._lesson(owner_id, lesson_id)
        group = await self._groups.get_owned(owner_id, lesson.group_id or 0)
        if group is None:
            raise AttendanceError("missing")
        members = await self._groups.members(group.id)
        stored = {row.student_id: row for row in await self._marks.for_lesson(lesson.id)}
        return _sheet(lesson, group.name, members, stored)

    async def save(self, owner_id: int, lesson_id: int, body: dict) -> dict:
        """Upsert marks for active members. A real mark finishes a scheduled session."""
        lesson = await self._lesson(owner_id, lesson_id)
        if not _started(lesson, self._now()):
            raise AttendanceError("future")
        members = {row.id for row in await self._groups.members(lesson.group_id or 0)}
        planned = _plans(body.get("marks"), members)
        stamp = datetime.now(UTC)
        marked = False
        for student_id, status, note in planned:
            if status is None:
                await self._marks.clear(lesson.id, student_id)
            else:
                await self._marks.upsert(lesson.id, student_id, status, note, stamp)
                marked = True
        if marked and lesson.status == "scheduled":
            lesson.status = "done"
            lesson.updated_at = stamp
            await self._lessons.save(lesson)
        return await self.sheet(owner_id, lesson_id)

    async def group_stats(self, owner_id: int, group_id: int, month: str) -> dict:
        """Students by sessions in one Tashkent month, plus each student's rate."""
        group = await self._groups.get_owned(owner_id, group_id)
        if group is None:
            raise AttendanceError("missing")
        start, end = _month(month)
        lessons = await self._lessons.for_group_between(owner_id, group.id, start, end)
        members = await self._groups.members(group.id)
        stored = await self._marks.for_lessons([row.id for row in lessons])
        by_pair = {(row.lesson_id, row.student_id): row.status for row in stored}
        students = []
        for member in members:
            statuses = [by_pair.get((row.id, member.id)) for row in lessons]
            students.append(
                {
                    "student_id": member.id,
                    "name": member.name,
                    "marks": statuses,
                    **attendance_rate(statuses),
                }
            )
        return {
            "group_id": group.id,
            "name": group.name,
            "month": month,
            "sessions": [_session(row) for row in lessons],
            "students": students,
        }

    async def student_history(self, user: User, group_id: int) -> dict:
        """Last 30 marks and the rate across every mark. Active membership only."""
        if user.telegram_id is None:
            raise AttendanceError("missing")
        found = await self._groups.active_study(user.telegram_id, group_id, user.id)
        if found is None:
            raise AttendanceError("missing")
        group, student = found
        statuses = await self._marks.statuses_for_student_group(student.id, group.id)
        recent = await self._marks.recent_for_student_group(student.id, group.id, HISTORY)
        marks = [
            {
                "lesson_id": lesson.id,
                "starts_at": lesson.starts_at.isoformat() if lesson.starts_at else None,
                "title": lesson.title,
                "status": mark.status,
            }
            for mark, lesson in recent
        ]
        return {
            "group_id": group.id,
            "group_name": group.name,
            "marks": marks,
            **attendance_rate(statuses),
        }

    async def _lesson(self, owner_id: int, lesson_id: int) -> TutorLesson:
        lesson = await self._lessons.get_owned(owner_id, lesson_id)
        if lesson is None or lesson.group_id is None:
            raise AttendanceError("missing")
        return lesson


def _plans(raw: object, members: set[int]) -> list[tuple[int, str | None, str | None]]:
    if not isinstance(raw, list):
        raise AttendanceError("marks")
    planned: list[tuple[int, str | None, str | None]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise AttendanceError("marks")
        student_id = _student_id(item.get("student_id"))
        if student_id not in members:
            raise AttendanceError("student")
        status = item.get("status", None)
        if status is None or status == "":
            planned.append((student_id, None, None))
            continue
        if not isinstance(status, str) or status not in STATUSES:
            raise AttendanceError("choice")
        note = _note(item["note"]) if "note" in item else None
        planned.append((student_id, status, note))
    return planned


def _sheet(
    lesson: TutorLesson, group_name: str, members, stored: dict[int, TutorAttendance]
) -> dict:
    students = []
    for member in members:
        mark = stored.get(member.id)
        students.append(
            {
                "student_id": member.id,
                "name": member.name,
                "status": None if mark is None else mark.status,
                "note": None if mark is None else mark.note,
            }
        )
    return {
        "lesson_id": lesson.id,
        "group_id": lesson.group_id,
        "group_name": group_name,
        "title": lesson.title,
        "starts_at": lesson.starts_at.isoformat() if lesson.starts_at else None,
        "status": lesson.status,
        "students": students,
    }


def _session(row: TutorLesson) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "status": row.status,
    }


def _started(lesson: TutorLesson, now: datetime) -> bool:
    """True when the session's Tashkent date is today or earlier."""
    if lesson.starts_at is None:
        return False
    return lesson.starts_at.astimezone(TASHKENT).date() <= now.astimezone(TASHKENT).date()


def _month(value: object) -> tuple[datetime, datetime]:
    if not isinstance(value, str):
        raise AttendanceError("month")
    match = _MONTH.fullmatch(value.strip())
    if match is None:
        raise AttendanceError("month")
    year, month = int(match.group(1)), int(match.group(2))
    if month < 1 or month > 12:
        raise AttendanceError("month")
    start = datetime(year, month, 1, tzinfo=TASHKENT)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=TASHKENT)
    else:
        end = datetime(year, month + 1, 1, tzinfo=TASHKENT)
    return start.astimezone(UTC), end.astimezone(UTC)


def _student_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AttendanceError("student")
    return value


def _note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AttendanceError("note")
    text = value.strip()
    if not text:
        return None
    if len(text) > NOTE_MAX:
        raise AttendanceError("note")
    return text
