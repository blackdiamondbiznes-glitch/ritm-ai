"""Cabinet home: counts from the owner's students and lessons."""

from __future__ import annotations

from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.students import StudentRepository


class CabinetService:
    """Read the numbers shown on the cabinet home."""

    def __init__(self, students: StudentRepository, lessons: LessonRepository) -> None:
        self._students = students
        self._lessons = lessons

    async def summary(self, owner_id: int) -> dict:
        """Student counts, debt total, and lesson counts for one owner."""
        students = await self._students.list_for_owner(owner_id)
        lessons = await self._lessons.list_for_owner(owner_id)
        return summarize(students, lessons)


def summarize(students: list[TutorStudent], lessons: list[TutorLesson]) -> dict:
    """Turn the two lists into the cabinet cards. Debt is the sum owed."""
    student_counts = {"paid": 0, "debtor": 0, "inactive": 0}
    debt = 0
    for row in students:
        if row.status == "pending":
            continue
        student_counts[row.status] = student_counts.get(row.status, 0) + 1
        if row.status == "debtor":
            debt += row.amount_uzs
    lesson_counts = {"scheduled": 0, "done": 0, "cancelled": 0}
    for row in lessons:
        lesson_counts[row.status] = lesson_counts.get(row.status, 0) + 1
    return {
        "students": {**student_counts, "debt_uzs": debt},
        "lessons": lesson_counts,
    }
