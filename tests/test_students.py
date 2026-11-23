"""Tutor student validation and owner isolation, without a database."""

from datetime import UTC, datetime

import pytest
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.services.students import StudentError, StudentService, parse_student


class _Repo:
    def __init__(self) -> None:
        self.rows: list[TutorStudent] = []
        self._next = 1

    async def list_for_owner(self, owner_id: int) -> list[TutorStudent]:
        return [row for row in self.rows if row.owner_id == owner_id]

    async def get_owned(self, owner_id: int, student_id: int) -> TutorStudent | None:
        for row in self.rows:
            if row.id == student_id and row.owner_id == owner_id:
                return row
        return None

    async def add(self, row: TutorStudent) -> TutorStudent:
        row.id = self._next
        self._next += 1
        self.rows.append(row)
        return row

    async def save(self, row: TutorStudent) -> TutorStudent:
        return row

    async def delete(self, row: TutorStudent) -> None:
        self.rows.remove(row)


def _service() -> tuple[StudentService, _Repo]:
    repo = _Repo()
    return StudentService(repo), repo


async def test_create_lists_only_the_owner_and_counts() -> None:
    service, _repo = _service()
    await service.create(
        1, {"name": "  Ali   Vali ", "phone": "+998 90 123 45 67", "amount_uzs": 150000}
    )
    await service.create(1, {"name": "Dilnoza", "status": "paid", "amount_uzs": 0})
    await service.create(2, {"name": "Boshqa", "status": "inactive"})
    mine = await service.list(1)
    by_name = {row["name"]: row for row in mine["students"]}
    assert set(by_name) == {"Dilnoza", "Ali Vali"}
    assert by_name["Ali Vali"]["phone"] == "+998 90 123 45 67"
    assert by_name["Ali Vali"]["status"] == "debtor"
    assert mine["counts"] == {"paid": 1, "debtor": 1, "inactive": 0}
    assert (await service.list(2))["counts"]["inactive"] == 1


async def test_update_keeps_omitted_fields_and_rejects_other_owners() -> None:
    service, _repo = _service()
    created = await service.create(
        1, {"name": "Ali", "status": "paid", "amount_uzs": 10, "note": "5-sinf"}
    )
    student_id = created["students"][0]["id"]
    updated = await service.update(1, student_id, {"status": "inactive"})
    row = updated["students"][0]
    assert row["status"] == "inactive"
    assert row["name"] == "Ali" and row["amount_uzs"] == 10 and row["note"] == "5-sinf"
    with pytest.raises(StudentError) as other:
        await service.update(2, student_id, {"name": "O'g'irlangan"})
    assert other.value.code == "missing"
    assert (await service.list(1))["students"][0]["name"] == "Ali"


async def test_remove_and_validation() -> None:
    service, repo = _service()
    created = await service.create(1, {"name": "Ali"})
    student_id = created["students"][0]["id"]
    assert (await service.remove(1, student_id))["students"] == []
    with pytest.raises(StudentError) as missing:
        await service.remove(1, student_id)
    assert missing.value.code == "missing"
    before = len(repo.rows)
    for body in (
        {},
        {"name": "   "},
        {"name": "x" * 81},
        {"name": "Ali", "phone": "123"},
        {"name": "Ali", "amount_uzs": -1},
        {"name": "Ali", "amount_uzs": True},
        {"name": "Ali", "status": "vip"},
        {"name": "Ali", "note": "n" * 301},
    ):
        with pytest.raises(StudentError):
            parse_student(body)
    assert len(repo.rows) == before


async def test_profile_lists_only_this_students_lessons() -> None:
    service, _repo = _service()
    ali = await service.create(1, {"name": "Ali"})
    vali = await service.create(1, {"name": "Vali"})
    ali_id = ali["created_id"]
    lesson = TutorLesson(
        id=1, owner_id=1, student_id=ali_id, title="Algebra", status="scheduled", amount_uzs=0
    )
    other = TutorLesson(
        id=2,
        owner_id=1,
        student_id=vali["created_id"],
        title="Fizika",
        status="done",
        amount_uzs=0,
    )
    foreign = TutorLesson(
        id=3, owner_id=2, student_id=ali_id, title="Begona", status="scheduled", amount_uzs=0
    )
    service._lessons = _Named([lesson, other, foreign])
    profile = await service.profile(1, ali_id)
    assert profile["student"]["name"] == "Ali"
    assert [item["title"] for item in profile["lessons"]] == ["Algebra"]
    assert profile["reminders"] == []
    with pytest.raises(StudentError) as missing:
        await service.profile(2, ali_id)
    assert missing.value.code == "missing"


class _Named:
    def __init__(self, rows) -> None:
        self.rows = rows

    async def list_for_owner(self, owner_id: int):
        return [row for row in self.rows if row.owner_id == owner_id]


async def test_create_places_the_student_in_the_chosen_group() -> None:
    service, _repo = _service()
    groups = _GroupBook()
    service._groups = groups
    await groups.add(
        TutorGroup(id=3, owner_id=1, name="Ingliz", weekdays="1,3", start_min=480, end_min=600)
    )
    created = await service.create(1, {"name": "Ali", "group_ids": [3]})
    assert groups.links[0].student_id == created["created_id"]
    assert groups.links[0].group_id == 3
    with pytest.raises(StudentError) as missing:
        await service.create(1, {"name": "Vali"})
    assert missing.value.code == "group"


class _GroupBook:
    def __init__(self) -> None:
        self.groups: list[TutorGroup] = []
        self.links: list[TutorGroupMember] = []

    async def add(self, row: TutorGroup) -> TutorGroup:
        self.groups.append(row)
        return row

    async def list_for_owner(self, owner_id: int):
        return [(group, 0) for group in self.groups if group.owner_id == owner_id]

    async def groups_for_student(self, student_id: int):
        ids = {link.group_id for link in self.links if link.student_id == student_id}
        return [group for group in self.groups if group.id in ids]

    async def membership(self, group_id: int, student_id: int):
        for link in self.links:
            if link.group_id == group_id and link.student_id == student_id:
                return link
        return None

    async def add_member(self, row: TutorGroupMember) -> TutorGroupMember:
        self.links.append(row)
        return row

    async def delete_member(self, row: TutorGroupMember) -> None:
        self.links.remove(row)


def test_partial_update_does_not_require_a_name() -> None:
    current = TutorStudent(
        owner_id=1,
        name="Ali",
        phone=None,
        status="paid",
        amount_uzs=20,
        note=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    parsed = parse_student({"amount_uzs": 0}, current)
    assert parsed.name == "Ali" and parsed.status == "paid" and parsed.amount_uzs == 0
