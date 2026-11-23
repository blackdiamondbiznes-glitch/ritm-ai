"""Cabinet usage against the plan. AccessService still owns the caps."""

from __future__ import annotations

from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.usage import UsageRepository
from app.services.access import AccessService
from app.services.clock import Clock, utcnow
from app.services.notify_rules import METRIC, period_key


async def usage_snapshot(
    access: AccessService,
    groups: GroupRepository,
    students: StudentRepository,
    usage: UsageRepository,
    owner: User,
    now: Clock | None = None,
) -> dict:
    """Used and allowed counts for groups, students, and reminders."""
    clock = now or utcnow
    limits = await access.tutor_limits(owner)
    kind = (await access.snapshot(owner)).kind
    notes = await usage.get_count(owner.id, METRIC, period_key(clock()))
    return {
        "plan": limits.plan_code,
        "kind": kind,
        "groups": {"used": await groups.count_for_owner(owner.id), "limit": limits.max_groups},
        "students": {
            "used": await students.count_visible(owner.id),
            "limit": limits.max_students,
        },
        "notifications": {"used": notes, "limit": limits.notifications},
        "reports": limits.reports,
    }
