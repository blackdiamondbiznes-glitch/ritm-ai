"""Queue one homework reminder the evening before it is due."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db.repositories.topics import TopicRepository
from app.services.clock import TASHKENT
from app.services.notify_queue import deliver
from app.services.notify_rules import run_at
from app.services.notify_targets import student_dest

EVENING = 18


async def enqueue_homework(planner, topics: TopicRepository, now: datetime) -> int:
    """Tell each linked student once. A second tick adds nothing."""
    local = now.astimezone(TASHKENT)
    if local.hour < EVENING:
        return 0
    due = local.date() + timedelta(days=1)
    made = 0
    for topic, group in await topics.homework_due(due):
        when, _late = run_at(now, None, "homework")
        params = {"topic": topic.title, "text": topic.homework or "", "date": due.isoformat()}
        for student in await planner._groups.members(group.id):
            dest = await student_dest(planner._users, student)
            if dest is None:
                continue
            if await deliver(
                planner._notes,
                planner._jobs,
                kind="homework",
                ref=topic.id,
                target="student",
                target_id=dest["target_id"],
                telegram_id=dest["telegram_id"],
                lang=dest["lang"],
                template="notify_homework",
                params=params,
                quota=True,
                owner_id=group.owner_id,
                run_at=when,
            ):
                made += 1
    return made
