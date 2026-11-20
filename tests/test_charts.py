"""M4 chart aggregations on real Postgres: timezones, gap filling, deltas, revenue."""

import os
from datetime import UTC, date, datetime, timedelta

import pytest
from app.db.models.audit import AuditLog
from app.db.models.chats import Chat, ChatProfile, ChatType
from app.db.models.content import ContentItem, ContentKind
from app.db.models.jobs import Job
from app.db.models.payments import Payment, PaymentEvent
from app.db.models.plans import Plan
from app.db.models.quizzes import Quiz, QuizAnswer
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.usage import UsageCounter, UsageDaily
from app.db.models.users import User
from app.services.charts import ChartService, Window, change_pct, pick_days, platform_charts
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.pg import allow_purge

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
U1, U2, U3, OWNER = 9810000001, 9810000002, 9810000003, 9810000009
_IDS = (U1, U2, U3, OWNER)
CHAT_A, CHAT_B = -9810000001, -9810000002
NOW = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)  # 15:00 in Tashkent

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


async def purge(s) -> None:
    await allow_purge(s)
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    chats = select(Chat.id).where(Chat.telegram_chat_id.in_((CHAT_A, CHAT_B)))
    quizzes = select(Quiz.id).where(Quiz.chat_id.in_(chats))
    pays = select(Payment.id).where(Payment.owner_id.in_(ids))
    await s.execute(delete(QuizAnswer).where(QuizAnswer.quiz_id.in_(quizzes)))
    await s.execute(delete(Quiz).where(Quiz.chat_id.in_(chats)))
    await s.execute(delete(ContentItem).where(ContentItem.chat_id.in_(chats)))
    await s.execute(delete(Job).where(Job.chat_id.in_(chats)))
    await s.execute(delete(ChatProfile).where(ChatProfile.chat_id.in_(chats)))
    await s.execute(delete(Chat).where(Chat.telegram_chat_id.in_((CHAT_A, CHAT_B))))
    await s.execute(delete(PaymentEvent).where(PaymentEvent.payment_id.in_(pays)))
    await s.execute(delete(Payment).where(Payment.owner_id.in_(ids)))
    await s.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await s.execute(delete(UsageDaily).where(UsageDaily.owner_id.in_(ids)))
    await s.execute(delete(UsageCounter).where(UsageCounter.owner_id.in_(ids)))
    await s.execute(delete(AuditLog).where(or_(AuditLog.actor_user_id.in_(ids))))
    await s.execute(delete(User).where(User.telegram_id.in_(_IDS)))


def profile(chat_id: int, zone: str) -> ChatProfile:
    return ChatProfile(
        chat_id=chat_id,
        niche_code="ielts",
        niche_description="IELTS",
        tone="friendly",
        audience_level="mixed",
        timezone=zone,
        modules_enabled=["quiz"],
        updated_at=NOW,
    )


def quiz(chat_id: int, created: str) -> Quiz:
    return Quiz(
        chat_id=chat_id,
        question="Q?",
        options=["a", "b"],
        correct_index=0,
        mode="group_native",
        created_at=at(created),
    )


@pytest.fixture
async def db():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        await purge(s)
        await s.commit()
    try:
        yield sessions
    finally:
        async with sessions() as s:
            await purge(s)
            await s.commit()
        await engine.dispose()


@pytest.fixture
async def world(db):
    """Chat A in Tashkent (+5), chat B in UTC. One answer lands on different days per zone."""
    async with db() as s:
        users = {
            tg: User(telegram_id=tg, full_name=f"P{tg % 10}", language_code="uz") for tg in _IDS
        }
        s.add_all(users.values())
        await s.flush()
        a = Chat(
            telegram_chat_id=CHAT_A,
            type=ChatType.GROUP,
            title="A",
            owner_id=users[OWNER].id,
            added_at=NOW,
        )
        b = Chat(
            telegram_chat_id=CHAT_B,
            type=ChatType.GROUP,
            title="B",
            owner_id=users[OWNER].id,
            added_at=NOW,
        )
        s.add_all([a, b])
        await s.flush()
        s.add_all([profile(a.id, "Asia/Tashkent"), profile(b.id, "UTC")])
        qa0, qa1, qb1 = (
            quiz(a.id, "2026-11-10T08:00"),
            quiz(a.id, "2026-11-20T19:00"),
            quiz(b.id, "2026-11-20T20:00"),
        )
        qb0 = quiz(b.id, "2026-11-16T20:00")
        s.add_all([qa0, qa1, qb1, qb0])
        s.add(
            ContentItem(
                chat_id=a.id,
                kind=ContentKind.DAILY,
                body="post",
                meta={},
                published_at=at("2026-11-17T12:00"),
            )
        )
        await s.flush()

        def answer(q, tg, ok, when):
            return QuizAnswer(
                quiz_id=q.id,
                user_id=users[tg].id,
                chosen_index=0 if ok else 1,
                is_correct=ok,
                answered_at=at(when),
            )

        s.add_all(
            [
                answer(qa0, U1, True, "2026-11-10T09:00"),  # previous window
                answer(qa1, U1, True, "2026-11-20T20:30"),  # A: local 21st 01:30
                answer(qa1, U2, False, "2026-11-21T05:00"),  # A: local 21st 10:00
                answer(qb1, U1, True, "2026-11-20T20:30"),  # B: 20th 20:30 UTC
                answer(qb0, U3, True, "2026-11-16T23:30"),  # B: Monday 16th 23:30
            ]
        )
        await s.commit()
        ids = {tg: users[tg].id for tg in _IDS}
    return {"sessions": db, "a": a.id, "b": b.id, "users": ids}


def svc(s) -> ChartService:
    return ChartService(s, default_timezone="Asia/Tashkent", points_per_correct=10, now=lambda: NOW)


async def test_all_chats_series_respects_each_chat_timezone_and_fills_gaps(world) -> None:
    async with world["sessions"]() as s:
        data = await svc(s).chats([(world["a"], "A"), (world["b"], "B")], 7, scope="all")
    assert data["start"] == "2026-11-15" and data["end"] == "2026-11-21"
    series = {row["date"]: row for row in data["series"]}
    assert list(series) == [f"2026-11-{d}" for d in range(15, 22)]
    assert series["2026-11-15"] == {
        "date": "2026-11-15",
        "posts": 0,
        "quizzes": 0,
        "answers": 0,
        "correct": 0,
        "participants": 0,
        "accuracy": None,
    }
    assert series["2026-11-16"]["answers"] == 1 and series["2026-11-16"]["quizzes"] == 1
    assert series["2026-11-17"]["posts"] == 1
    assert series["2026-11-19"]["answers"] == 0
    # 20:30 UTC on the 20th: the 20th in chat B (UTC), the 21st in chat A (Tashkent).
    assert series["2026-11-20"]["answers"] == 1 and series["2026-11-20"]["quizzes"] == 1
    assert series["2026-11-21"]["answers"] == 2 and series["2026-11-21"]["quizzes"] == 1
    assert series["2026-11-21"]["participants"] == 2 and series["2026-11-21"]["accuracy"] == 50.0


async def test_period_totals_and_deltas_vs_previous_period(world) -> None:
    async with world["sessions"]() as s:
        data = await svc(s).chats([(world["a"], "A"), (world["b"], "B")], 7, scope="all")
    cur, prev, change = (
        data["totals"]["current"],
        data["totals"]["previous"],
        data["totals"]["change"],
    )
    assert cur == {
        "posts": 1,
        "quizzes": 3,
        "answers": 4,
        "correct": 3,
        "participants": 3,
        "accuracy": 75.0,
    }
    assert prev == {
        "posts": 0,
        "quizzes": 1,
        "answers": 1,
        "correct": 1,
        "participants": 1,
        "accuracy": 100.0,
    }
    assert change["answers"] == 300 and change["participants"] == 200 and change["quizzes"] == 200
    assert change["posts"] is None  # nothing to compare with
    assert change["accuracy"] == -25.0  # percentage points


async def test_heatmap_weekly_compare_and_top_growth(world) -> None:
    async with world["sessions"]() as s:
        data = await svc(s).chats([(world["a"], "A"), (world["b"], "B")], 7, scope="all")
    cells = data["heatmap"]["cells"]
    assert sum(map(sum, cells)) == 4 and data["heatmap"]["max"] == 1
    assert cells[5][1] == 1 and cells[5][10] == 1  # Saturday 01:00 and 10:00 in Tashkent
    assert cells[4][20] == 1 and cells[0][23] == 1  # Friday 20:00 and Monday 23:00 in UTC
    assert [w["week"] for w in data["weekly"]] == ["2026-11-09", "2026-11-16"]
    assert data["weekly"][0]["answers"] == 0 and data["weekly"][1]["participants"] == 3
    assert [
        (c["title"], c["answers"], c["participants"], c["accuracy"]) for c in data["compare"]
    ] == [
        ("A", 2, 2, 50.0),
        ("B", 2, 2, 100.0),
    ]
    top = {row["name"]: row for row in data["top"]}
    assert list(top) == ["P1", "P3"]  # P2 has no correct answer
    assert top["P1"]["points"] == 20 and top["P1"]["series"] == [0, 0, 0, 0, 0, 10, 20]
    assert top["P3"]["series"] == [0, 10, 10, 10, 10, 10, 10]


async def test_single_chat_uses_that_chats_timezone(world) -> None:
    async with world["sessions"]() as s:
        data = await svc(s).chats([(world["b"], "B")], 30, scope="chat")
    assert data["timezone"] == "UTC" and len(data["series"]) == 30
    assert data["series"][-1]["date"] == "2026-11-21"
    by_day = {row["date"]: row["answers"] for row in data["series"]}
    assert by_day["2026-11-20"] == 1 and by_day["2026-11-21"] == 0 and by_day["2026-11-16"] == 1
    assert data["compare"] == []


async def test_member_weekly_points_and_accuracy(world) -> None:
    async with world["sessions"]() as s:
        data = await svc(s).member(world["users"][U1], [world["a"], world["b"]], 12)
    assert len(data["series"]) == 12 and data["series"][-1]["week"] == "2026-11-16"
    weeks = {row["week"]: row for row in data["series"]}
    assert weeks["2026-11-16"]["points"] == 20 and weeks["2026-11-16"]["accuracy"] == 100.0
    assert weeks["2026-11-09"]["points"] == 10
    assert weeks["2026-11-02"] == {
        "week": "2026-11-02",
        "answers": 0,
        "correct": 0,
        "points": 0,
        "accuracy": None,
    }
    assert data["totals"] == {"answers": 3, "correct": 3, "points": 30, "accuracy": 100.0}
    async with world["sessions"]() as s:
        wrong = await svc(s).member(world["users"][U2], [world["a"]], 12)
    assert wrong["totals"]["accuracy"] == 0.0


async def test_empty_scope_returns_zero_filled_payload(db) -> None:
    async with db() as s:
        data = await svc(s).chats([], 7, scope="all")
    assert len(data["series"]) == 7 and all(row["answers"] == 0 for row in data["series"])
    assert data["top"] == [] and data["heatmap"]["max"] == 0


def test_helpers() -> None:
    assert (
        pick_days("30") == 30
        and pick_days("31") == 7
        and pick_days("x") == 7
        and pick_days(None, 30) == 30
    )
    assert change_pct(150, 100) == 50 and change_pct(5, 0) is None and change_pct(None, 3) is None
    window = Window.ending(date(2026, 11, 21), 7)
    assert (window.start, window.prev_start, window.prev_end) == (
        date(2026, 11, 15),
        date(2026, 11, 8),
        date(2026, 11, 14),
    )


async def test_platform_revenue_subscriptions_churn_and_daily(db) -> None:
    """Global numbers: compare before/after inserting known rows (other data may exist)."""
    now = datetime.now(UTC)
    tashkent = now + timedelta(hours=5)
    this_month = tashkent.date().replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    # 1 hour after local midnight on the 1st = 20:00 UTC the day before: belongs to this month.
    border = datetime.combine(this_month, datetime.min.time()).replace(tzinfo=UTC) - timedelta(
        hours=4
    )
    async with db() as s:
        before = await platform_charts(s, days=7, founder_slots=20)
    async with db() as s:
        plan = (await s.execute(select(Plan).where(Plan.code == "pro"))).scalar_one()
        users = {
            tg: User(telegram_id=tg, full_name="Rev", language_code="uz") for tg in (U1, U2, U3)
        }
        users[U1].is_founder = True
        users[U1].founder_since = border
        s.add_all(users.values())
        await s.flush()
        s.add_all(
            [
                Payment(
                    owner_id=users[U1].id,
                    plan_id=plan.id,
                    amount_uzs=27_313,
                    status="approved",
                    reviewed_at=border,
                ),
                Payment(
                    owner_id=users[U2].id,
                    plan_id=plan.id,
                    amount_uzs=39_011,
                    status="approved",
                    reviewed_at=border
                    - timedelta(hours=2),  # 23:00 local on the last day of last month
                ),
                Payment(
                    owner_id=users[U3].id,
                    plan_id=plan.id,
                    amount_uzs=99_999,
                    status="rejected",
                    reviewed_at=border,
                ),
                # Paid this month, still active.
                Subscription(
                    owner_id=users[U1].id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.ACTIVE,
                    source=SubscriptionSource.MANUAL_PAYMENT,
                    started_at=border,
                    expires_at=now + timedelta(days=20),
                ),
                # A trial started and ended this month without converting: trial churn.
                Subscription(
                    owner_id=users[U3].id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.EXPIRED,
                    source=SubscriptionSource.TRIAL,
                    started_at=border,
                    expires_at=now - timedelta(minutes=5),
                ),
            ]
        )
        s.add(
            UsageDaily(owner_id=users[U1].id, metric="ai_generation", day=tashkent.date(), count=4)
        )
        await s.commit()
    async with db() as s:
        after = await platform_charts(s, days=7, founder_slots=20)
    cur, prev = after["months"][-1], after["months"][-2]
    cur0, prev0 = before["months"][-1], before["months"][-2]
    assert len(after["months"]) == 12 and cur["month"] == this_month.strftime("%Y-%m")
    assert prev["month"] == last_month.strftime("%Y-%m")
    assert (
        cur["revenue_uzs"] - cur0["revenue_uzs"] == 27_313
        and cur["payments"] - cur0["payments"] == 1
    )
    assert prev["revenue_uzs"] - prev0["revenue_uzs"] == 39_011
    assert cur["new_paid"] - cur0["new_paid"] == 1 and cur["new_trials"] - cur0["new_trials"] == 1
    assert cur["churn_trial"] - cur0["churn_trial"] == 1 and cur["churn_paid"] == cur0["churn_paid"]
    assert cur["active"].get("pro", 0) - cur0["active"].get("pro", 0) == 1
    assert cur["founders"] - cur0["founders"] == 1 and prev["founders"] == prev0["founders"]
    assert after["founder"]["used"] == cur["founders"]
    assert after["daily"][-1]["ai"] - before["daily"][-1]["ai"] == 4
    assert len(after["daily"]) == 7 and after["ai_daily_since"] is not None


async def test_usage_bump_also_writes_the_daily_row(db) -> None:
    from app.db.repositories.usage import UsageRepository

    async with db() as s:
        user = User(telegram_id=U1, full_name="AI", language_code="uz")
        s.add(user)
        await s.flush()
        repo = UsageRepository(s)
        assert await repo.bump(user.id, "ai_generation", "2026-11") == 1
        assert await repo.bump(user.id, "ai_generation", "2026-11") == 2
        await s.commit()
        rows = (
            (await s.execute(select(UsageDaily).where(UsageDaily.owner_id == user.id)))
            .scalars()
            .all()
        )
    assert len(rows) == 1 and rows[0].count == 2
