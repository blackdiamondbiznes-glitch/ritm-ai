"""Monthly tutor report numbers, and one private message per workspace on the 1st."""

import os
from datetime import UTC, date, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.jobs import Job
from app.db.models.lessons import TutorLesson
from app.db.models.plans import Plan
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.db.repositories.users import UserRepository
from app.jobs.runner import JobCancel
from app.jobs.tutor_report import TutorReportHandler, enqueue_reports
from app.services.access import AccessService
from app.services.clock import TASHKENT
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
PRO, FREE = 9865100001, 9865100002
_IDS = (PRO, FREE)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
_FIRST = datetime(2026, 12, 1, 9, 0, tzinfo=TASHKENT)
_EARLY = datetime(2026, 12, 1, 8, 59, tzinfo=TASHKENT)
_LATER = datetime(2026, 12, 2, 9, 0, tzinfo=TASHKENT)


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    user_ids = list((await session.execute(ids)).scalars())
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    invoices = select(TutorInvoice.id).where(TutorInvoice.group_id.in_(groups))
    lessons = select(TutorLesson.id).where(TutorLesson.owner_id.in_(ids))
    await session.execute(delete(TutorFeePayment).where(TutorFeePayment.invoice_id.in_(invoices)))
    await session.execute(delete(TutorInvoice).where(TutorInvoice.group_id.in_(groups)))
    await session.execute(delete(TutorAttendance).where(TutorAttendance.lesson_id.in_(lessons)))
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(ids)))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    for user_id in user_ids:
        await session.execute(
            delete(Job).where(
                Job.type == "tutor_report", Job.payload.contains({"owner_id": user_id})
            )
        )
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        session.add_all(
            [
                User(telegram_id=PRO, full_name="Lola", language_code="uz"),
                User(telegram_id=FREE, full_name="Free", language_code="uz"),
            ]
        )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        "pro": {"Authorization": f"Bearer {issue_session(PRO, secret, 600)}"},
        "free": {"Authorization": f"Bearer {issue_session(FREE, secret, 600)}"},
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


def _access(session, moment: datetime) -> AccessService:
    from app.db.repositories.chats import ChatRepository
    from app.db.repositories.plans import PlanRepository
    from app.db.repositories.subscriptions import SubscriptionRepository
    from app.db.repositories.usage import UsageRepository

    return AccessService(
        PlanRepository(session),
        SubscriptionRepository(session),
        ChatRepository(session),
        UsageRepository(session),
        UserRepository(session),
        now=lambda: moment,
    )


class _Bot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_kwargs) -> None:
        self.sent.append((chat_id, text))


async def _jobs(session, owner_id: int) -> list[Job]:
    rows = (await session.execute(select(Job).where(Job.type == "tutor_report"))).scalars()
    return [row for row in rows if row.payload.get("owner_id") == owner_id]


async def test_monthly_numbers_and_one_message_per_workspace(client) -> None:
    http, heads, sessions = client
    now = datetime.now(UTC)
    async with sessions() as session:
        owner = (await session.execute(select(User).where(User.telegram_id == PRO))).scalar_one()
        plan = (await session.execute(select(Plan).where(Plan.code == "pro"))).scalar_one()
        session.add(
            Subscription(
                owner_id=owner.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=now - timedelta(days=5),
                expires_at=now + timedelta(days=30),
            )
        )
        await session.commit()
    busy = await http.post(
        "/api/tutor/groups",
        headers=heads["pro"],
        json={"name": "Ingliz <b>", "weekdays": [1], "start": "18:00", "end": "19:00"},
    )
    empty = await http.post(
        "/api/tutor/groups",
        headers=heads["free"],
        json={"name": "Bosh", "weekdays": [2], "start": "09:00", "end": "10:00"},
    )
    # The free teacher needs a cabinet so the monthly scan can see the workspace.
    assert busy.status == 200 and empty.status == 200
    data_id = (await busy.json())["created_id"]
    async with sessions() as session:
        group = await session.get(TutorGroup, data_id)
        assert group is not None
        await _fill(session, group)
        await session.commit()
        owner_id = group.owner_id
    report = await http.get("/api/tutor/reports/monthly?month=2026-11", headers=heads["pro"])
    body = await report.json()
    assert report.status == 200 and body["month"] == "2026-11"
    assert body["new_students"] == 1 and body["left_students"] == 1
    found = {row["name"]: row for row in body["groups"]}
    assert found["Ingliz <b>"]["attendance_rate"] == 0.5
    assert found["Ingliz <b>"]["collected_uzs"] == 100_000
    assert found["Ingliz <b>"]["outstanding_uzs"] == 200_000
    refused = await http.get("/api/tutor/reports/monthly?month=2026-11", headers=heads["free"])
    assert refused.status == 403 and (await refused.json())["error"] == "export"
    bad = await http.get("/api/tutor/reports/monthly?month=2026-13", headers=heads["pro"])
    assert bad.status == 400 and (await bad.json())["error"] == "month"
    async with sessions() as session:
        access = _access(session, _FIRST)
        await enqueue_reports(session, access, now=_EARLY)
        await session.commit()
        assert await _jobs(session, owner_id) == []
        await enqueue_reports(session, access, now=_FIRST)
        await enqueue_reports(session, access, now=_FIRST)
        await enqueue_reports(session, access, now=_LATER)
        await session.commit()
        rows = await _jobs(session, owner_id)
        assert len(rows) == 1 and rows[0].payload["month"] == "2026-11"
        free = (await session.execute(select(User).where(User.telegram_id == FREE))).scalar_one()
        assert await _jobs(session, free.id) == []
        bot = _Bot()
        await TutorReportHandler(bot, access, UserRepository(session), session).handle(rows[0])
        assert bot.sent[0][0] == PRO
        text = bot.sent[0][1]
        assert "Ingliz &lt;b&gt;" in text and "50%" in text
        assert "100 000" in text and "200 000" in text and "Yangi: 1" in text
        sub = (
            await session.execute(select(Subscription).where(Subscription.owner_id == owner_id))
        ).scalar_one()
        sub.expires_at = _FIRST - timedelta(days=1)
        await session.commit()
        with pytest.raises(JobCancel):
            await TutorReportHandler(bot, access, UserRepository(session), session).handle(rows[0])
        assert len(bot.sent) == 1


async def _fill(session, group: TutorGroup) -> None:
    """November marks, one payment, one open invoice, one joiner and one leaver."""
    space = group.workspace_id
    joined = _student(group, space, "Ali", "paid", "r-ali")
    old = _student(group, space, "Vali", "paid", "r-vali")
    late = _student(group, space, "Sali", "paid", "r-sali")
    excused = _student(group, space, "Guli", "paid", "r-guli")
    left = _student(group, space, "Ketgan", "inactive", "r-left")
    left.updated_at = datetime(2026, 11, 8, 12, 0, tzinfo=TASHKENT)
    stayed = _student(group, space, "Eski", "inactive", "r-old")
    stayed.updated_at = datetime(2026, 10, 8, 12, 0, tzinfo=TASHKENT)
    session.add_all([joined, old, late, excused, left, stayed])
    await session.flush()
    november = datetime(2026, 11, 3, 10, 0, tzinfo=TASHKENT)
    october = datetime(2026, 10, 3, 10, 0, tzinfo=TASHKENT)
    session.add(
        TutorGroupMember(
            group_id=group.id, student_id=joined.id, status="active", created_at=november
        )
    )
    for pupil in (old, late, excused, left, stayed):
        session.add(
            TutorGroupMember(
                group_id=group.id, student_id=pupil.id, status="active", created_at=october
            )
        )
    lesson = TutorLesson(
        owner_id=group.owner_id,
        workspace_id=space,
        group_id=group.id,
        title="Dars",
        status="done",
        source="manual",
        starts_at=datetime(2026, 11, 10, 18, 0, tzinfo=TASHKENT),
    )
    outside = TutorLesson(
        owner_id=group.owner_id,
        workspace_id=space,
        group_id=group.id,
        title="Oktyabr",
        status="done",
        source="manual",
        starts_at=datetime(2026, 10, 10, 18, 0, tzinfo=TASHKENT),
    )
    session.add_all([lesson, outside])
    await session.flush()
    for pupil, status in (
        (joined, "present"),
        (old, "late"),
        (late, "absent"),
        (excused, "excused"),
    ):
        session.add(TutorAttendance(lesson_id=lesson.id, student_id=pupil.id, status=status))
    session.add(TutorAttendance(lesson_id=outside.id, student_id=joined.id, status="present"))
    bill = _invoice(
        group, joined.id, date(2026, 11, 1), date(2026, 11, 20), 300_000, 100_000, "due"
    )
    october_bill = _invoice(
        group, old.id, date(2026, 10, 1), date(2026, 10, 20), 50_000, 50_000, "paid"
    )
    session.add_all([bill, october_bill])
    await session.flush()
    session.add(_pay(bill.id, 100_000, date(2026, 11, 15)))
    session.add(_pay(october_bill.id, 50_000, date(2026, 10, 15)))


def _student(group, space, name, status, code) -> TutorStudent:
    return TutorStudent(
        owner_id=group.owner_id,
        workspace_id=space,
        name=name,
        status=status,
        amount_uzs=0,
        join_code=code,
    )


def _invoice(group, student_id, period, due, amount, paid, status) -> TutorInvoice:
    return TutorInvoice(
        workspace_id=group.workspace_id,
        group_id=group.id,
        student_id=student_id,
        kind="monthly",
        period_start=period,
        amount_uzs=amount,
        paid_uzs=paid,
        due_on=due,
        status=status,
    )


def _pay(invoice_id: int, amount: int, day: date) -> TutorFeePayment:
    return TutorFeePayment(invoice_id=invoice_id, amount_uzs=amount, paid_on=day, method="cash")
