"""Tutor lesson validation, Tashkent time, and owner isolation."""

from datetime import UTC, datetime

import pytest
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.services.lessons import LessonError, LessonService, parse_lesson


class _Lessons:
    def __init__(self) -> None:
        self.rows: list[TutorLesson] = []
        self._next = 1

    async def list_for_owner(self, owner_id: int) -> list[TutorLesson]:
        return [row for row in self.rows if row.owner_id == owner_id]

    async def get_owned(self, owner_id: int, lesson_id: int) -> TutorLesson | None:
        for row in self.rows:
            if row.id == lesson_id and row.owner_id == owner_id:
                return row
        return None

    async def add(self, row: TutorLesson) -> TutorLesson:
        row.id = self._next
        self._next += 1
        self.rows.append(row)
        return row

    async def save(self, row: TutorLesson) -> TutorLesson:
        return row

    async def delete(self, row: TutorLesson) -> None:
        self.rows.remove(row)


class _Students:
    def __init__(self, rows: list[TutorStudent]) -> None:
        self.rows = rows

    async def list_for_owner(self, owner_id: int) -> list[TutorStudent]:
        return [row for row in self.rows if row.owner_id == owner_id]

    async def get_owned(self, owner_id: int, student_id: int) -> TutorStudent | None:
        for row in self.rows:
            if row.id == student_id and row.owner_id == owner_id:
                return row
        return None


def _service() -> LessonService:
    ali = TutorStudent(id=4, owner_id=1, name="Ali", status="paid", amount_uzs=0)
    other = TutorStudent(id=9, owner_id=2, name="Begona", status="paid", amount_uzs=0)
    return LessonService(_Lessons(), _Students([ali, other]))


async def test_create_links_only_an_owned_student_and_stores_tashkent_time() -> None:
    service = _service()
    created = await service.create(
        1,
        {
            "title": "  Algebra  ",
            "student_id": 4,
            "starts_at": "2026-11-21T15:30",
            "amount_uzs": 50000,
        },
    )
    row = created["lessons"][0]
    assert row["title"] == "Algebra"
    assert row["student_name"] == "Ali"
    assert row["status"] == "scheduled"
    assert row["starts_at"].startswith("2026-11-21T10:30:00")
    with pytest.raises(LessonError) as stolen:
        await service.create(1, {"title": "Sir", "student_id": 9})
    assert stolen.value.code == "student"
    assert len((await service.list(2))["lessons"]) == 0


async def test_update_status_keeps_omitted_fields() -> None:
    service = _service()
    created = await service.create(1, {"title": "Algebra", "student_id": 4, "amount_uzs": 10})
    lesson_id = created["lessons"][0]["id"]
    updated = await service.update(1, lesson_id, {"status": "done"})
    row = updated["lessons"][0]
    assert row["status"] == "done"
    assert row["title"] == "Algebra" and row["student_id"] == 4 and row["amount_uzs"] == 10
    with pytest.raises(LessonError) as other:
        await service.update(2, lesson_id, {"title": "Olingan"})
    assert other.value.code == "missing"


def test_rejects_bad_lesson_input() -> None:
    for body in (
        {},
        {"title": "  "},
        {"title": "x" * 121},
        {"title": "Dars", "starts_at": "21.11.2026 15:30"},
        {"title": "Dars", "starts_at": "2026-02-31T10:00"},
        {"title": "Dars", "student_id": True},
        {"title": "Dars", "status": "paid"},
        {"title": "Dars", "amount_uzs": -1},
    ):
        with pytest.raises(LessonError):
            parse_lesson(body)
    kept = TutorLesson(
        owner_id=1,
        title="Algebra",
        student_id=4,
        status="scheduled",
        amount_uzs=0,
        starts_at=datetime(2026, 11, 21, 10, 30, tzinfo=UTC),
        note=None,
    )
    parsed = parse_lesson({"status": "cancelled"}, kept)
    assert parsed.title == "Algebra" and parsed.starts_at == kept.starts_at
