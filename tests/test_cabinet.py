"""Cabinet home counts come from the owner's students and lessons."""

from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.services.cabinet import summarize


def _student(status: str, amount: int) -> TutorStudent:
    return TutorStudent(owner_id=1, name="A", status=status, amount_uzs=amount)


def _lesson(status: str) -> TutorLesson:
    return TutorLesson(owner_id=1, title="Dars", status=status, amount_uzs=0)


def test_empty_cabinet_is_zero() -> None:
    data = summarize([], [])
    assert data["students"] == {"paid": 0, "debtor": 0, "inactive": 0, "debt_uzs": 0}
    assert data["lessons"] == {"scheduled": 0, "done": 0, "cancelled": 0}


def test_debt_is_the_sum_of_owing_students_only() -> None:
    data = summarize(
        [_student("debtor", 150_000), _student("debtor", 20_000), _student("paid", 80_000)],
        [_lesson("scheduled"), _lesson("done")],
    )
    assert data["students"]["debtor"] == 2
    assert data["students"]["paid"] == 1
    assert data["students"]["debt_uzs"] == 170_000
    assert data["lessons"]["scheduled"] == 1
    assert data["lessons"]["done"] == 1


def test_pending_cards_stay_off_the_cabinet() -> None:
    data = summarize([_student("pending", 50_000), _student("debtor", 10)], [])
    assert data["students"]["debtor"] == 1
    assert data["students"]["debt_uzs"] == 10
    assert "pending" not in data["students"]
