"""Tutor reminders must not inflate the admin AI charts."""

import os
from datetime import UTC, datetime

import pytest
from app.db.models.usage import UsageCounter, UsageDaily
from app.db.models.users import User
from app.services.charts import platform_charts
from app.services.clock import TASHKENT
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
TG = 9866100001
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id == TG)
    await session.execute(delete(UsageDaily).where(UsageDaily.owner_id.in_(ids)))
    await session.execute(delete(UsageCounter).where(UsageCounter.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id == TG))


@pytest.fixture
async def db():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        await session.commit()
    try:
        yield sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


async def test_tutor_notifications_are_not_ai_usage(db) -> None:
    local = datetime.now(UTC).astimezone(TASHKENT)
    month = local.strftime("%Y-%m")
    async with db() as session:
        before = await platform_charts(session, days=7, founder_slots=20)
    async with db() as session:
        user = User(telegram_id=TG, full_name="AI", language_code="uz")
        session.add(user)
        await session.flush()
        session.add_all(
            [
                UsageCounter(owner_id=user.id, metric="ai_generation", period_key=month, count=3),
                UsageCounter(owner_id=user.id, metric="tutor_notify", period_key=month, count=9),
                UsageDaily(owner_id=user.id, metric="ai_generation", day=local.date(), count=4),
                UsageDaily(owner_id=user.id, metric="tutor_notify", day=local.date(), count=8),
            ]
        )
        await session.commit()
    async with db() as session:
        after = await platform_charts(session, days=7, founder_slots=20)
    assert after["months"][-1]["ai"] - before["months"][-1]["ai"] == 3
    assert after["daily"][-1]["ai"] - before["daily"][-1]["ai"] == 4
