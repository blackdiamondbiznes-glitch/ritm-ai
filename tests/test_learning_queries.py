"""Three groups must not cost more queries than one."""

from datetime import date, timedelta

import pytest
from app.db.models.attendance import TutorAttendance
from app.db.models.topics import TutorScore, TutorTopic
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.test_learning import (
    _URL,
    NOW,
    _bill,
    _card,
    _group,
    _lesson,
    _member,
    _purge,
    _service,
    _user,
)

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def test_three_groups_use_the_same_number_of_statements_as_one() -> None:
    engine = create_async_engine(_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    one_id, all_id = 9864800002, 9864800003
    ids = (9864800001, one_id, all_id)
    statements: list[str] = []

    def before(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        async with factory() as session:
            await _purge(session, ids)
            teacher, space = await _user(session, ids[0], "O‘qituvchi")
            one, _one_space = await _user(session, one_id, "Bitta")
            many, _many_space = await _user(session, all_id, "Uchta")
            groups = []
            for index in range(3):
                group = _group(
                    teacher, space, f"Guruh {index}", None, f"st{index}code", None, "monthly"
                )
                session.add(group)
                await session.flush()
                groups.append(group)
            one_card = _card(teacher, space, "Bitta O‘quvchi", one_id, "one-card")
            many_card = _card(teacher, space, "Uchta O‘quvchi", all_id, "all-card")
            session.add_all([one_card, many_card])
            await session.flush()
            session.add(_member(groups[0], one_card, "active"))
            for group in groups:
                session.add(_member(group, many_card, "active"))
                await _lesson(session, teacher, space, group, NOW + timedelta(days=1), "scheduled")
                lesson = await _lesson(
                    session, teacher, space, group, NOW - timedelta(days=1), "done"
                )
                session.add(
                    TutorAttendance(lesson_id=lesson.id, student_id=many_card.id, status="present")
                )
                session.add(
                    _bill(space, group, many_card, "monthly", 1000, date(2026, 12, 1), None, 0)
                )
                topic = TutorTopic(group_id=group.id, title="Mavzu", held_on=date(2026, 11, 1))
                session.add(topic)
                await session.flush()
                session.add(TutorScore(topic_id=topic.id, student_id=many_card.id, score=8))
            session.add(
                _bill(space, groups[0], one_card, "monthly", 1000, date(2026, 12, 2), None, 0)
            )
            topic = TutorTopic(group_id=groups[0].id, title="Yana", held_on=date(2026, 11, 2))
            session.add(topic)
            await session.flush()
            session.add(TutorScore(topic_id=topic.id, student_id=one_card.id, score=6))
            await session.commit()
            await session.connection()
            service = _service(session)
            statements.clear()
            await service.for_user(one)
            single = len(statements)
            statements.clear()
            payload = await service.for_user(many)
            triple = len(statements)
        assert single == triple
        assert triple <= 10
        assert len(payload["groups"]) == 3
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)
        async with factory() as session:
            await _purge(session, ids)
            await session.commit()
        await engine.dispose()
