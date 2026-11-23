"""The evening-before reminder is once per student and stops when the quota is full."""

import os
from datetime import date, datetime

import pytest
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.jobs import Job
from app.db.models.plans import Plan
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.topics import TutorTopic
from app.db.models.tutor_notices import TutorNotice
from app.db.models.usage import UsageCounter
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.db.repositories.jobs import JobRepository
from app.db.repositories.tutor_notices import TutorNoticeRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.jobs.runner import JobCancel
from app.jobs.tutor_notify import TutorNotifyHandler
from app.services.access import AccessService
from app.services.clock import TASHKENT
from app.services.notify import notify_for
from app.services.notify_rules import METRIC, period_key
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, ACTIVE, PENDING = 9865400001, 9865400002, 9865400003
_IDS = (OWNER, ACTIVE, PENDING)
_DUE = date(2099, 1, 15)
_EVENING = datetime(2099, 1, 14, 18, 0, tzinfo=TASHKENT)
_AFTERNOON = datetime(2099, 1, 14, 17, 0, tzinfo=TASHKENT)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    user_ids = list((await session.execute(ids)).scalars())
    targets = list(_IDS) + user_ids
    await session.execute(delete(TutorNotice).where(TutorNotice.target_id.in_(targets)))
    for user_id in user_ids:
        await session.execute(
            delete(Job).where(
                Job.type == "tutor_notify", Job.payload.contains({"owner_id": user_id})
            )
        )
        await session.execute(delete(UsageCounter).where(UsageCounter.owner_id == user_id))
        await session.execute(delete(Subscription).where(Subscription.owner_id == user_id))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorTopic).where(TutorTopic.group_id.in_(groups)))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def db():
    engine = create_async_engine(_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _purge(session)
        await session.commit()
    try:
        yield factory
    finally:
        async with factory() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


class _Bot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_kwargs) -> None:
        self.sent.append((chat_id, text))


def _handler(session, bot, moment) -> TutorNotifyHandler:
    from app.db.repositories.chats import ChatRepository
    from app.db.repositories.plans import PlanRepository
    from app.db.repositories.subscriptions import SubscriptionRepository

    usage = UsageRepository(session)
    access = AccessService(
        PlanRepository(session),
        SubscriptionRepository(session),
        ChatRepository(session),
        usage,
        UserRepository(session),
        now=lambda: moment,
    )
    return TutorNotifyHandler(
        bot,
        TutorNoticeRepository(session),
        UserRepository(session),
        usage,
        access,
        JobRepository(session),
        now=lambda: moment,
    )


async def _world(session, plan: str) -> dict:
    user = User(telegram_id=OWNER, full_name="Lola", language_code="uz")
    session.add(user)
    await session.flush()
    space = Workspace(owner_id=user.id, vertical="tutor", name="Kabinet")
    session.add(space)
    await session.flush()
    group = TutorGroup(
        owner_id=user.id,
        workspace_id=space.id,
        name="Ingliz",
        weekdays="1",
        start_min=18 * 60,
        end_min=19 * 60,
        enroll_code=f"h{user.id}",
    )
    active = TutorStudent(
        owner_id=user.id,
        workspace_id=space.id,
        name="Ali",
        status="paid",
        amount_uzs=0,
        telegram_id=ACTIVE,
        join_code=f"ha{user.id}",
    )
    waiting = TutorStudent(
        owner_id=user.id,
        workspace_id=space.id,
        name="Vali",
        status="paid",
        amount_uzs=0,
        telegram_id=PENDING,
        join_code=f"hp{user.id}",
    )
    session.add_all([group, active, waiting])
    await session.flush()
    session.add(TutorGroupMember(group_id=group.id, student_id=active.id, status="active"))
    session.add(TutorGroupMember(group_id=group.id, student_id=waiting.id, status="pending"))
    topic = TutorTopic(
        group_id=group.id,
        title="Unit <1>",
        held_on=date(2099, 1, 10),
        homework="<b>read",
        homework_due=_DUE,
    )
    session.add(topic)
    if plan != "free":
        chosen = (await session.execute(select(Plan).where(Plan.code == plan))).scalar_one()
        session.add(
            Subscription(
                owner_id=user.id,
                plan_id=chosen.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=_EVENING,
                expires_at=_EVENING.replace(year=_EVENING.year + 1),
            )
        )
    await session.flush()
    return {"user": user, "group": group, "topic": topic}


async def _jobs(session, owner_id: int) -> list[Job]:
    rows = (await session.execute(select(Job).where(Job.type == "tutor_notify"))).scalars()
    return [
        row
        for row in rows
        if row.payload.get("owner_id") == owner_id and row.payload.get("kind") == "homework"
    ]


async def test_homework_reminder_is_once_and_stops_at_the_quota(db) -> None:
    async with db() as session:
        made = await _world(session, "start")
        sender = notify_for(session, now=lambda: _AFTERNOON)
        await sender.enqueue_due(_AFTERNOON)
        assert await _jobs(session, made["user"].id) == []
        await notify_for(session, now=lambda: _EVENING).enqueue_due(_EVENING)
        await notify_for(session, now=lambda: _EVENING).enqueue_due(_EVENING)
        rows = await _jobs(session, made["user"].id)
        assert len(rows) == 1
        assert rows[0].payload["telegram_id"] == ACTIVE
        bot = _Bot()
        await _handler(session, bot, _EVENING).handle(rows[0])
        assert bot.sent == [
            (ACTIVE, "Uy vazifasi: Unit &lt;1&gt;\n&lt;b&gt;read\nMuddat: 2099-01-15")
        ]
        counter = (
            await session.execute(
                select(UsageCounter).where(
                    UsageCounter.owner_id == made["user"].id,
                    UsageCounter.metric == METRIC,
                    UsageCounter.period_key == period_key(_EVENING),
                )
            )
        ).scalar_one()
        counter.count = 300
        extra = TutorTopic(
            group_id=made["group"].id,
            title="Unit 2",
            held_on=date(2099, 1, 11),
            homework="more",
            homework_due=_DUE,
        )
        session.add(extra)
        await session.flush()
        await notify_for(session, now=lambda: _EVENING).enqueue_due(_EVENING)
        second = next(
            row
            for row in await _jobs(session, made["user"].id)
            if row.payload["params"]["text"] == "more"
        )
        with pytest.raises(JobCancel):
            await _handler(session, bot, _EVENING).handle(second)
        assert len(bot.sent) == 1
        skipped = await session.get(TutorNotice, second.payload["notification_id"])
        assert skipped is not None and skipped.status == "skipped"


async def test_a_free_plan_does_not_send_the_homework_reminder(db) -> None:
    async with db() as session:
        made = await _world(session, "free")
        await notify_for(session, now=lambda: _EVENING).enqueue_due(_EVENING)
        rows = await _jobs(session, made["user"].id)
        assert len(rows) == 1
        bot = _Bot()
        with pytest.raises(JobCancel):
            await _handler(session, bot, _EVENING).handle(rows[0])
        assert bot.sent == []
