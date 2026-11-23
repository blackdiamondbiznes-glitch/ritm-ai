"""Lesson reminders: one send per target, quiet hours, blocks, and the monthly quota."""

from datetime import datetime

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage
from app.db.models.jobs import Job
from app.db.models.plans import Plan
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.tutor_notices import TutorNotice
from app.db.models.usage import UsageCounter
from app.db.repositories.usage import UsageRepository
from app.jobs.runner import JobCancel
from app.services.clock import TASHKENT
from app.services.notify_rules import METRIC, quiet_wake
from sqlalchemy import select
from tests.notify_world import BLOCKED, CHAT_TG, STUDENT, handler, open_db, service, world


@pytest.fixture
async def db():
    async for factory in open_db():
        yield factory


_SENTENCE = "Dars 1 soatdan keyin: Ingliz tili B1, 18:00"
_AT = datetime(2026, 11, 21, 18, 0, tzinfo=TASHKENT)
_NOW = datetime(2026, 11, 21, 17, 0, tzinfo=TASHKENT)


def test_quiet_hours_wait_until_eight() -> None:
    late = datetime(2026, 11, 21, 22, 30, tzinfo=TASHKENT)
    early = datetime(2026, 11, 21, 7, 30, tzinfo=TASHKENT)
    assert quiet_wake(late) == datetime(2026, 11, 22, 8, 0, tzinfo=TASHKENT)
    assert quiet_wake(early) == datetime(2026, 11, 21, 8, 0, tzinfo=TASHKENT)
    assert quiet_wake(_NOW) is None
    assert quiet_wake(datetime(2026, 11, 21, 8, 0, tzinfo=TASHKENT)) is None


class _Bot:
    def __init__(self, forbidden: set[int] | None = None, missing: set[int] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.forbidden = forbidden or set()
        self.missing = missing or set()

    async def send_message(self, chat_id: int, text: str, **_kwargs) -> None:
        method = SendMessage(chat_id=chat_id, text=text)
        if chat_id in self.forbidden:
            raise TelegramForbiddenError(method=method, message="bot was blocked by the user")
        if chat_id in self.missing:
            raise TelegramBadRequest(method=method, message="chat not found")
        self.sent.append((chat_id, text))


async def _jobs(session, owner_id: int) -> list[Job]:
    rows = (await session.execute(select(Job).where(Job.type == "tutor_notify"))).scalars()
    return [row for row in rows if row.payload.get("owner_id") == owner_id]


async def test_lesson_notice_is_sent_once_to_the_student_and_the_group(db) -> None:
    async with db() as session:
        made = await world(session, _NOW, start=_AT)
        sender = service(session, _NOW)
        await sender.enqueue_due(_NOW)
        await sender.enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        assert len(rows) == 2
        bot = _Bot()
        worker = handler(session, bot, _NOW)
        student = next(row for row in rows if row.payload["telegram_id"] == STUDENT)
        group = next(row for row in rows if row.payload["telegram_id"] == CHAT_TG)
        await worker.handle(student)
        with pytest.raises(JobCancel):
            await worker.handle(student)
        await worker.handle(group)
        assert bot.sent == [(STUDENT, _SENTENCE), (CHAT_TG, _SENTENCE)]


async def test_quiet_hours_postpone_a_morning_lesson_and_skip_a_late_one(db) -> None:
    morning = datetime(2026, 11, 21, 7, 30, tzinfo=TASHKENT)
    early = datetime(2026, 11, 21, 9, 30, tzinfo=TASHKENT)
    async with db() as session:
        made = await world(session, morning, start=early, remind=120)
        await service(session, morning).enqueue_due(morning)
        job = (await _jobs(session, made["user"].id))[0]
        assert job.run_at == datetime(2026, 11, 21, 8, 0, tzinfo=TASHKENT)
    night = datetime(2026, 11, 21, 22, 30, tzinfo=TASHKENT)
    late = datetime(2026, 11, 21, 23, 30, tzinfo=TASHKENT)
    async with db() as session:
        made = await world(session, night, start=late, remind=60)
        await service(session, night).enqueue_due(night)
        assert await _jobs(session, made["user"].id) == []
        notes = (
            await session.execute(
                select(TutorNotice).where(TutorNotice.ref_id == made["lesson"].id)
            )
        ).scalars()
        assert {row.status for row in notes} == {"skipped"}


async def test_a_blocked_student_is_skipped_and_a_missing_chat_is_not_retried(db) -> None:
    async with db() as session:
        made = await world(session, _NOW, start=_AT, blocked=True)
        await service(session, _NOW).enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        bot = _Bot(forbidden={BLOCKED})
        worker = handler(session, bot, _NOW)
        blocked = next(row for row in rows if row.payload["telegram_id"] == BLOCKED)
        with pytest.raises(JobCancel):
            await worker.handle(blocked)
        note = await session.get(TutorNotice, blocked.payload["notification_id"])
        assert note is not None and note.status == "skipped"
        group = next(row for row in rows if row.payload["telegram_id"] == CHAT_TG)
        missing = _Bot(missing={CHAT_TG})
        with pytest.raises(JobCancel):
            await handler(session, missing, _NOW).handle(group)
        gone = await session.get(TutorNotice, group.payload["notification_id"])
        assert gone is not None and gone.status == "skipped"
        assert all(chat_id != CHAT_TG for chat_id, _text in bot.sent)


async def test_user_text_is_escaped(db) -> None:
    async with db() as session:
        made = await world(session, _NOW, start=_AT, name="A & B <C>", level=None)
        await service(session, _NOW).enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        bot = _Bot()
        await handler(session, bot, _NOW).handle(rows[0])
        text = bot.sent[0][1]
        assert "&amp;" in text and "&lt;" in text
        assert "<" not in text


async def test_free_sends_nothing_and_start_stops_at_300(db) -> None:
    async with db() as session:
        made = await world(session, _NOW, start=_AT, plan="free")
        await service(session, _NOW).enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        bot = _Bot()
        with pytest.raises(JobCancel):
            await handler(session, bot, _NOW).handle(rows[0])
        assert bot.sent == []
        used = await UsageRepository(session).get_count(made["user"].id, METRIC, "2026-11")
        assert used == 0
        warning = next(
            row for row in await _jobs(session, made["user"].id) if not row.payload["quota"]
        )
        await handler(session, bot, _NOW).handle(warning)
        assert "limit" in bot.sent[0][1].lower() or "limiti" in bot.sent[0][1].lower()
        assert await UsageRepository(session).get_count(made["user"].id, METRIC, "2026-11") == 0
    async with db() as session:
        made = await world(session, _NOW, start=_AT, plan="free")
        plan = (await session.execute(select(Plan).where(Plan.code == "start"))).scalar_one()
        session.add(
            Subscription(
                owner_id=made["user"].id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=_NOW,
                expires_at=datetime(2026, 12, 21, tzinfo=TASHKENT),
            )
        )
        session.add(
            UsageCounter(owner_id=made["user"].id, metric=METRIC, period_key="2026-11", count=299)
        )
        await session.flush()
        await service(session, _NOW).enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        bot = _Bot()
        worker = handler(session, bot, _NOW)
        await worker.handle(next(row for row in rows if row.payload["telegram_id"] == STUDENT))
        assert await UsageRepository(session).get_count(made["user"].id, METRIC, "2026-11") == 300
        with pytest.raises(JobCancel):
            await worker.handle(next(row for row in rows if row.payload["telegram_id"] == CHAT_TG))
        assert len(bot.sent) == 1
        assert await UsageRepository(session).get_count(made["user"].id, METRIC, "2026-11") == 300
