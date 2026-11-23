"""Tutor groups: a weekly slot and the students who attend it."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.clock import utcnow
from app.services.fee_rules import tashkent_today
from app.services.fees import FeeService
from app.services.sessions import SessionPlanner
from app.services.tutor_limits import ensure_group_room
from app.services.workspaces import WorkspaceService

NAME_MAX = 80
LEVEL_MAX = 40
_SPACE = re.compile(r"\s+")
_CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class GroupError(Exception):
    """Invalid group input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class GroupInput:
    """Validated group fields."""

    name: str
    level: str | None
    weekdays: str
    start_min: int
    end_min: int


class GroupService:
    """Create groups and place the owner's students in them."""

    def __init__(
        self,
        groups: GroupRepository,
        students: StudentRepository,
        access: AccessService | None = None,
        users: UserRepository | None = None,
        spaces: WorkspaceService | None = None,
        planner: SessionPlanner | None = None,
        fees: FeeService | None = None,
    ) -> None:
        self._groups = groups
        self._students = students
        self._access = access
        self._users = users
        self._spaces = spaces
        self._planner = planner
        self._fees = fees

    async def list(self, owner_id: int) -> dict:
        """Every group of this owner, with how many students sit in each."""
        rows = await self._groups.list_for_owner(owner_id)
        return {"groups": [_brief(group, count) for group, count in rows]}

    async def create(self, owner_id: int, body: dict) -> dict:
        """Store a group and return the list, including the new id."""
        parsed = parse_group(body)
        if self._access is not None and self._users is not None:
            await ensure_group_room(self._access, self._users, self._groups, owner_id)
        workspace_id = await self._spaces.id_for(owner_id) if self._spaces else 0
        row = await self._groups.add(
            TutorGroup(
                owner_id=owner_id,
                workspace_id=workspace_id,
                name=parsed.name,
                level=parsed.level,
                weekdays=parsed.weekdays,
                start_min=parsed.start_min,
                end_min=parsed.end_min,
                enroll_code=secrets.token_hex(5),
            )
        )
        if self._planner is not None:
            await self._planner.fill(row)
        payload = await self.list(owner_id)
        payload["created_id"] = row.id
        return payload

    async def update(self, owner_id: int, group_id: int, body: dict) -> dict:
        """Change the fields present in `body`."""
        row = await self._groups.get_owned(owner_id, group_id)
        if row is None:
            raise GroupError("missing")
        parsed = parse_group(body, current=row)
        row.name = parsed.name
        row.level = parsed.level
        row.weekdays = parsed.weekdays
        row.start_min = parsed.start_min
        row.end_min = parsed.end_min
        await self._groups.save(row)
        if self._planner is not None:
            await self._planner.refill(row)
        return await self.open(owner_id, group_id)

    async def open(self, owner_id: int, group_id: int) -> dict:
        """One group, its members, and the owner's other students."""
        row = await self._groups.get_owned(owner_id, group_id)
        if row is None:
            raise GroupError("missing")
        members = await self._groups.members(group_id)
        everyone = [
            item
            for item in await self._students.list_for_owner(owner_id)
            if item.status != "pending"
        ]
        inside = {item.id for item in members}
        outside = [{"id": item.id, "name": item.name} for item in everyone if item.id not in inside]
        outside.sort(key=lambda item: item["name"].casefold())
        return {
            "group": _brief(row, len(members)),
            "members": [
                {"id": item.id, "name": item.name, "status": item.status} for item in members
            ],
            "available": outside,
        }

    async def remove(self, owner_id: int, group_id: int) -> dict:
        """Delete one of this owner's groups."""
        row = await self._groups.get_owned(owner_id, group_id)
        if row is None:
            raise GroupError("missing")
        await self._groups.delete(row)
        return await self.list(owner_id)

    async def add_student(self, owner_id: int, group_id: int, student_id: int) -> dict:
        """Put one of this owner's students into the group. A repeat is a no-op."""
        group = await self._groups.get_owned(owner_id, group_id)
        if group is None:
            raise GroupError("missing")
        student = await self._students.get_owned(owner_id, student_id)
        if student is None or student.status == "pending":
            raise GroupError("student")
        link = await self._groups.membership(group_id, student_id)
        if link is None:
            link = await self._groups.add_member(
                TutorGroupMember(
                    group_id=group_id,
                    student_id=student_id,
                    status="active",
                    billing_start=tashkent_today(utcnow()),
                )
            )
        elif link.status == "pending":
            link.status = "active"
            if link.billing_start is None:
                link.billing_start = tashkent_today(utcnow())
            await self._groups.save_member(link)
        if self._fees is not None and link is not None:
            await self._fees.sync_member(group, link)
        return await self.open(owner_id, group_id)

    async def remove_student(self, owner_id: int, group_id: int, student_id: int) -> dict:
        """Take a student out of the group. The student record stays."""
        if await self._groups.get_owned(owner_id, group_id) is None:
            raise GroupError("missing")
        link = await self._groups.membership(group_id, student_id)
        if link is None:
            raise GroupError("missing")
        await self._groups.delete_member(link)
        return await self.open(owner_id, group_id)


def parse_group(body: dict, current: TutorGroup | None = None) -> GroupInput:
    """Validate a create body, or a partial update when `current` is set."""
    if "name" in body or current is None:
        name = _name(body.get("name"))
    else:
        name = current.name
    if "level" in body or current is None:
        level = _level(body.get("level"))
    else:
        level = current.level
    if "weekdays" in body or current is None:
        weekdays = _days(body.get("weekdays"))
    else:
        weekdays = current.weekdays
    if current is None or "start" in body:
        start = _clock(body.get("start"))
    else:
        start = current.start_min
    if current is None or "end" in body:
        end = _clock(body.get("end"))
    else:
        end = current.end_min
    if start >= end:
        raise GroupError("time")
    return GroupInput(name=name, level=level, weekdays=weekdays, start_min=start, end_min=end)


def _brief(row: TutorGroup, count: int) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "level": row.level,
        "weekdays": [int(part) for part in row.weekdays.split(",")],
        "start": _hhmm(row.start_min),
        "end": _hhmm(row.end_min),
        "students": count,
        "fee_mode": row.fee_mode or "none",
        "fee_uzs": row.fee_uzs or 0,
        "package_lessons": row.package_lessons,
        "billing_day": row.billing_day,
        "due_days": 5 if row.due_days is None else row.due_days,
    }


def _name(value: object) -> str:
    if not isinstance(value, str):
        raise GroupError("empty")
    text = _SPACE.sub(" ", value).strip()
    if not text:
        raise GroupError("empty")
    if len(text) > NAME_MAX:
        raise GroupError("long")
    return text


def _level(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GroupError("long")
    text = _SPACE.sub(" ", value).strip()
    if not text:
        return None
    if len(text) > LEVEL_MAX:
        raise GroupError("long")
    return text


def _days(value: object) -> str:
    if not isinstance(value, list) or not value:
        raise GroupError("days")
    found: set[int] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < 1 or item > 7:
            raise GroupError("days")
        found.add(item)
    return ",".join(str(day) for day in sorted(found))


def _clock(value: object) -> int:
    if not isinstance(value, str):
        raise GroupError("time")
    match = _CLOCK.fullmatch(value.strip())
    if match is None:
        raise GroupError("time")
    hour, minute = int(match.group(1)), int(match.group(2))
    return hour * 60 + minute


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
