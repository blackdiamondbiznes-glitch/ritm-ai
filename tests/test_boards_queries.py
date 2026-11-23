"""Student rankings load with a fixed number of queries and keep full names."""

import os
from datetime import date

import pytest
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent
from app.db.models.topics import TutorScore, TutorTopic
from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.topics import TopicRepository
from app.services.grades import GradeService
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER = 9880000001
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id == OWNER)
    group_ids = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    topic_ids = select(TutorTopic.id).where(TutorTopic.group_id.in_(group_ids))
    await session.execute(delete(TutorScore).where(TutorScore.topic_id.in_(topic_ids)))
    await session.execute(delete(TutorTopic).where(TutorTopic.group_id.in_(group_ids)))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(group_ids)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id == OWNER))


async def test_three_groups_take_at_most_five_statements() -> None:
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    statements: list[str] = []

    def before(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        async with sessions() as session:
            await _purge(session)
            owner = User(telegram_id=OWNER, full_name="Teacher", language_code="uz")
            session.add(owner)
            await session.flush()
            student = TutorStudent(
                owner_id=owner.id,
                name="Ali Valiyev",
                status="paid",
                amount_uzs=0,
                telegram_id=9880000099,
                join_code="boardcode1",
            )
            session.add(student)
            await session.flush()
            groups = []
            for index, name in enumerate(("Ingliz", "Matematika", "Fizika"), start=1):
                group = TutorGroup(
                    owner_id=owner.id,
                    name=name,
                    weekdays=str(index),
                    start_min=8 * 60 + index,
                    end_min=10 * 60,
                    enroll_code=f"board{index:02d}xx",
                )
                session.add(group)
                await session.flush()
                session.add(
                    TutorGroupMember(group_id=group.id, student_id=student.id, status="active")
                )
                topic = TutorTopic(group_id=group.id, title="Mavzu", held_on=date(2026, 11, 22))
                session.add(topic)
                await session.flush()
                session.add(TutorScore(topic_id=topic.id, student_id=student.id, score=8))
                groups.append(group)
            await session.commit()
            await session.connection()
            statements.clear()
            service = GradeService(
                GroupRepository(session),
                StudentRepository(session),
                TopicRepository(session),
            )
            boards = await service.boards_for(9880000099)
        assert len(statements) <= 5
        assert len(boards) == 3
        names = [row["name"] for board in boards for row in board["ranking"]]
        assert names == ["Ali Valiyev", "Ali Valiyev", "Ali Valiyev"]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()
