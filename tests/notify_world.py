"""Shared Postgres setup for tutor notice tests."""

import os
from datetime import datetime, timedelta

import pytest
from app.db.models.chats import Chat, ChatType
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.jobs import Job
from app.db.models.lessons import TutorLesson
from app.db.models.plans import Plan
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.tutor_notices import TutorNotice
from app.db.models.usage import UsageCounter, UsageDaily
from app.db.models.users import User
from app.db.models.widget_messages import WidgetMessage
from app.db.models.workspaces import Workspace
from app.db.repositories.jobs import JobRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.tutor_notices import TutorNoticeRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.jobs.tutor_notify import TutorNotifyHandler
from app.services.access import AccessService
from app.services.clock import TASHKENT
from app.services.notify import notify_for
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, STUDENT, BLOCKED = 9864500001, 9864500002, 9864500003
CHAT_TG = -100986450099
_IDS = (OWNER, STUDENT, BLOCKED)


def require_postgres() -> str:
    """Skip the test when Postgres is not the configured database."""
    if not _URL.startswith("postgresql"):
        pytest.skip("Postgres is required")
    return _URL


async def purge(session) -> None:
    """Remove rows this suite created."""
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    user_ids = list((await session.execute(ids)).scalars())
    targets = list(_IDS) + user_ids + [CHAT_TG]
    await session.execute(delete(WidgetMessage).where(WidgetMessage.telegram_id.in_(_IDS)))
    await session.execute(delete(TutorNotice).where(TutorNotice.target_id.in_(targets)))
    await session.execute(delete(Job).where(Job.type == "tutor_notify"))
    if user_ids:
        await session.execute(delete(UsageDaily).where(UsageDaily.owner_id.in_(user_ids)))
        await session.execute(delete(UsageCounter).where(UsageCounter.owner_id.in_(user_ids)))
    await session.execute(delete(Chat).where(Chat.telegram_chat_id == CHAT_TG))
    if user_ids:
        await session.execute(delete(Subscription).where(Subscription.owner_id.in_(user_ids)))
        await session.execute(delete(Chat).where(Chat.owner_id.in_(user_ids)))
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(ids)))
    await session.execute(
        delete(TutorGroupMember).where(
            TutorGroupMember.group_id.in_(select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids)))
        )
    )
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


async def world(
    session,
    now: datetime,
    *,
    name: str = "Ingliz tili",
    level: str | None = "B1",
    start: datetime | None = None,
    remind: int | None = 60,
    fee_days: int | None = 3,
    fee_in_group: bool = False,
    blocked: bool = False,
    plan: str | None = "start",
) -> dict:
    """One teacher, one group, one linked student, and one group chat."""
    user = User(telegram_id=OWNER, full_name="Lola", language_code="uz")
    session.add(user)
    await session.flush()
    space = Workspace(owner_id=user.id, vertical="tutor", name="Kabinet")
    session.add(space)
    await session.flush()
    chat = Chat(
        telegram_chat_id=CHAT_TG,
        type=ChatType.GROUP,
        title="Guruh",
        owner_id=user.id,
        added_at=now,
        is_active=True,
    )
    session.add(chat)
    await session.flush()
    group = TutorGroup(
        owner_id=user.id,
        workspace_id=space.id,
        name=name,
        level=level,
        weekdays="6",
        start_min=18 * 60,
        end_min=19 * 60 + 30,
        enroll_code=f"n{user.id}",
        chat_id=chat.id,
        remind_lesson_min=remind,
        remind_fee_days=fee_days,
        fee_in_group=fee_in_group,
    )
    session.add(group)
    await session.flush()
    pupil = _student(user.id, space.id, STUDENT, "Ali Valiyev", "n-ali")
    session.add(pupil)
    extra = None
    if blocked:
        extra = _student(user.id, space.id, BLOCKED, "Vali", "n-vali")
        session.add(extra)
    await session.flush()
    session.add(TutorGroupMember(group_id=group.id, student_id=pupil.id, status="active"))
    if extra is not None:
        session.add(TutorGroupMember(group_id=group.id, student_id=extra.id, status="active"))
    lesson = None
    if start is not None:
        lesson = TutorLesson(
            owner_id=user.id,
            workspace_id=space.id,
            group_id=group.id,
            title="Dars",
            status="scheduled",
            source="manual",
            starts_at=start,
            ends_at=start + timedelta(minutes=90),
        )
        session.add(lesson)
    if plan and plan != "free":
        chosen = (await session.execute(select(Plan).where(Plan.code == plan))).scalar_one()
        session.add(
            Subscription(
                owner_id=user.id,
                plan_id=chosen.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=now,
                expires_at=now.replace(year=now.year + 1),
            )
        )
    await session.flush()
    return {"user": user, "group": group, "chat": chat, "student": pupil, "lesson": lesson}


def service(session, now: datetime):
    """Planner and settings bound to a fixed clock."""
    return notify_for(session, now=lambda: now)


def handler(session, bot, now: datetime) -> TutorNotifyHandler:
    """The sender, with the real plan lookup."""
    usage = UsageRepository(session)
    return TutorNotifyHandler(
        bot,
        TutorNoticeRepository(session),
        UserRepository(session),
        usage,
        AccessService(
            PlanRepository(session),
            SubscriptionRepository(session),
            session_chats(session),
            usage,
            UserRepository(session),
            now=lambda: now,
        ),
        JobRepository(session),
        now=lambda: now,
        session=session,
    )


def session_chats(session):
    """Chat repository used by the plan lookup."""
    from app.db.repositories.chats import ChatRepository

    return ChatRepository(session)


def _student(
    owner_id: int, workspace_id: int, telegram_id: int, name: str, code: str
) -> TutorStudent:
    return TutorStudent(
        owner_id=owner_id,
        workspace_id=workspace_id,
        name=name,
        status="paid",
        amount_uzs=0,
        telegram_id=telegram_id,
        join_code=code,
    )


def local(moment: datetime) -> datetime:
    """The same moment on the Tashkent clock."""
    return moment.astimezone(TASHKENT)


async def open_db():
    url = require_postgres()
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await purge(session)
        await session.commit()
    try:
        yield factory
    finally:
        async with factory() as session:
            await purge(session)
            await session.commit()
        await engine.dispose()
