"""Group ranking sums 0–10 marks. Ungraded students stay off the board."""

from datetime import date

from app.db.models.students import TutorStudent
from app.db.models.topics import TutorScore
from app.services.grades import rank


def _student(student_id: int, name: str) -> TutorStudent:
    return TutorStudent(
        id=student_id, owner_id=1, name=name, status="paid", amount_uzs=0, join_code="abc"
    )


def _score(student_id: int, score: int, topic_id: int = 1) -> TutorScore:
    return TutorScore(topic_id=topic_id, student_id=student_id, score=score)


def test_ties_share_a_place_and_zero_counts() -> None:
    members = [_student(1, "Ali"), _student(2, "Vali"), _student(3, "Sami"), _student(4, "Nora")]
    scores = [_score(1, 8), _score(2, 8), _score(3, 0), _score(1, 2, topic_id=2)]
    placed = rank(members, scores)
    assert [(item["name"], item["total"], item["rank"]) for item in placed] == [
        ("Ali", 10, 1),
        ("Vali", 8, 2),
        ("Sami", 0, 3),
    ]


def test_a_real_day_parses() -> None:
    from app.services.grades import _day

    assert _day("2026-11-21") == date(2026, 11, 21)
