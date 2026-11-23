"""Group ranking sums 0–10 marks. A tutor cannot claim their own student link."""

from datetime import date

from app.db.models.students import TutorStudent
from app.db.models.topics import TutorScore
from app.db.models.users import User
from app.services.enrollment import EnrollmentService
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


class _Students:
    def __init__(self, row: TutorStudent) -> None:
        self.row = row

    async def by_join_code(self, code: str) -> TutorStudent | None:
        return self.row if self.row.join_code == code else None

    async def save(self, row: TutorStudent) -> TutorStudent:
        self.row = row
        return row

    async def by_owner_telegram(self, owner_id: int, telegram_id: int) -> TutorStudent | None:
        if self.row.owner_id == owner_id and self.row.telegram_id == telegram_id:
            return self.row
        return None


class _Spaces:
    async def id_for(self, owner_id: int, vertical: str = "tutor") -> int:
        return 1


class _Users:
    def __init__(self, owner: User) -> None:
        self.owner = owner

    async def get_by_id(self, user_id: int) -> User | None:
        return self.owner if self.owner.id == user_id else None


async def test_tutor_cannot_claim_their_own_student() -> None:
    student = TutorStudent(
        id=4, owner_id=1, name="Ali", status="paid", amount_uzs=0, join_code="abc123"
    )
    owner = User(id=1, telegram_id=555, full_name="Tutor")
    service = EnrollmentService(None, _Students(student), _Users(owner), _Spaces())  # type: ignore[arg-type]
    assert await service.claim("abc123", 555) == "own"
    assert student.telegram_id is None
    assert await service.claim("abc123", 777) == "ok"
    assert student.telegram_id == 777


def test_gradebook_lines_marks_up_with_topics() -> None:
    from app.db.models.topics import TutorTopic
    from app.services.grades import gradebook

    members = [_student(2, "Vali"), _student(1, "Ali")]
    topics = [
        TutorTopic(id=1, group_id=1, title="Kasr", held_on=date(2026, 11, 21)),
        TutorTopic(id=2, group_id=1, title="Foiz", held_on=date(2026, 11, 22)),
    ]
    scores = [_score(1, 8, 1), _score(1, 10, 2)]
    rows = gradebook(members, topics, scores)
    assert [row["name"] for row in rows] == ["Ali", "Vali"]
    assert rows[0]["marks"] == [8, 10]
    assert rows[1]["marks"] == [None, None]


def test_a_real_day_parses() -> None:
    from app.services.grades import _day

    assert _day("2026-11-21") == date(2026, 11, 21)
