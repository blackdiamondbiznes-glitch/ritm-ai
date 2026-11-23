"""How many groups and students the owner's plan allows."""

from __future__ import annotations

from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.users import UserRepository
from app.services.access import AccessService


class TutorLimitError(Exception):
    """The owner is already at a cabinet cap. `code` is limit_groups or limit_students."""

    def __init__(self, code: str, limit: int, used: int, plan: str) -> None:
        super().__init__(code)
        self.code = code
        self.limit = limit
        self.used = used
        self.plan = plan


def limit_body(exc: TutorLimitError) -> dict[str, object]:
    """JSON body for a 403 from a cabinet cap."""
    return {"error": exc.code, "limit": exc.limit, "used": exc.used, "plan": exc.plan}


async def ensure_group_room(
    access: AccessService,
    users: UserRepository,
    groups: GroupRepository,
    owner_id: int,
) -> None:
    """Raise when this owner cannot open another group."""
    owner = await _owner(users, owner_id, "limit_groups")
    limits = await access.tutor_limits(owner)
    used = await groups.count_for_owner(owner_id)
    if used >= limits.max_groups:
        raise TutorLimitError("limit_groups", limits.max_groups, used, limits.plan_code)


async def ensure_student_room(
    access: AccessService,
    users: UserRepository,
    students: StudentRepository,
    owner_id: int,
) -> None:
    """Raise when this owner cannot add another visible student card."""
    owner = await _owner(users, owner_id, "limit_students")
    limits = await access.tutor_limits(owner)
    used = await students.count_visible(owner_id)
    if used >= limits.max_students:
        raise TutorLimitError("limit_students", limits.max_students, used, limits.plan_code)


async def _owner(users: UserRepository, owner_id: int, code: str) -> User:
    owner = await users.get_by_id(owner_id)
    if owner is None:
        raise TutorLimitError(code, 0, 0, "free")
    return owner
