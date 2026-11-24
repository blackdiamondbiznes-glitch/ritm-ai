"""Student homework submission and teacher grading workflows."""

from __future__ import annotations

from datetime import UTC, datetime

from app.db.models.homework_submissions import TutorHomeworkSubmission
from app.db.models.topics import TutorScore
from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.homework_submissions import HomeworkSubmissionRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.topics import TopicRepository

BODY_MAX = 5000
FEEDBACK_MAX = 1000


class HomeworkSubmissionError(ValueError):
    """Invalid or unauthorized homework operation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HomeworkSubmissionService:
    """Enforce active membership for students and ownership for teachers."""

    def __init__(
        self,
        submissions: HomeworkSubmissionRepository,
        topics: TopicRepository,
        groups: GroupRepository,
        students: StudentRepository,
    ) -> None:
        self._submissions = submissions
        self._topics = topics
        self._groups = groups
        self._students = students

    async def student_tasks(self, user: User) -> list[dict]:
        """Only homework from groups where this Telegram account is active."""
        if user.telegram_id is None:
            return []
        cards = await self._students.by_telegram(user.telegram_id)
        card_by_id = {card.id: card for card in cards}
        seats = await self._groups.active_for_students(list(card_by_id))
        seats = [
            (group, student_id)
            for group, student_id in seats
            if group.owner_id != user.id and student_id in card_by_id
        ]
        group_names = {group.id: group.name for group, _student_id in seats}
        students_by_group: dict[int, list[int]] = {}
        for group, student_id in seats:
            students_by_group.setdefault(group.id, []).append(student_id)
        topics = [
            topic
            for topic in await self._topics.list_for_groups(list(group_names))
            if topic.homework
        ]
        submissions = await self._submissions.for_topics([topic.id for topic in topics])
        by_pair = {(row.topic_id, row.student_id): row for row in submissions}
        result = []
        for topic in topics:
            for student_id in students_by_group[topic.group_id]:
                submission = by_pair.get((topic.id, student_id))
                result.append(
                    {
                        "topic_id": topic.id,
                        "group_id": topic.group_id,
                        "group": group_names[topic.group_id],
                        "title": topic.title,
                        "homework": topic.homework,
                        "due_on": topic.homework_due.isoformat() if topic.homework_due else None,
                        "status": "todo" if submission is None else submission.status,
                        "submission_id": None if submission is None else submission.id,
                        "answer": None if submission is None else submission.body,
                        "score": None if submission is None else submission.score,
                        "feedback": None if submission is None else submission.feedback,
                        "submitted_at": (
                            None if submission is None else submission.submitted_at.isoformat()
                        ),
                        "student_id": student_id,
                        "student": card_by_id[student_id].name,
                    }
                )
        result.sort(key=lambda item: (item["due_on"] or "9999-12-31", item["topic_id"]))
        return result

    async def submit(self, user: User, topic_id: int, raw_body: object) -> dict:
        """Create or replace an ungraded submission for an active group member."""
        if user.telegram_id is None:
            raise HomeworkSubmissionError("student_link_required")
        body = _answer(raw_body)
        topic = await self._topics.get(topic_id)
        if topic is None or topic.homework is None:
            raise HomeworkSubmissionError("missing")
        seat = await self._groups.active_study(user.telegram_id, topic.group_id, user.id)
        if seat is None:
            raise HomeworkSubmissionError("missing")
        _group, student = seat
        row = await self._submissions.get_for(topic.id, student.id)
        if row is not None and row.status == "graded":
            raise HomeworkSubmissionError("graded")
        now = datetime.now(UTC)
        if row is None:
            row = TutorHomeworkSubmission(
                topic_id=topic.id,
                student_id=student.id,
                body=body,
                status="submitted",
                submitted_at=now,
            )
        else:
            row.body = body
            row.status = "submitted"
            row.score = None
            row.feedback = None
            row.submitted_at = now
            row.graded_at = None
        await self._submissions.save(row)
        return {"topic_id": topic.id, "status": row.status, "submitted_at": now.isoformat()}

    async def teacher_tasks(self, owner_id: int) -> list[dict]:
        """Assignments, counts, and submissions for one teacher's groups."""
        groups = await self._groups.list_for_owner(owner_id)
        group_names = {group.id: group.name for group, _count in groups}
        group_totals = {group.id: count for group, count in groups}
        topics = [
            topic
            for topic in await self._topics.list_for_groups(list(group_names))
            if topic.homework
        ]
        topic_ids = [topic.id for topic in topics]
        submissions = await self._submissions.for_topics(topic_ids)
        students = {
            student.id: student
            for student in await self._students.list_for_owner(owner_id)
        }
        by_topic: dict[int, list[TutorHomeworkSubmission]] = {}
        for submission in submissions:
            by_topic.setdefault(submission.topic_id, []).append(submission)
        assignments = []
        for topic in topics:
            topic_submissions = by_topic.get(topic.id, [])
            total = group_totals.get(topic.group_id, 0)
            graded = sum(item.status == "graded" for item in topic_submissions)
            status = (
                "review"
                if any(item.status == "submitted" for item in topic_submissions)
                else "done"
                if total > 0 and graded >= total
                else "active"
            )
            assignments.append({
                "topic_id": topic.id,
                "group_id": topic.group_id,
                "group": group_names[topic.group_id],
                "title": topic.title,
                "homework": topic.homework,
                "due_on": topic.homework_due.isoformat() if topic.homework_due else None,
                "status": status,
                "submitted": len(topic_submissions),
                "total": total,
                "submissions": [
                    {
                        "id": submission.id,
                        "student_id": submission.student_id,
                        "student": students[submission.student_id].name,
                        "answer": submission.body,
                        "status": submission.status,
                        "score": submission.score,
                        "feedback": submission.feedback,
                        "submitted_at": submission.submitted_at.isoformat(),
                    }
                    for submission in topic_submissions
                    if submission.student_id in students
                ],
            })
        return assignments

    async def grade(self, owner_id: int, submission_id: int, body: dict) -> dict:
        """Save teacher feedback and mirror a 0–10 grade to the existing gradebook."""
        row = await self._submissions.get(submission_id)
        if row is None:
            raise HomeworkSubmissionError("missing")
        topic = await self._topics.get(row.topic_id)
        if topic is None or await self._groups.get_owned(owner_id, topic.group_id) is None:
            raise HomeworkSubmissionError("missing")
        score = _score(body.get("score"))
        feedback = _feedback(body.get("feedback"))
        student = await self._students.get_owned(owner_id, row.student_id)
        if student is None:
            raise HomeworkSubmissionError("missing")
        row.status = "graded"
        row.score = score
        row.feedback = feedback
        row.graded_at = datetime.now(UTC)
        await self._submissions.save(row)
        current = await self._topics.score(topic.id, student.id)
        if current is None:
            await self._topics.add_score(
                TutorScore(topic_id=topic.id, student_id=student.id, score=score)
            )
        else:
            current.score = score
            await self._topics.save_score(current)
        return {"submission_id": row.id, "status": row.status, "score": score}


def _answer(value: object) -> str:
    if not isinstance(value, str):
        raise HomeworkSubmissionError("answer")
    answer = value.strip()
    if not answer or len(answer) > BODY_MAX:
        raise HomeworkSubmissionError("answer")
    return answer


def _score(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
        raise HomeworkSubmissionError("score")
    return value


def _feedback(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HomeworkSubmissionError("feedback")
    feedback = value.strip()
    if len(feedback) > FEEDBACK_MAX:
        raise HomeworkSubmissionError("feedback")
    return feedback or None
