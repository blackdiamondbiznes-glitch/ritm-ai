"""Tutor groups: weekly slot, owner isolation, and a student in two groups."""

import pytest
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent
from app.services.groups import GroupError, GroupService, parse_group


class _Groups:
    def __init__(self) -> None:
        self.groups: list[TutorGroup] = []
        self.links: list[TutorGroupMember] = []
        self._next = 1

    async def list_for_owner(self, owner_id: int) -> list[tuple[TutorGroup, int]]:
        rows = []
        for group in self.groups:
            if group.owner_id != owner_id:
                continue
            count = sum(1 for link in self.links if link.group_id == group.id)
            rows.append((group, count))
        return rows

    async def get_owned(self, owner_id: int, group_id: int) -> TutorGroup | None:
        for group in self.groups:
            if group.id == group_id and group.owner_id == owner_id:
                return group
        return None

    async def members(self, group_id: int) -> list[TutorStudent]:
        ids = {link.student_id for link in self.links if link.group_id == group_id}
        return [row for row in _Students.rows if row.id in ids and row.owner_id]

    async def membership(self, group_id: int, student_id: int) -> TutorGroupMember | None:
        for link in self.links:
            if link.group_id == group_id and link.student_id == student_id:
                return link
        return None

    async def add(self, row: TutorGroup) -> TutorGroup:
        row.id = self._next
        self._next += 1
        self.groups.append(row)
        return row

    async def add_member(self, row: TutorGroupMember) -> TutorGroupMember:
        self.links.append(row)
        return row

    async def save(self, row: TutorGroup) -> TutorGroup:
        return row

    async def delete(self, row: TutorGroup) -> None:
        self.groups.remove(row)
        self.links = [link for link in self.links if link.group_id != row.id]

    async def delete_member(self, row: TutorGroupMember) -> None:
        self.links.remove(row)


class _Students:
    rows = [
        TutorStudent(id=4, owner_id=1, name="Ali", status="paid", amount_uzs=0),
        TutorStudent(id=5, owner_id=1, name="Vali", status="debtor", amount_uzs=10),
        TutorStudent(id=9, owner_id=2, name="Begona", status="paid", amount_uzs=0),
    ]

    async def list_for_owner(self, owner_id: int) -> list[TutorStudent]:
        return [row for row in self.rows if row.owner_id == owner_id]

    async def get_owned(self, owner_id: int, student_id: int) -> TutorStudent | None:
        for row in self.rows:
            if row.id == student_id and row.owner_id == owner_id:
                return row
        return None


def _service() -> GroupService:
    return GroupService(_Groups(), _Students())


async def test_same_student_can_sit_in_two_groups() -> None:
    service = _service()
    morning = await service.create(
        1,
        {
            "name": "Ingliz",
            "level": "A1",
            "weekdays": [1, 3, 5],
            "start": "08:00",
            "end": "10:00",
        },
    )
    evening = await service.create(
        1, {"name": "Matematika", "weekdays": [1, 3], "start": "10:30", "end": "12:30"}
    )
    first = morning["created_id"]
    second = evening["created_id"]
    opened = await service.add_student(1, first, 4)
    await service.add_student(1, second, 4)
    again = await service.add_student(1, first, 4)
    assert [item["name"] for item in opened["members"]] == ["Ali"]
    assert [item["id"] for item in again["members"]] == [4]
    both = await service.open(1, second)
    assert [item["name"] for item in both["members"]] == ["Ali"]
    assert morning["groups"][0]["start"] == "08:00"
    with pytest.raises(GroupError) as stolen:
        await service.add_student(1, first, 9)
    assert stolen.value.code == "student"
    with pytest.raises(GroupError):
        await service.open(2, first)


def test_rejects_a_bad_slot() -> None:
    for body in (
        {},
        {"name": "A", "weekdays": [], "start": "08:00", "end": "10:00"},
        {"name": "A", "weekdays": [1], "start": "10:00", "end": "10:00"},
        {"name": "A", "weekdays": [8], "start": "08:00", "end": "09:00"},
        {"name": "A", "weekdays": [1], "start": "25:00", "end": "26:00"},
    ):
        with pytest.raises(GroupError):
            parse_group(body)
    current = TutorGroup(
        owner_id=1, name="Ingliz", level="A1", weekdays="1,3,5", start_min=8 * 60, end_min=10 * 60
    )
    parsed = parse_group({"name": "Ingliz B1"}, current)
    assert parsed.level == "A1" and parsed.start_min == 8 * 60 and parsed.weekdays == "1,3,5"
