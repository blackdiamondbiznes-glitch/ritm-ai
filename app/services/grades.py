"""Group topics, 0–10 marks, and the ranking both sides can see."""

from __future__ import annotations

import re
from datetime import date, datetime

from app.db.models.groups import TutorGroup
from app.db.models.students import TutorStudent
from app.db.models.topics import TutorScore, TutorTopic
from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.topics import TopicRepository
from app.db.repositories.users import UserRepository
from app.services.clock import TASHKENT
from app.services.groups import _hhmm

TITLE_MAX = 120
_SPACE = re.compile(r"\s+")
_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class GradeError(Exception):
    """Invalid grade input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class GradeService:
    """Record a topic mark and build the group ranking from those marks."""

    def __init__(
        self,
        groups: GroupRepository,
        students: StudentRepository,
        topics: TopicRepository,
        users: UserRepository,
    ) -> None:
        self._groups = groups
        self._students = students
        self._topics = topics
        self._users = users

    async def board(self, owner_id: int, group_id: int) -> dict:
        """Topics and the ranking for one of this owner's groups."""
        group = await self._owned(owner_id, group_id)
        members = await self._groups.members(group.id)
        topics = await self._topics.list_for_group(group.id)
        scores = await self._topics.scores_for([item.id for item in topics])
        return {
            "topics": [_topic_row(item, scores) for item in topics],
            "ranking": rank(members, scores),
            "gradebook": gradebook(members, topics, scores),
        }

    async def add_topic(self, owner_id: int, group_id: int, body: dict) -> dict:
        """Open a topic and return the blank mark sheet for current members."""
        group = await self._owned(owner_id, group_id)
        row = await self._topics.add_topic(
            TutorTopic(
                group_id=group.id,
                title=_title(body.get("title")),
                held_on=_day(body.get("held_on")),
            )
        )
        return await self.sheet(owner_id, group_id, row.id)

    async def sheet(self, owner_id: int, group_id: int, topic_id: int) -> dict:
        """One topic with a mark slot for every current member."""
        await self._owned(owner_id, group_id)
        topic = await self._topic_in_group(group_id, topic_id)
        members = await self._groups.members(group_id)
        scores = await self._topics.scores_for([topic.id])
        by_student = {item.student_id: item.score for item in scores}
        return {
            "topic": {"id": topic.id, "title": topic.title, "held_on": topic.held_on.isoformat()},
            "marks": [
                {"student_id": item.id, "name": item.name, "score": by_student.get(item.id)}
                for item in members
            ],
        }

    async def save_marks(self, owner_id: int, group_id: int, topic_id: int, body: dict) -> dict:
        """Store the marks the teacher sent. An empty mark clears the old one."""
        await self._owned(owner_id, group_id)
        await self._topic_in_group(group_id, topic_id)
        members = {item.id for item in await self._groups.members(group_id)}
        raw = body.get("scores")
        if not isinstance(raw, list):
            raise GradeError("score")
        for item in raw:
            if not isinstance(item, dict):
                raise GradeError("score")
            student_id = item.get("student_id")
            if (
                isinstance(student_id, bool)
                or not isinstance(student_id, int)
                or student_id not in members
            ):
                raise GradeError("student")
            await self._put_score(topic_id, student_id, item.get("score"))
        return await self.sheet(owner_id, group_id, topic_id)

    async def has_boards(self, telegram_id: int) -> bool:
        """True when this Telegram account is a member of at least one group."""
        return await self._groups.studies(telegram_id)

    async def boards_for(self, telegram_id: int) -> list[dict]:
        """Rankings of the groups this Telegram account studies in. Names and totals only."""
        found = []
        seen: set[int] = set()
        for student in await self._students.by_telegram(telegram_id):
            for group in await self._groups.groups_for_student(student.id):
                if group.id in seen or group.owner_id != student.owner_id:
                    continue
                seen.add(group.id)
                members = await self._groups.members(group.id)
                topics = await self._topics.list_for_group(group.id)
                scores = await self._topics.scores_for([item.id for item in topics])
                found.append(_public_group(group, rank(members, scores), student.id))
        found.sort(key=lambda item: (not item["today"], item["start"]))
        return found

    async def claim(self, code: str, telegram_id: int) -> str:
        """Link the student invite to this Telegram account. Returns ok, missing, or taken."""
        row = await self._students.by_join_code(code)
        if row is None:
            return "missing"
        owner = await self._users.get_by_id(row.owner_id)
        if owner is not None and owner.telegram_id == telegram_id:
            return "own"
        if row.telegram_id is not None and row.telegram_id != telegram_id:
            return "taken"
        row.telegram_id = telegram_id
        await self._students.save(row)
        return "ok"

    async def _owned(self, owner_id: int, group_id: int) -> TutorGroup:
        group = await self._groups.get_owned(owner_id, group_id)
        if group is None:
            raise GradeError("missing")
        return group

    async def _topic_in_group(self, group_id: int, topic_id: int) -> TutorTopic:
        topic = await self._topics.get(topic_id)
        if topic is None or topic.group_id != group_id:
            raise GradeError("missing")
        return topic

    async def _put_score(self, topic_id: int, student_id: int, value: object) -> None:
        existing = await self._topics.score(topic_id, student_id)
        if value is None or value == "":
            if existing is not None:
                await self._topics.delete_score(existing)
            return
        score = _score(value)
        if existing is None:
            await self._topics.add_score(
                TutorScore(topic_id=topic_id, student_id=student_id, score=score)
            )
            return
        existing.score = score
        await self._topics.save_score(existing)


def rank(members: list[TutorStudent], scores: list[TutorScore]) -> list[dict]:
    """Sum of marks. Ungraded students stay off the board. Ties share the place."""
    totals: dict[int, int] = {}
    graded: set[int] = set()
    for item in scores:
        totals[item.student_id] = totals.get(item.student_id, 0) + item.score
        graded.add(item.student_id)
    rows = [member for member in members if member.id in graded]
    rows.sort(key=lambda member: (-totals[member.id], member.name.casefold(), member.id))
    placed = []
    last_total = None
    last_rank = 0
    for index, member in enumerate(rows, start=1):
        total = totals[member.id]
        if total != last_total:
            last_rank = index
            last_total = total
        placed.append(
            {"student_id": member.id, "name": member.name, "total": total, "rank": last_rank}
        )
    return placed


def _topic_row(topic: TutorTopic, scores: list[TutorScore]) -> dict:
    graded = sum(1 for item in scores if item.topic_id == topic.id)
    return {
        "id": topic.id,
        "title": topic.title,
        "held_on": topic.held_on.isoformat(),
        "graded": graded,
    }


def gradebook(
    members: list[TutorStudent], topics: list[TutorTopic], scores: list[TutorScore]
) -> list[dict]:
    """One row per student. Marks follow the topic list. A blank cell is ungraded."""
    marks = {(item.topic_id, item.student_id): item.score for item in scores}
    rows = [
        {
            "student_id": member.id,
            "name": member.name,
            "marks": [marks.get((topic.id, member.id)) for topic in topics],
        }
        for member in members
    ]
    rows.sort(key=lambda row: row["name"].casefold())
    return rows


def _meets_today(weekdays: str, moment: datetime | None = None) -> bool:
    now = moment or datetime.now(TASHKENT)
    days = {int(part) for part in weekdays.split(",") if part}
    return now.isoweekday() in days


def _public_group(group: TutorGroup, ranking: list[dict], student_id: int) -> dict:
    return {
        "group_id": group.id,
        "name": group.name,
        "level": group.level,
        "today": _meets_today(group.weekdays),
        "weekdays": [int(part) for part in group.weekdays.split(",")],
        "start": _hhmm(group.start_min),
        "end": _hhmm(group.end_min),
        "ranking": [
            {
                "name": item["name"],
                "total": item["total"],
                "rank": item["rank"],
                "mine": item["student_id"] == student_id,
            }
            for item in ranking
        ],
    }


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise GradeError("empty")
    text = _SPACE.sub(" ", value).strip()
    if not text:
        raise GradeError("empty")
    if len(text) > TITLE_MAX:
        raise GradeError("long")
    return text


def _day(value: object) -> date:
    if not isinstance(value, str):
        raise GradeError("date")
    match = _DAY.fullmatch(value.strip())
    if match is None:
        raise GradeError("date")
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise GradeError("date") from exc


def _score(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10:
        raise GradeError("score")
    return value
