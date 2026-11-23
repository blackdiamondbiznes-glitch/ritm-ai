"""One payload for every group a student attends. Queries do not grow with groups."""

from __future__ import annotations

from datetime import date

from app.db.models.invoices import TutorInvoice
from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.learning import LearningRepository
from app.db.repositories.topics import TopicRepository
from app.services.attendance import attendance_rate
from app.services.clock import Clock, utcnow
from app.services.grades import rank
from app.services.groups import _hhmm

LAST = 10


class LearningService:
    """Build the student cabinet from a fixed set of reads."""

    def __init__(
        self,
        learning: LearningRepository,
        groups: GroupRepository,
        topics: TopicRepository,
        now: Clock | None = None,
    ) -> None:
        self._learning = learning
        self._groups = groups
        self._topics = topics
        self._now = now or utcnow

    async def for_user(self, user: User) -> dict:
        """Active groups and pending requests for this account, never groups they teach."""
        if user.telegram_id is None:
            return {"groups": [], "pending": []}
        seats = await self._learning.seats(user.telegram_id, user.id)
        active = [seat for seat in seats if seat[0].status == "active"]
        pending = [_pending(seat) for seat in seats if seat[0].status == "pending"]
        if not active:
            return {"groups": [], "pending": pending}
        return {"groups": await self._groups_payload(active), "pending": pending}

    async def _groups_payload(self, seats: list) -> list[dict]:
        group_ids = [group.id for _member, group, _student, _teacher in seats]
        student_ids = [student.id for _member, _group, student, _teacher in seats]
        nxt = await self._learning.next_lessons(group_ids, self._now())
        marks = await self._learning.marks(student_ids, group_ids)
        bills = await self._learning.invoices(group_ids, student_ids)
        members = await self._groups.active_members(group_ids)
        topics = await self._topics.list_for_groups(group_ids)
        scores = await self._topics.scores_for([topic.id for topic in topics])
        by_members = _bucket_members(members)
        by_topics, by_scores = _bucket_topics(topics, scores)
        by_marks = _bucket_marks(marks)
        by_bills = _bucket_bills(bills)
        found = [
            _card(seat, nxt, by_marks, by_bills, by_members, by_topics, by_scores) for seat in seats
        ]
        found.sort(key=lambda item: (item["group"]["start"], item["group"]["id"]))
        return found


def _card(seat, nxt, by_marks, by_bills, by_members, by_topics, by_scores) -> dict:
    member, group, student, teacher = seat
    topics = by_topics.get(group.id, [])
    scores = [score for topic in topics for score in by_scores.get(topic.id, [])]
    lesson = nxt.get(group.id)
    return {
        "group": _group(group, teacher),
        "next_session": _next(lesson),
        "attendance": _attendance(by_marks.get((student.id, group.id), [])),
        "fee": _fee(group, by_bills.get((group.id, student.id), [])),
        "ranking": _ranking(by_members.get(group.id, []), scores, student.id),
        "scores": _my_scores(topics, by_scores, student.id),
        "homework": _homework(topics),
    }


def _group(group, teacher: str | None) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "level": group.level,
        "teacher_name": teacher or "",
        "weekdays": [int(part) for part in group.weekdays.split(",") if part],
        "start": _hhmm(group.start_min),
        "end": _hhmm(group.end_min),
        "chat_linked": group.chat_id is not None,
    }


def _next(lesson) -> dict | None:
    if lesson is None or lesson.starts_at is None:
        return None
    return {
        "starts_at": lesson.starts_at.isoformat(),
        "status": lesson.status,
        "meeting_url": getattr(lesson, "meeting_url", None),
    }


def _attendance(rows: list[tuple]) -> dict:
    last = [
        {
            "starts_at": start.isoformat() if start is not None else None,
            "status": status,
            "title": title,
        }
        for status, start, title in rows[:LAST]
    ]
    return {
        "rate": attendance_rate([status for status, _start, _title in rows])["rate"],
        "last": last,
    }


def _fee(group, rows: list[TutorInvoice]) -> dict | None:
    if group.fee_mode == "none":
        return None
    current = _current(rows)
    if current is None:
        return None
    return {
        "mode": group.fee_mode,
        "amount": current.amount_uzs,
        "due_on": current.due_on.isoformat(),
        "status": current.status,
        "paid": current.paid_uzs,
        "lessons_used": current.lessons_used,
        "lessons_total": current.lessons_total,
    }


def _current(rows: list[TutorInvoice]) -> TutorInvoice | None:
    open_rows = [row for row in rows if row.status in ("due", "overdue")]
    if open_rows:
        return open_rows[0]
    return rows[-1] if rows else None


def _ranking(members, scores, student_id: int) -> list[dict]:
    return [
        {
            "name": item["name"],
            "total": item["total"],
            "rank": item["rank"],
            "mine": item["student_id"] == student_id,
        }
        for item in rank(members, scores)
    ]


def _my_scores(topics, by_scores, student_id: int) -> list[dict]:
    found = []
    for topic in topics:
        for score in by_scores.get(topic.id, []):
            if score.student_id != student_id:
                continue
            found.append((topic.held_on, topic.id, topic.title, score.score))
    found.sort(reverse=True)
    return [
        {"topic": title, "held_on": held.isoformat(), "score": score}
        for held, _topic_id, title, score in found[:LAST]
    ]


def _homework(topics) -> list[dict]:
    rows = [topic for topic in topics if topic.homework]
    rows.sort(key=lambda topic: (topic.homework_due or date.min, topic.id), reverse=True)
    return [
        {
            "topic": topic.title,
            "text": topic.homework,
            "due_on": topic.homework_due.isoformat() if topic.homework_due else None,
        }
        for topic in rows
    ]


def _pending(seat) -> dict:
    member, group, _student, teacher = seat
    return {
        "group_name": group.name,
        "teacher_name": teacher or "",
        "created_at": member.created_at.isoformat() if member.created_at else None,
    }


def _bucket_members(rows) -> dict:
    found: dict[int, list] = {}
    for group_id, student in rows:
        found.setdefault(group_id, []).append(student)
    return found


def _bucket_topics(topics, scores) -> tuple[dict, dict]:
    by_topic: dict[int, list] = {}
    for score in scores:
        by_topic.setdefault(score.topic_id, []).append(score)
    by_group: dict[int, list] = {}
    for topic in topics:
        by_group.setdefault(topic.group_id, []).append(topic)
    return by_group, by_topic


def _bucket_marks(rows) -> dict:
    found: dict[tuple[int, int], list] = {}
    for student_id, group_id, status, start, title in rows:
        found.setdefault((int(student_id), int(group_id)), []).append((status, start, title))
    return found


def _bucket_bills(rows: list[TutorInvoice]) -> dict:
    found: dict[tuple[int, int], list] = {}
    for row in rows:
        found.setdefault((row.group_id, row.student_id), []).append(row)
    return found
