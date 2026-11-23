"""Join links and group registration requests."""

from __future__ import annotations

import re
import secrets
from collections.abc import Awaitable, Callable

from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.clock import utcnow
from app.services.fee_rules import tashkent_today
from app.services.fees import FeeService
from app.services.tutor_limits import ensure_student_room
from app.services.workspaces import WorkspaceService

PENDING_CAP = 50
_SPACE = re.compile(r"\s+")
Notify = Callable[[User, str, str], Awaitable[None]]


class EnrollmentError(Exception):
    """A request the teacher cannot resolve. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EnrollmentService:
    """Claim a personal link or ask to join a group."""

    def __init__(
        self,
        groups: GroupRepository,
        students: StudentRepository,
        users: UserRepository,
        spaces: WorkspaceService,
        access: AccessService | None = None,
        fees: FeeService | None = None,
    ) -> None:
        self._groups = groups
        self._students = students
        self._users = users
        self._access = access
        self._spaces = spaces
        self._fees = fees

    async def claim(self, code: str, telegram_id: int) -> str:
        """Link a personal invite. Returns ok, missing, taken, own, or already."""
        row = await self._students.by_join_code(code)
        if row is None:
            return "missing"
        owner = await self._users.get_by_id(row.owner_id)
        if owner is not None and owner.telegram_id == telegram_id:
            return "own"
        if row.telegram_id is not None and row.telegram_id != telegram_id:
            return "taken"
        other = await self._students.by_owner_telegram(row.owner_id, telegram_id)
        if other is not None and other.id != row.id:
            return "already"
        row.telegram_id = telegram_id
        await self._students.save(row)
        return "ok"

    async def describe(self, kind: str, code: str) -> tuple[str | None, str | None]:
        """Group name and teacher display name behind a join_ or enroll_ code."""
        from app.db.repositories.users import teacher_name_of

        if kind == "enroll":
            group = await self._groups.by_enroll_code(code)
            if group is None:
                return None, None
            owner = await self._users.get_by_id(group.owner_id)
            return group.name, teacher_name_of(owner) or None
        row = await self._students.by_join_code(code)
        if row is None:
            return None, None
        owner = await self._users.get_by_id(row.owner_id)
        groups = await self._groups.groups_for_student(row.id)
        return (groups[0].name if groups else None), teacher_name_of(owner) or None

    async def enroll(
        self,
        code: str,
        telegram_id: int,
        full_name: str,
        notify: Notify | None = None,
    ) -> str:
        """Ask to join the group. Returns pending, already, own, missing, or busy."""
        group = await self._groups.by_enroll_code(code)
        if group is None:
            return "missing"
        owner = await self._users.get_by_id(group.owner_id)
        if owner is None:
            return "missing"
        if owner.telegram_id == telegram_id:
            return "own"
        student = await self._students.by_owner_telegram(group.owner_id, telegram_id)
        if student is not None and await self._linked(group.id, student.id):
            return "already"
        if await self._groups.count_pending_for_owner(group.owner_id) >= PENDING_CAP:
            return "busy"
        if student is None:
            workspace_id = await self._spaces.id_for(group.owner_id)
            student = await self._students.insert_or_get(
                TutorStudent(
                    owner_id=group.owner_id,
                    workspace_id=workspace_id,
                    name=_name(full_name),
                    status="pending",
                    amount_uzs=0,
                    telegram_id=telegram_id,
                    join_code=secrets.token_hex(5),
                )
            )
        if await self._linked(group.id, student.id):
            return "already"
        inserted = await self._groups.add_member_once(group.id, student.id, "pending")
        if not inserted:
            return "already"
        if notify is not None:
            await notify(owner, student.name, group.name, group.id, student.id)
        return "pending"

    async def requests(self, owner_id: int) -> dict:
        """Registration requests waiting for this teacher."""
        rows = await self._groups.pending_for_owner(owner_id)
        return {
            "requests": [
                {
                    "group_id": group.id,
                    "group_name": group.name,
                    "student_id": student.id,
                    "name": student.name,
                    "telegram_id": student.telegram_id,
                    "created_at": member.created_at.isoformat(),
                }
                for member, group, student in rows
            ]
        }

    async def approve(self, owner_id: int, group_id: int, student_id: int) -> dict:
        """Accept one request. A new card becomes a debtor until fees exist."""
        group, student, link = await self._pending(owner_id, group_id, student_id)
        if student.status == "pending" and self._access is not None:
            await ensure_student_room(self._access, self._users, self._students, owner_id)
        link.status = "active"
        if link.billing_start is None:
            link.billing_start = tashkent_today(utcnow())
        await self._groups.save_member(link)
        if self._fees is not None:
            await self._fees.sync_member(group, link)
        if student.status == "pending":
            student.status = "debtor"
            await self._students.save(student)
        return {"group": group.name, "telegram_id": student.telegram_id}

    async def reject(self, owner_id: int, group_id: int, student_id: int) -> dict:
        """Drop the request. A card that was only waiting is deleted."""
        group, student, link = await self._pending(owner_id, group_id, student_id)
        telegram_id = student.telegram_id
        await self._groups.delete_member(link)
        if student.status == "pending":
            rest = await self._groups.memberships_for_student(student.id)
            if not rest:
                await self._students.delete(student)
        return {"group": group.name, "telegram_id": telegram_id}

    async def _pending(self, owner_id: int, group_id: int, student_id: int):
        group = await self._groups.get_owned(owner_id, group_id)
        student = await self._students.get_owned(owner_id, student_id)
        link = (
            None
            if group is None or student is None
            else await self._linked_row(group_id, student_id)
        )
        if group is None or student is None or link is None or link.status != "pending":
            raise EnrollmentError("missing")
        return group, student, link

    async def _linked(self, group_id: int, student_id: int) -> bool:
        return await self._linked_row(group_id, student_id) is not None

    async def _linked_row(self, group_id: int, student_id: int):
        return await self._groups.membership(group_id, student_id)


def _name(value: str) -> str:
    text = _SPACE.sub(" ", (value or "").strip())
    return text[:80] or "O'quvchi"
