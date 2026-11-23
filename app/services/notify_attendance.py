"""Queue one attendance card per group session after it has started today."""

from __future__ import annotations

from datetime import datetime

from app.db.repositories.attendance import AttendanceRepository
from app.services.clock import TASHKENT
from app.services.notify_queue import deliver
from app.services.notify_rules import language, lesson_label, run_at


async def enqueue_attendance(planner, now: datetime) -> int:
    """Tell the teacher once. Sessions from earlier days are ignored."""
    local = now.astimezone(TASHKENT)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await planner._notes.lessons_started(start, now)
    if not rows:
        return 0
    marks = await AttendanceRepository(planner._notes._session).for_lessons(
        [lesson.id for lesson, _group in rows]
    )
    by_lesson: dict[int, set[int]] = {}
    for row in marks:
        by_lesson.setdefault(row.lesson_id, set()).add(row.student_id)
    made = 0
    for lesson, group in rows:
        members = await planner._groups.members(group.id)
        if not members:
            continue
        if len(by_lesson.get(lesson.id, set())) >= len(members):
            continue
        owner = await planner._users.get_by_id(group.owner_id)
        if owner is None or owner.telegram_id is None:
            continue
        when, _late = run_at(now, None, "attendance")
        clock = lesson.starts_at.astimezone(TASHKENT).strftime("%H:%M") if lesson.starts_at else ""
        if await deliver(
            planner._notes,
            planner._jobs,
            kind="attendance",
            ref=lesson.id,
            target="owner",
            target_id=owner.id,
            telegram_id=owner.telegram_id,
            lang=language(owner.language_code),
            template="notify_attendance",
            params={"title": lesson_label(group.name, group.level), "time": clock},
            quota=False,
            owner_id=owner.id,
            run_at=when,
        ):
            made += 1
    return made
