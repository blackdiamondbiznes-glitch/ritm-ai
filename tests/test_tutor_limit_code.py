"""A missing owner raises the limit that the caller was checking."""

import pytest
from app.services.tutor_limits import TutorLimitError, ensure_group_room, ensure_student_room


class _Users:
    async def get_by_id(self, user_id: int):
        return None


async def test_a_missing_owner_keeps_the_callers_limit_code() -> None:
    users = _Users()
    with pytest.raises(TutorLimitError) as students:
        await ensure_student_room(None, users, None, 1)  # type: ignore[arg-type]
    assert students.value.code == "limit_students"
    with pytest.raises(TutorLimitError) as groups:
        await ensure_group_room(None, users, None, 1)  # type: ignore[arg-type]
    assert groups.value.code == "limit_groups"
