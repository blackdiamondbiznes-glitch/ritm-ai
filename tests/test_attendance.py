"""Attendance marks, the excused rate, and the planner lock."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.db.repositories.attendance import AttendanceRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.services.attendance import AttendanceError, AttendanceService, attendance_rate
from app.services.sessions import SessionPlanner
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, LEARNER = 9864100001, 9864100002
# Monday 2026-11-16 08:00 in Asia/Tashkent.
NOW = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
TODAY = datetime(2026, 11, 16, 13, 0, tzinfo=UTC)
TOMORROW = datetime(2026, 11, 17, 13, 0, tzinfo=UTC)
NOV_EDGE = datetime(2026, 11, 30, 18, 0, tzinfo=UTC)
DEC_EDGE = datetime(2026, 11, 30, 19, 30, tzinfo=UTC)


def test_rate_counts_excused_as_marked_but_not_attended() -> None:
    """Excused is in the denominator only. A blank mark is in neither."""
    row = attendance_rate([None, "present", "late", "excused", "absent"])
    assert row == {"attended": 2, "marked": 4, "rate": 0.5}
    assert attendance_rate([]) == {"attended": 0, "marked": 0, "rate": None}


async def _wipe(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_((OWNER, LEARNER)))
    lessons = select(TutorLesson.id).where(TutorLesson.owner_id.in_(ids))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorAttendance).where(TutorAttendance.lesson_id.in_(lessons)))
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(ids)))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_((OWNER, LEARNER))))


def _lesson(
    owner_id: int, space_id: int, group_id: int, start: datetime, title: str
) -> TutorLesson:
    return TutorLesson(
        owner_id=owner_id,
        workspace_id=space_id,
        group_id=group_id,
        title=title,
        status="scheduled",
        source="schedule",
        amount_uzs=0,
        starts_at=start,
        ends_at=start + timedelta(hours=1, minutes=30),
        planned_at=start,
    )


@pytest.fixture
async def db():
    if not _URL.startswith("postgresql"):
        pytest.skip("Postgres is required")
    engine = create_async_engine(_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _wipe(session)
        await session.commit()
    try:
        yield factory
    finally:
        async with factory() as session:
            await _wipe(session)
            await session.commit()
        await engine.dispose()


async def _seed(session) -> dict:
    owner = User(telegram_id=OWNER, full_name="Lola", language_code="uz")
    learner = User(telegram_id=LEARNER, full_name="Ali", language_code="uz")
    session.add_all([owner, learner])
    await session.flush()
    space = Workspace(owner_id=owner.id, vertical="tutor", name="Kabinet")
    session.add(space)
    await session.flush()
    group = TutorGroup(
        owner_id=owner.id,
        workspace_id=space.id,
        name="Ingliz",
        weekdays="1",
        start_min=18 * 60,
        end_min=19 * 60 + 30,
        enroll_code="attphase3",
    )
    session.add(group)
    await session.flush()
    ali = TutorStudent(
        owner_id=owner.id,
        workspace_id=space.id,
        name="Ali",
        status="paid",
        amount_uzs=0,
        telegram_id=LEARNER,
        join_code="attali1",
    )
    bex = TutorStudent(
        owner_id=owner.id,
        workspace_id=space.id,
        name="Bex",
        status="paid",
        amount_uzs=0,
        join_code="attbex1",
    )
    outsider = TutorStudent(
        owner_id=owner.id,
        workspace_id=space.id,
        name="Begona",
        status="paid",
        amount_uzs=0,
        join_code="attout1",
    )
    session.add_all([ali, bex, outsider])
    await session.flush()
    session.add(TutorGroupMember(group_id=group.id, student_id=ali.id, status="active"))
    session.add(TutorGroupMember(group_id=group.id, student_id=bex.id, status="pending"))
    today = _lesson(owner.id, space.id, group.id, TODAY, "Bugun")
    tomorrow = _lesson(owner.id, space.id, group.id, TOMORROW, "Ertaga")
    november = _lesson(owner.id, space.id, group.id, NOV_EDGE, "Oxiri")
    december = _lesson(owner.id, space.id, group.id, DEC_EDGE, "Yangi")
    session.add_all([today, tomorrow, november, december])
    await session.flush()
    return {
        "owner_id": owner.id,
        "learner_id": learner.id,
        "group_id": group.id,
        "ali": ali.id,
        "bex": bex.id,
        "outsider": outsider.id,
        "today": today.id,
        "tomorrow": tomorrow.id,
        "november": november.id,
        "december": december.id,
    }


def _service(session, **kwargs) -> AttendanceService:
    return AttendanceService(
        AttendanceRepository(session),
        LessonRepository(session),
        GroupRepository(session),
        now=kwargs.get("now", lambda: NOW),
    )


async def test_save_upserts_clears_and_rejects_the_wrong_people(db) -> None:
    async with db() as session:
        ids = await _seed(session)
        service = _service(session)
        saved = await service.save(
            ids["owner_id"],
            ids["today"],
            {"marks": [{"student_id": ids["ali"], "status": "present"}]},
        )
        assert saved["status"] == "done"
        assert saved["students"] == [
            {"student_id": ids["ali"], "name": "Ali", "status": "present", "note": None}
        ]
        again = await service.save(
            ids["owner_id"],
            ids["today"],
            {"marks": [{"student_id": ids["ali"], "status": "late", "note": "  10 min  "}]},
        )
        assert again["students"][0]["status"] == "late"
        assert again["students"][0]["note"] == "10 min"
        cleared = await service.save(
            ids["owner_id"], ids["today"], {"marks": [{"student_id": ids["ali"], "status": ""}]}
        )
        assert cleared["students"][0]["status"] is None
        assert cleared["status"] == "done"
        with pytest.raises(AttendanceError) as pending:
            await service.save(
                ids["owner_id"],
                ids["today"],
                {"marks": [{"student_id": ids["bex"], "status": "present"}]},
            )
        assert pending.value.code == "student"
        with pytest.raises(AttendanceError) as foreign:
            await service.save(
                ids["owner_id"],
                ids["today"],
                {"marks": [{"student_id": ids["outsider"], "status": "absent"}]},
            )
        assert foreign.value.code == "student"
        with pytest.raises(AttendanceError) as future:
            await service.save(
                ids["owner_id"],
                ids["tomorrow"],
                {"marks": [{"student_id": ids["ali"], "status": "present"}]},
            )
        assert future.value.code == "future"
        tomorrow = await service.sheet(ids["owner_id"], ids["tomorrow"])
        assert tomorrow["status"] == "scheduled"
        with pytest.raises(AttendanceError) as missing:
            await service.sheet(ids["learner_id"], ids["today"])
        assert missing.value.code == "missing"


async def test_month_uses_tashkent_and_history_is_only_the_member(db) -> None:
    async with db() as session:
        ids = await _seed(session)
        service = _service(session)
        marks = AttendanceRepository(session)
        stamp = NOW
        await marks.upsert(ids["november"], ids["ali"], "present", None, stamp)
        await marks.upsert(ids["december"], ids["ali"], "excused", None, stamp)
        await service.save(
            ids["owner_id"],
            ids["today"],
            {"marks": [{"student_id": ids["ali"], "status": "present"}]},
        )
        november = await service.group_stats(ids["owner_id"], ids["group_id"], "2026-11")
        assert [row["title"] for row in november["sessions"]] == ["Bugun", "Ertaga", "Oxiri"]
        ali = november["students"][0]
        assert ali["marks"] == ["present", None, "present"]
        assert ali["attended"] == 2 and ali["marked"] == 2 and ali["rate"] == 1
        december = await service.group_stats(ids["owner_id"], ids["group_id"], "2026-12")
        assert [row["title"] for row in december["sessions"]] == ["Yangi"]
        assert december["students"][0]["rate"] == 0
        learner = await session.get(User, ids["learner_id"])
        history = await service.student_history(learner, ids["group_id"])
        assert history["attended"] == 2 and history["marked"] == 3
        assert [row["status"] for row in history["marks"]] == ["excused", "present", "present"]
        owner = await session.get(User, ids["owner_id"])
        with pytest.raises(AttendanceError) as own:
            await service.student_history(owner, ids["group_id"])
        assert own.value.code == "missing"
        with pytest.raises(AttendanceError) as other:
            await service.group_stats(ids["learner_id"], ids["group_id"], "2026-11")
        assert other.value.code == "missing"


async def test_a_marked_session_is_not_replaced(db) -> None:
    async with db() as session:
        ids = await _seed(session)
        service = _service(session)
        await service.save(
            ids["owner_id"],
            ids["today"],
            {"marks": [{"student_id": ids["ali"], "status": "present"}]},
        )
        lesson = await session.get(TutorLesson, ids["today"])
        lesson.status = "scheduled"
        await session.flush()
        group = await session.get(TutorGroup, ids["group_id"])
        group.weekdays = "3"
        planner = SessionPlanner(
            LessonRepository(session),
            GroupRepository(session),
            now=lambda: NOW,
            attendance=AttendanceRepository(session),
        )
        await planner.refill(group)
        kept = await session.get(TutorLesson, ids["today"])
        assert kept is not None and kept.starts_at == TODAY
        assert await session.get(TutorLesson, ids["tomorrow"]) is None
        assert await session.get(TutorLesson, ids["november"]) is None
        assert await session.get(TutorLesson, ids["december"]) is None
        stmt = select(TutorLesson).where(TutorLesson.group_id == ids["group_id"])
        rows = list((await session.execute(stmt)).scalars().all())
        assert ids["today"] in {row.id for row in rows}
        assert any(
            row.planned_at and row.planned_at.astimezone(UTC).isoweekday() == 3 for row in rows
        )
