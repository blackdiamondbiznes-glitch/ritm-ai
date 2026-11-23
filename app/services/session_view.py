"""Read and change dated sessions. The planner owns the weekly fill."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app.db.models.lessons import TutorLesson
from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.services.clock import TASHKENT, Clock, utcnow
from app.services.meeting_link import clean_meeting_url
from app.services.sessions import SessionError

TITLE_MAX = 120
NOTE_MAX = 300
MAX_SPAN = timedelta(hours=6)
MAX_DAYS = 31
_SPACE = re.compile(r"\s+")
_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_WHEN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})$")
_STATUSES = frozenset({"scheduled", "done", "cancelled"})


class SessionView:
    """Owner timetable and the student's next lessons."""

    def __init__(
        self,
        lessons: LessonRepository,
        groups: GroupRepository,
        now: Clock | None = None,
        notifier=None,
    ) -> None:
        self._lessons = lessons
        self._groups = groups
        self._now = now or utcnow
        self._notifier = notifier

    async def between(self, owner_id: int, start: object, end: object) -> list[dict]:
        """Lessons and group sessions that start inside the inclusive date range."""
        opening, closing = _dates(start, end)
        rows = await self._lessons.in_range(owner_id, opening, closing)
        return [_public(row, name) for row, name in rows]

    async def add_extra(self, owner_id: int, group_id: int, body: dict) -> dict:
        """One extra session. It occupies the slot so the planner will not refill it."""
        group = await self._groups.get_owned(owner_id, group_id)
        if group is None:
            raise SessionError("missing")
        start, end = _span(body.get("starts_at"), body.get("ends_at"))
        new_id = await self._lessons.insert_slot(
            {
                "owner_id": owner_id,
                "workspace_id": group.workspace_id,
                "group_id": group.id,
                "student_id": None,
                "title": _title(body.get("title")),
                "status": "scheduled",
                "source": "manual",
                "amount_uzs": 0,
                "starts_at": start,
                "ends_at": end,
                "planned_at": start,
                "note": None,
                "meeting_url": _link(body.get("meeting_url")),
            }
        )
        if new_id is None:
            raise SessionError("slot")
        row = await self._lessons.get_owned(owner_id, new_id)
        if row is None:
            raise SessionError("missing")
        return _public(row, group.name)

    async def update(self, owner_id: int, session_id: int, body: dict) -> dict:
        """Change status, title, note, or the clock time. `planned_at` stays."""
        row = await self._lessons.get_owned(owner_id, session_id)
        if row is None:
            raise SessionError("missing")
        previous_status, previous_start = row.status, row.starts_at
        if "title" in body:
            row.title = _title(body.get("title"))
        if "status" in body:
            row.status = _status(body.get("status"))
        if "note" in body:
            row.note = _note(body.get("note"))
        if "meeting_url" in body:
            row.meeting_url = _link(body.get("meeting_url"))
        if "starts_at" in body or "ends_at" in body:
            start = _wall(body["starts_at"]) if "starts_at" in body else row.starts_at
            end = _wall(body["ends_at"]) if "ends_at" in body else row.ends_at
            _check_span(start, end)
            row.starts_at = start
            row.ends_at = end
        row.updated_at = datetime.now(UTC)
        await self._lessons.save(row)
        await self._changed(owner_id, row, previous_status, previous_start)
        return _public(row, await self._name(owner_id, row.group_id))

    async def _changed(self, owner_id: int, row: TutorLesson, status: str, start) -> None:
        """Cancel and move reach the same chats as a lesson reminder."""
        if self._notifier is None or row.group_id is None:
            return
        if row.status == "cancelled" and status != "cancelled":
            await self._notifier.queue_session(owner_id, row, "cancel")
        elif row.starts_at != start:
            await self._notifier.queue_session(owner_id, row, "move")

    async def for_student(self, user: User, days: int) -> list[dict]:
        """Sessions of groups where this account's membership is active."""
        if days < 1 or days > MAX_DAYS:
            raise SessionError("range")
        if user.telegram_id is None:
            return []
        local = self._now().astimezone(TASHKENT)
        start = datetime(local.year, local.month, local.day, tzinfo=TASHKENT).astimezone(UTC)
        rows = await self._lessons.for_learner(
            user.telegram_id, user.id, start, start + timedelta(days=days)
        )
        return [_public(row, name, teacher or "") for row, name, teacher in rows]

    async def _name(self, owner_id: int, group_id: int | None) -> str | None:
        if group_id is None:
            return None
        group = await self._groups.get_owned(owner_id, group_id)
        return None if group is None else group.name


def _public(row: TutorLesson, group_name: str | None, teacher_name: str | None = None) -> dict:
    data = {
        "id": row.id,
        "group_id": row.group_id,
        "group_name": group_name,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        "status": row.status,
        "title": row.title,
        "source": row.source,
        "meeting_url": row.meeting_url,
    }
    if teacher_name is not None:
        data["teacher_name"] = teacher_name
    return data


def _dates(start: object, end: object) -> tuple[datetime, datetime]:
    left, right = _day(start), _day(end)
    if (right - left).days < 0 or (right - left).days >= MAX_DAYS:
        raise SessionError("range")
    opening = datetime(left.year, left.month, left.day, tzinfo=TASHKENT).astimezone(UTC)
    closing = datetime(right.year, right.month, right.day, tzinfo=TASHKENT) + timedelta(days=1)
    return opening, closing.astimezone(UTC)


def _day(value: object) -> datetime:
    if not isinstance(value, str):
        raise SessionError("range")
    match = _DAY.fullmatch(value.strip())
    if match is None:
        raise SessionError("range")
    year, month, day = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day)
    except ValueError as exc:
        raise SessionError("range") from exc


def _span(start: object, end: object) -> tuple[datetime, datetime]:
    opening, closing = _wall(start), _wall(end)
    _check_span(opening, closing)
    return opening, closing


def _check_span(start: datetime | None, end: datetime | None) -> None:
    if start is None or end is None or end <= start:
        raise SessionError("time")
    if end - start > MAX_SPAN:
        raise SessionError("span")


def _wall(value: object) -> datetime:
    """Read a Tashkent wall time `YYYY-MM-DDTHH:MM` and return UTC."""
    if not isinstance(value, str):
        raise SessionError("when")
    match = _WHEN.fullmatch(value.strip())
    if match is None:
        raise SessionError("when")
    year, month, day, hour, minute = (int(part) for part in match.groups())
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=TASHKENT)
    except ValueError as exc:
        raise SessionError("when") from exc
    return local.astimezone(UTC)


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise SessionError("empty")
    text = _SPACE.sub(" ", value).strip()
    if not text:
        raise SessionError("empty")
    if len(text) > TITLE_MAX:
        raise SessionError("long")
    return text


def _status(value: object) -> str:
    if not isinstance(value, str) or value not in _STATUSES:
        raise SessionError("choice")
    return value


def _note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SessionError("note")
    text = value.strip()
    if not text:
        return None
    if len(text) > NOTE_MAX:
        raise SessionError("note")
    return text


def _link(value: object) -> str | None:
    try:
        return clean_meeting_url(value)
    except ValueError as exc:
        raise SessionError("link") from exc
