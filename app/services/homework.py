"""Homework text on a topic, at most 1000 characters."""

from __future__ import annotations

import re
from datetime import date

from app.db.repositories.groups import GroupRepository
from app.db.repositories.topics import TopicRepository

_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
TEXT_MAX = 1000


class HomeworkError(Exception):
    """Invalid homework. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HomeworkService:
    """Save homework on a topic the teacher owns."""

    def __init__(self, topics: TopicRepository, groups: GroupRepository) -> None:
        self._topics = topics
        self._groups = groups

    async def save(self, owner_id: int, group_id: int, topic_id: int, body: dict) -> dict:
        """Store or clear the text and the due date."""
        if await self._groups.get_owned(owner_id, group_id) is None:
            raise HomeworkError("missing")
        topic = await self._topics.get(topic_id)
        if topic is None or topic.group_id != group_id:
            raise HomeworkError("missing")
        topic.homework, topic.homework_due = parse_homework(body)
        await self._topics.save_topic(topic)
        return _public(topic)


def parse_homework(body: dict) -> tuple[str | None, date | None]:
    """Read optional homework fields. An empty text clears the task."""
    text = _text(body.get("homework"))
    due = _due(body.get("homework_due"))
    if text is None:
        due = None
    return text, due


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise HomeworkError("homework")
    text = value.strip()
    if not text:
        return None
    if len(text) > TEXT_MAX:
        raise HomeworkError("long")
    return text


def _due(value: object) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise HomeworkError("date")
    match = _DAY.fullmatch(value.strip())
    if match is None:
        raise HomeworkError("date")
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise HomeworkError("date") from exc


def _public(topic) -> dict:
    return {
        "id": topic.id,
        "homework": topic.homework,
        "homework_due": topic.homework_due.isoformat() if topic.homework_due else None,
    }
