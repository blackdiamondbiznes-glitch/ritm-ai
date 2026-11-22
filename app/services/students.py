"""Tutor cabinet: the owner's students and whether they have paid."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models.groups import TutorGroupMember
from app.db.models.students import TutorStudent
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.reminders import ReminderRepository
from app.db.repositories.students import StudentRepository

STATUSES = frozenset({"paid", "debtor", "inactive"})
NAME_MAX = 80
PHONE_MAX = 20
NOTE_MAX = 300
AMOUNT_MAX = 1_000_000_000
_PHONE = re.compile(r"^\+?[0-9][0-9 ()-]{5,18}$")
_SPACE = re.compile(r"\s+")


class StudentError(Exception):
    """Invalid student input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class StudentInput:
    """Validated student fields."""

    name: str
    phone: str | None
    status: str
    amount_uzs: int
    note: str | None


class StudentService:
    """Create, edit and list students for one owner."""

    def __init__(
        self,
        students: StudentRepository,
        lessons: LessonRepository | None = None,
        reminders: ReminderRepository | None = None,
        groups: GroupRepository | None = None,
    ) -> None:
        self._students = students
        self._lessons = lessons
        self._reminders = reminders
        self._groups = groups

    async def list(self, owner_id: int) -> dict:
        """Every student of this owner, plus counts by status."""
        return _payload(await self._students.list_for_owner(owner_id))

    async def create(self, owner_id: int, body: dict) -> dict:
        """Store a new student. A missing status starts as owing."""
        parsed = parse_student(body)
        now = datetime.now(UTC)
        row = await self._students.add(
            TutorStudent(
                owner_id=owner_id,
                name=parsed.name,
                phone=parsed.phone,
                status=parsed.status,
                amount_uzs=parsed.amount_uzs,
                note=parsed.note,
                join_code=secrets.token_hex(5),
                created_at=now,
                updated_at=now,
            )
        )
        await self._place(owner_id, row.id, body, required=True)
        payload = await self.list(owner_id)
        payload["created_id"] = row.id
        return payload

    async def update(self, owner_id: int, student_id: int, body: dict) -> dict:
        """Change the fields present in `body`. Other fields stay as they are."""
        row = await self._students.get_owned(owner_id, student_id)
        if row is None:
            raise StudentError("missing")
        parsed = parse_student(body, current=row)
        row.name = parsed.name
        row.phone = parsed.phone
        row.status = parsed.status
        row.amount_uzs = parsed.amount_uzs
        row.note = parsed.note
        row.updated_at = datetime.now(UTC)
        await self._students.save(row)
        if "group_ids" in body:
            await self._place(owner_id, row.id, body, required=True)
        return await self.list(owner_id)

    async def profile(self, owner_id: int, student_id: int) -> dict:
        """One student plus only the lessons and reminders tied to them."""
        row = await self._students.get_owned(owner_id, student_id)
        if row is None:
            raise StudentError("missing")
        lessons = []
        if self._lessons is not None:
            owned = await self._lessons.list_for_owner(owner_id)
            lessons = [_lesson_brief(item) for item in owned if item.student_id == student_id]
        reminders = []
        if self._reminders is not None:
            owned_notes = await self._reminders.list_for_owner(owner_id)
            reminders = [
                _reminder_brief(item) for item in owned_notes if item.student_id == student_id
            ]
        groups = await self._group_names(owner_id, student_id)
        return {"student": _one(row), "lessons": lessons, "reminders": reminders, "groups": groups}

    async def _place(self, owner_id: int, student_id: int, body: dict, *, required: bool) -> None:
        """Put the student in the chosen groups. A tutor with groups must pick one."""
        if self._groups is None:
            return
        owned = await self._groups.list_for_owner(owner_id)
        owned_ids = {group.id for group, _count in owned}
        if "group_ids" not in body:
            if required and owned_ids:
                raise StudentError("group")
            return
        wanted = set(_group_ids(body.get("group_ids"), required=required and bool(owned_ids)))
        if not wanted <= owned_ids:
            raise StudentError("group")
        current = {
            group.id
            for group in await self._groups.groups_for_student(student_id)
            if group.owner_id == owner_id
        }
        for group_id in wanted - current:
            await self._groups.add_member(
                TutorGroupMember(group_id=group_id, student_id=student_id)
            )
        for group_id in current - wanted:
            link = await self._groups.membership(group_id, student_id)
            if link is not None:
                await self._groups.delete_member(link)

    async def _group_names(self, owner_id: int, student_id: int) -> list[dict]:
        if self._groups is None:
            return []
        rows = await self._groups.groups_for_student(student_id)
        return [
            {"id": group.id, "name": group.name}
            for group in rows
            if group.owner_id == owner_id
        ]

    async def remove(self, owner_id: int, student_id: int) -> dict:
        """Delete one of this owner's students."""
        row = await self._students.get_owned(owner_id, student_id)
        if row is None:
            raise StudentError("missing")
        await self._students.delete(row)
        return await self.list(owner_id)


def parse_student(body: dict, current: TutorStudent | None = None) -> StudentInput:
    """Validate a create body, or a partial update when `current` is set."""
    if "name" in body or current is None:
        name = _name(body.get("name"))
    else:
        name = current.name
    if "phone" in body or current is None:
        phone = _phone(body.get("phone"))
    else:
        phone = current.phone
    if "status" in body or current is None:
        status = _status(body.get("status", "debtor"))
    else:
        status = current.status
    if "amount_uzs" in body:
        amount = _amount(body["amount_uzs"])
    elif current is None:
        amount = 0
    else:
        amount = current.amount_uzs
    if "note" in body or current is None:
        note = _note(body.get("note"))
    else:
        note = current.note
    return StudentInput(name=name, phone=phone, status=status, amount_uzs=amount, note=note)


def _one(row: TutorStudent) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "phone": row.phone,
        "status": row.status,
        "amount_uzs": row.amount_uzs,
        "note": row.note,
        "join_code": row.join_code,
    }


def _lesson_brief(row) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "amount_uzs": row.amount_uzs,
    }


def _reminder_brief(row) -> dict:
    return {
        "id": row.id,
        "text": row.text,
        "send_at": row.send_at.isoformat(),
        "sent": row.sent_at is not None,
    }


def _payload(rows: list[TutorStudent]) -> dict:
    counts = {"paid": 0, "debtor": 0, "inactive": 0}
    students = []
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
        students.append(_one(row))
    return {"students": students, "counts": counts}


def _group_ids(value: object, *, required: bool) -> list[int]:
    if not isinstance(value, list):
        raise StudentError("group")
    found: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise StudentError("group")
        if item not in found:
            found.append(item)
    if required and not found:
        raise StudentError("group")
    return found


def _name(value: object) -> str:
    if not isinstance(value, str):
        raise StudentError("empty")
    text = _SPACE.sub(" ", value).strip()
    if not text:
        raise StudentError("empty")
    if len(text) > NAME_MAX:
        raise StudentError("long")
    return text


def _phone(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StudentError("phone")
    text = _SPACE.sub(" ", value).strip()
    if not text:
        return None
    if len(text) > PHONE_MAX or _PHONE.fullmatch(text) is None:
        raise StudentError("phone")
    return text


def _status(value: object) -> str:
    if not isinstance(value, str) or value not in STATUSES:
        raise StudentError("choice")
    return value


def _amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StudentError("amount")
    if value < 0 or value > AMOUNT_MAX:
        raise StudentError("amount")
    return value


def _note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StudentError("note")
    text = value.strip()
    if not text:
        return None
    if len(text) > NOTE_MAX:
        raise StudentError("note")
    return text
