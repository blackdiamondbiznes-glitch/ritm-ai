"""The student cabinet is one payload, with a fixed number of queries."""

import os
from datetime import UTC, date, datetime, timedelta

import pytest
from app.db.models.attendance import TutorAttendance
from app.db.models.chats import Chat, ChatType
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.models.topics import TutorScore, TutorTopic
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.db.repositories.groups import GroupRepository
from app.db.repositories.learning import LearningRepository
from app.db.repositories.topics import TopicRepository
from app.services.clock import TASHKENT
from app.services.learning import LearningService
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
A, B, PUPIL, OTHER = 9864700001, 9864700002, 9864700003, 9864700004
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=TASHKENT)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session, ids: tuple[int, ...]) -> None:
    owners = select(User.id).where(User.telegram_id.in_(ids))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(owners))
    topics = select(TutorTopic.id).where(TutorTopic.group_id.in_(groups))
    lessons = select(TutorLesson.id).where(TutorLesson.owner_id.in_(owners))
    await session.execute(delete(TutorScore).where(TutorScore.topic_id.in_(topics)))
    await session.execute(delete(TutorTopic).where(TutorTopic.group_id.in_(groups)))
    await session.execute(delete(TutorAttendance).where(TutorAttendance.lesson_id.in_(lessons)))
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(owners)))
    await session.execute(delete(TutorInvoice).where(TutorInvoice.group_id.in_(groups)))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(owners)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(owners)))
    await session.execute(delete(Chat).where(Chat.owner_id.in_(owners)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(owners)))
    await session.execute(delete(User).where(User.telegram_id.in_(ids)))


async def _user(session, telegram: int, name: str) -> tuple[User, Workspace]:
    user = User(telegram_id=telegram, full_name=name, language_code="uz")
    session.add(user)
    await session.flush()
    space = Workspace(owner_id=user.id, vertical="tutor", name="Kabinet")
    session.add(space)
    await session.flush()
    return user, space


def _service(session) -> LearningService:
    return LearningService(
        LearningRepository(session),
        GroupRepository(session),
        TopicRepository(session),
        now=lambda: NOW,
    )


async def test_two_teachers_and_a_pending_request_stay_in_their_places() -> None:
    engine = create_async_engine(_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _purge(session, (A, B, PUPIL, OTHER))
        teacher_a, space_a = await _user(session, A, "Lola Karimova")
        teacher_b, space_b = await _user(session, B, "Sardor Aliyev")
        pupil, space_p = await _user(session, PUPIL, "Ali")
        other, _space_o = await _user(session, OTHER, "Begona")
        chat = Chat(
            telegram_chat_id=-100986470111,
            type=ChatType.GROUP,
            title="Ingliz",
            owner_id=teacher_a.id,
            added_at=NOW,
            is_active=True,
        )
        session.add(chat)
        await session.flush()
        english = _group(teacher_a, space_a, "Ingliz tili", "B1", "eng6code", chat.id, "monthly")
        maths = _group(teacher_b, space_b, "Matematika", None, "mat6code", None, "package")
        waiting = _group(teacher_a, space_a, "Fizika", None, "fiz6code", None, "none")
        own = _group(pupil, space_p, "Mening", None, "own6code", None, "none")
        session.add_all([english, maths, waiting, own])
        await session.flush()
        ali_a = _card(teacher_a, space_a, "Ali Valiyev", PUPIL, "ali-a")
        ali_b = _card(teacher_b, space_b, "Ali Valiyev", PUPIL, "ali-b")
        vali = _card(teacher_a, space_a, "Vali Karimov", None, "vali-a")
        self_card = _card(pupil, space_p, "Ali Valiyev", PUPIL, "ali-own")
        session.add_all([ali_a, ali_b, vali, self_card])
        await session.flush()
        session.add_all(
            [
                _member(english, ali_a, "active"),
                _member(english, vali, "active"),
                _member(maths, ali_b, "active"),
                _member(waiting, ali_a, "pending"),
                _member(own, self_card, "active"),
            ]
        )
        await _lesson(session, teacher_a, space_a, english, NOW + timedelta(days=2), "scheduled")
        for index in range(12):
            start = datetime(2026, 10, 1, 8, 0, tzinfo=TASHKENT) + timedelta(days=index)
            lesson = await _lesson(session, teacher_a, space_a, english, start, "done")
            session.add(
                TutorAttendance(
                    lesson_id=lesson.id,
                    student_id=ali_a.id,
                    status="present" if index % 2 == 0 else "absent",
                )
            )
        session.add_all(
            [
                _bill(space_a, english, ali_a, "monthly", 300_000, date(2026, 12, 5), None, 0),
                _bill(space_b, maths, ali_b, "package", 100_000, date(2026, 12, 1), 12, 7),
            ]
        )
        await _scores(session, english, ali_a, vali)
        await session.commit()
        payload = await _service(session).for_user(pupil)
        hidden = await _service(session).for_user(teacher_a)
        stranger = await _service(session).for_user(other)
    try:
        names = [item["group"]["name"] for item in payload["groups"]]
        assert names == ["Ingliz tili", "Matematika"]
        assert [item["group_name"] for item in payload["pending"]] == ["Fizika"]
        assert "Mening" not in names
        english_card = payload["groups"][0]
        maths_card = payload["groups"][1]
        assert english_card["group"]["teacher_name"] == "Lola Karimova"
        assert maths_card["group"]["teacher_name"] == "Sardor Aliyev"
        assert english_card["group"]["chat_linked"] is True
        assert maths_card["group"]["chat_linked"] is False
        assert english_card["next_session"]["status"] == "scheduled"
        assert english_card["next_session"]["starts_at"].startswith("2026-11-23")
        assert english_card["fee"]["amount"] == 300_000
        assert english_card["fee"]["status"] == "due"
        assert maths_card["fee"]["lessons_used"] == 7
        assert maths_card["fee"]["lessons_total"] == 12
        assert english_card["attendance"]["rate"] == 0.5
        assert len(english_card["attendance"]["last"]) == 10
        ranked = [row["name"] for row in english_card["ranking"]]
        assert ranked == ["Ali Valiyev", "Vali Karimov"]
        assert english_card["ranking"][0]["mine"] is True
        assert english_card["scores"][0]["topic"] == "Mavzu 10"
        assert len(english_card["scores"]) == 10
        assert hidden == {"groups": [], "pending": []}
        assert stranger == {"groups": [], "pending": []}
    finally:
        async with factory() as session:
            await _purge(session, (A, B, PUPIL, OTHER))
            await session.commit()
        await engine.dispose()


async def test_a_running_lesson_stays_next_until_it_ends() -> None:
    """The join button stays while the lesson runs: next_session holds it until ends_at."""
    engine = create_async_engine(_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _purge(session, (A, PUPIL))
        teacher, space = await _user(session, A, "Lola Karimova")
        pupil, _space_p = await _user(session, PUPIL, "Ali")
        english = _group(teacher, space, "Ingliz tili", "B1", "eng7code", None, "none")
        session.add(english)
        await session.flush()
        ali = _card(teacher, space, "Ali Valiyev", PUPIL, "ali-run")
        session.add(ali)
        await session.flush()
        session.add(_member(english, ali, "active"))
        await _lesson(session, teacher, space, english, NOW - timedelta(hours=2), "done")
        await _lesson(session, teacher, space, english, NOW - timedelta(minutes=30), "scheduled")
        await _lesson(session, teacher, space, english, NOW + timedelta(days=2), "scheduled")
        await session.commit()
        payload = await _service(session).for_user(pupil)
    try:
        nxt = payload["groups"][0]["next_session"]
        running = NOW - timedelta(minutes=30)
        assert datetime.fromisoformat(nxt["starts_at"]) == running
        assert datetime.fromisoformat(nxt["ends_at"]) == running + timedelta(hours=1)
    finally:
        async with factory() as session:
            await _purge(session, (A, PUPIL))
            await session.commit()
        await engine.dispose()


def _group(owner, space, name, level, code, chat_id, mode) -> TutorGroup:
    return TutorGroup(
        owner_id=owner.id,
        workspace_id=space.id,
        name=name,
        level=level,
        weekdays="1",
        start_min=18 * 60,
        end_min=19 * 60 + 30,
        enroll_code=code,
        chat_id=chat_id,
        fee_mode=mode,
        fee_uzs=300_000 if mode != "none" else 0,
        package_lessons=12 if mode == "package" else None,
        billing_day=1 if mode == "monthly" else None,
    )


def _card(owner, space, name, telegram, code) -> TutorStudent:
    return TutorStudent(
        owner_id=owner.id,
        workspace_id=space.id,
        name=name,
        status="paid",
        amount_uzs=0,
        telegram_id=telegram,
        join_code=code,
    )


def _member(group, student, status) -> TutorGroupMember:
    return TutorGroupMember(group_id=group.id, student_id=student.id, status=status, created_at=NOW)


async def _lesson(session, owner, space, group, start, status) -> TutorLesson:
    row = TutorLesson(
        owner_id=owner.id,
        workspace_id=space.id,
        group_id=group.id,
        title="Dars",
        status=status,
        source="manual",
        starts_at=start.astimezone(UTC),
        ends_at=(start + timedelta(hours=1)).astimezone(UTC),
    )
    session.add(row)
    await session.flush()
    return row


def _bill(space, group, student, kind, amount, due, total, used) -> TutorInvoice:
    return TutorInvoice(
        workspace_id=space.id,
        group_id=group.id,
        student_id=student.id,
        kind=kind,
        period_start=date(2026, 11, 1),
        amount_uzs=amount,
        due_on=due,
        status="due",
        lessons_total=total,
        lessons_used=used,
    )


async def _scores(session, group, ali, vali) -> None:
    for index in range(11):
        topic = TutorTopic(
            group_id=group.id,
            title=f"Mavzu {index}",
            held_on=date(2026, 10, 1) + timedelta(days=index),
        )
        session.add(topic)
        await session.flush()
        session.add(TutorScore(topic_id=topic.id, student_id=ali.id, score=8))
        if index == 0:
            session.add(TutorScore(topic_id=topic.id, student_id=vali.id, score=7))
