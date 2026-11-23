"""Fee reminders stay private unless asked, and cancel or move tells the same chats."""

from datetime import date, datetime, timedelta

import pytest
from app.db.models.invoices import TutorInvoice
from app.db.models.jobs import Job
from app.db.models.lessons import TutorLesson
from app.db.models.reminders import TutorReminder
from app.db.models.usage import UsageCounter
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.usage import UsageRepository
from app.jobs.runner import JobCancel
from app.services.clock import TASHKENT
from app.services.notify_rules import METRIC
from app.services.session_view import SessionView
from sqlalchemy import select
from tests.notify_world import CHAT_TG, STUDENT, handler, open_db, service, world
from tests.test_notify import _Bot, _jobs

_NOW = datetime(2026, 11, 21, 12, 0, tzinfo=TASHKENT)
_GROUP = "To'lov muddati yaqinlashdi, iltimos o'qituvchingiz bilan bog'laning"


@pytest.fixture
async def db():
    async for factory in open_db():
        yield factory


async def _invoice(session, made: dict, due: date, period: date) -> None:
    session.add(
        TutorInvoice(
            workspace_id=made["group"].workspace_id,
            group_id=made["group"].id,
            student_id=made["student"].id,
            kind="monthly",
            period_start=period,
            amount_uzs=300_000,
            due_on=due,
            status="due",
        )
    )
    await session.flush()


async def test_fee_reminders_are_private_unless_the_group_hides_the_debt(db) -> None:
    async with db() as session:
        made = await world(session, _NOW, remind=None)
        await _invoice(session, made, date(2026, 11, 24), date(2026, 11, 1))
        await _invoice(session, made, date(2026, 11, 20), date(2026, 10, 1))
        await service(session, _NOW).enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        assert {row.payload["template"] for row in rows} == {
            "notify_fee_student",
            "notify_fee_digest",
        }
        assert all(row.payload["telegram_id"] != CHAT_TG for row in rows)
        bot = _Bot()
        private = next(row for row in rows if row.payload["template"] == "notify_fee_student")
        await handler(session, bot, _NOW).handle(private)
        assert "300000" in bot.sent[0][1]
    async with db() as session:
        made = await world(session, _NOW, remind=None, fee_in_group=True)
        await _invoice(session, made, date(2026, 11, 24), date(2026, 11, 1))
        await service(session, _NOW).enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        group = next(row for row in rows if row.payload["telegram_id"] == CHAT_TG)
        bot = _Bot()
        await handler(session, bot, _NOW).handle(group)
        assert bot.sent == [(CHAT_TG, _GROUP)]
        assert "300000" not in bot.sent[0][1] and "Ali" not in bot.sent[0][1]


async def test_the_teacher_digest_does_not_use_the_quota(db) -> None:
    async with db() as session:
        made = await world(session, _NOW, remind=None)
        await _invoice(session, made, date(2026, 11, 24), date(2026, 11, 1))
        session.add(
            UsageCounter(owner_id=made["user"].id, metric=METRIC, period_key="2026-11", count=300)
        )
        await session.flush()
        await service(session, _NOW).enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        digest = next(row for row in rows if row.payload["template"] == "notify_fee_digest")
        assert digest.payload["quota"] is False
        bot = _Bot()
        await handler(session, bot, _NOW).handle(digest)
        assert bot.sent[0][0] == made["user"].telegram_id
        assert await UsageRepository(session).get_count(made["user"].id, METRIC, "2026-11") == 300
        private = next(row for row in rows if row.payload["template"] == "notify_fee_student")
        with pytest.raises(JobCancel):
            await handler(session, bot, _NOW).handle(private)


async def test_cancel_and_move_notify_the_same_chats(db) -> None:
    start = datetime(2026, 11, 21, 18, 0, tzinfo=TASHKENT)
    async with db() as session:
        made = await world(session, _NOW, start=start, remind=None)
        view = SessionView(
            LessonRepository(session), GroupRepository(session), notifier=service(session, _NOW)
        )
        await view.update(made["user"].id, made["lesson"].id, {"status": "cancelled"})
        rows = await _jobs(session, made["user"].id)
        assert {row.payload["template"] for row in rows} == {"notify_cancel"}
        assert {row.payload["telegram_id"] for row in rows} == {STUDENT, CHAT_TG}
        bot = _Bot()
        await handler(session, bot, _NOW).handle(rows[0])
        assert "bekor" in bot.sent[0][1] and "18:00" in bot.sent[0][1]
        await service(session, _NOW).enqueue_due(_NOW)
        assert len(await _jobs(session, made["user"].id)) == 2
    async with db() as session:
        made = await world(session, _NOW, start=start, remind=None)
        view = SessionView(
            LessonRepository(session), GroupRepository(session), notifier=service(session, _NOW)
        )
        await view.update(
            made["user"].id,
            made["lesson"].id,
            {"starts_at": "2026-11-21T19:00", "ends_at": "2026-11-21T20:00"},
        )
        rows = await _jobs(session, made["user"].id)
        assert {row.payload["template"] for row in rows} == {"notify_move"}
        bot = _Bot()
        await handler(session, bot, _NOW).handle(rows[0])
        assert "19:00" in bot.sent[0][1]
        solo = TutorLesson(
            owner_id=made["user"].id,
            workspace_id=made["group"].workspace_id,
            title="Yakka",
            status="scheduled",
            source="manual",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        session.add(solo)
        await session.flush()
        before = len(await _jobs(session, made["user"].id))
        await view.update(made["user"].id, solo.id, {"status": "cancelled"})
        assert len(await _jobs(session, made["user"].id)) == before


async def test_a_scheduled_student_reminder_is_queued_once(db) -> None:
    async with db() as session:
        made = await world(session, _NOW, remind=None, fee_days=None)
        reminder = TutorReminder(
            owner_id=made["user"].id,
            student_id=made["student"].id,
            audience="student",
            text="A & <b>",
            send_at=_NOW,
        )
        session.add(reminder)
        await session.flush()
        sender = service(session, _NOW)
        await sender.enqueue_due(_NOW)
        await sender.enqueue_due(_NOW)
        rows = await _jobs(session, made["user"].id)
        assert len(rows) == 1 and rows[0].type == "tutor_notify"
        bot = _Bot()
        await handler(session, bot, _NOW).handle(rows[0])
        assert bot.sent == [(STUDENT, "A &amp; &lt;b&gt;")]
        owner_jobs = (
            await session.execute(select(Job).where(Job.type == "tutor_reminder"))
        ).scalars()
        assert all(row.payload.get("reminder_id") != reminder.id for row in owner_jobs)
