"""Group timetable slots, idempotent fill, and the once-a-day claim."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from app.db.models.groups import TutorGroup
from app.db.models.lessons import TutorLesson
from app.db.models.system_state import SystemState
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.jobs.tutor_sessions import refill_sessions
from app.services.sessions import KIND, SessionPlanner, has_attendance, sessions_due, slots_for
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
TG = 9862000001
# Monday 2026-11-16 23:30 in Asia/Tashkent (UTC+5).
NOW = datetime(2026, 11, 16, 18, 30, tzinfo=UTC)
_MON = (
    datetime(2026, 11, 16, 13, 0, tzinfo=UTC),
    datetime(2026, 11, 18, 13, 0, tzinfo=UTC),
    datetime(2026, 11, 20, 13, 0, tzinfo=UTC),
    datetime(2026, 11, 23, 13, 0, tzinfo=UTC),
    datetime(2026, 11, 25, 13, 0, tzinfo=UTC),
    datetime(2026, 11, 27, 13, 0, tzinfo=UTC),
)


def _group() -> TutorGroup:
    return TutorGroup(
        owner_id=1,
        workspace_id=1,
        name="Ingliz",
        weekdays="1,3,5",
        start_min=18 * 60,
        end_min=19 * 60 + 30,
        enroll_code="slot",
    )


def test_monday_night_plans_six_tashkent_slots() -> None:
    assert datetime(2026, 11, 16).isoweekday() == 1
    slots = slots_for(_group(), NOW, 14)
    assert [start for start, _end in slots] == list(_MON)
    assert slots[0][1] == datetime(2026, 11, 16, 14, 30, tzinfo=UTC)
    # 00:30 Tashkent Tuesday is still Monday in UTC. The horizon follows Tashkent.
    early = datetime(2026, 11, 16, 19, 30, tzinfo=UTC)
    assert [start for start, _end in slots_for(_group(), early, 14)][0] == _MON[1]


def test_sessions_run_once_per_tashkent_day() -> None:
    assert sessions_due(NOW, None) == "2026-11-16"
    assert sessions_due(NOW, "2026-11-16") is None
    edge = datetime(2026, 11, 16, 19, 30, tzinfo=UTC)
    assert sessions_due(edge, "2026-11-16") == "2026-11-17"


def test_attendance_locks_only_a_marked_session() -> None:
    row = TutorLesson(owner_id=1, workspace_id=1, title="Dars", status="scheduled", amount_uzs=0)
    row.id = 7
    assert has_attendance(row) is False
    assert has_attendance(row, set()) is False
    assert has_attendance(row, {7}) is True


async def _wipe(session) -> None:
    ids = select(User.id).where(User.telegram_id == TG)
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(ids)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id == TG))
    await session.execute(delete(SystemState).where(SystemState.key == KIND))


async def _seed(session) -> TutorGroup:
    user = User(telegram_id=TG, full_name="Owner", language_code="uz")
    session.add(user)
    await session.flush()
    space = Workspace(owner_id=user.id, vertical="tutor", name="Kabinet")
    session.add(space)
    await session.flush()
    group = TutorGroup(
        owner_id=user.id,
        workspace_id=space.id,
        name="Ingliz",
        weekdays="1,3,5",
        start_min=18 * 60,
        end_min=19 * 60 + 30,
        enroll_code="sessphase2",
    )
    session.add(group)
    await session.flush()
    return group


def _planner(session) -> SessionPlanner:
    return SessionPlanner(LessonRepository(session), GroupRepository(session), now=lambda: NOW)


async def _rows(session, group_id: int) -> list[TutorLesson]:
    stmt = (
        select(TutorLesson)
        .where(TutorLesson.group_id == group_id)
        .order_by(TutorLesson.planned_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


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


async def test_fill_keeps_cancelled_and_moved_slots(db) -> None:
    async with db() as session:
        group = await _seed(session)
        planner = _planner(session)
        assert await planner.fill(group) == 6
        assert await planner.fill(group) == 0
        rows = await _rows(session, group.id)
        assert [row.starts_at for row in rows] == list(_MON)
        assert all(row.ends_at == row.starts_at + timedelta(hours=1, minutes=30) for row in rows)
        cancelled, moved = rows[2], rows[1]
        cancelled.status = "cancelled"
        moved.starts_at = moved.starts_at + timedelta(hours=1)
        await session.flush()
        assert await planner.fill(group) == 0
        again = await _rows(session, group.id)
        assert len(again) == 6
        assert again[2].status == "cancelled" and again[2].id == cancelled.id
        assert again[1].id == moved.id
        assert again[1].starts_at == _MON[1] + timedelta(hours=1)
        assert again[1].planned_at == _MON[1]


async def test_weekday_change_replaces_only_untouched_future_sessions(db) -> None:
    async with db() as session:
        group = await _seed(session)
        planner = _planner(session)
        await planner.fill(group)
        rows = await _rows(session, group.id)
        past, moved, cancelled = rows[0], rows[1], rows[2]
        cancelled.status = "cancelled"
        moved.starts_at = moved.starts_at + timedelta(hours=1)
        await session.flush()
        group.weekdays = "1,5"
        await planner.refill(group)
        left = await _rows(session, group.id)
        by_id = {row.id: row for row in left}
        assert past.id in by_id and by_id[past.id].starts_at == _MON[0]
        assert by_id[moved.id].starts_at == _MON[1] + timedelta(hours=1)
        assert by_id[cancelled.id].status == "cancelled"
        planned = {row.planned_at for row in left}
        assert _MON[4] not in planned
        assert _MON[3] in planned and _MON[5] in planned
        assert len(left) == 5


async def test_daily_refill_claims_the_tashkent_day(db) -> None:
    async with db() as session:
        group = await _seed(session)
        assert await refill_sessions(session, now=lambda: NOW) is True
        assert len(await _rows(session, group.id)) == 6
        assert await refill_sessions(session, now=lambda: NOW) is False
        assert len(await _rows(session, group.id)) == 6
