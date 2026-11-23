"""CSV export: BOM, quoting, owner scope, and the Pro gate."""

import csv
import io
import os
from datetime import UTC, date, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.plans import Plan
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.services.clock import TASHKENT
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
PRO, OTHER, START, FREE = 9865200001, 9865200002, 9865200003, 9865200004
_IDS = (PRO, OTHER, START, FREE)
_NAME = 'Ali, "B"\nC'
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
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
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


def _body(name: str) -> dict:
    return {"name": name, "weekdays": [1], "start": "18:00", "end": "19:00"}


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sessions() as session:
        await _purge(session)
        session.add_all(
            [
                User(telegram_id=PRO, full_name="Pro", language_code="uz"),
                User(telegram_id=OTHER, full_name="Other", language_code="uz"),
                User(telegram_id=START, full_name="Start", language_code="uz"),
                User(telegram_id=FREE, full_name="Free", language_code="uz"),
            ]
        )
        await session.flush()
        plans = {
            row.code: row
            for row in (
                await session.execute(select(Plan).where(Plan.code.in_(("pro", "start"))))
            ).scalars()
        }
        for telegram, code in ((PRO, "pro"), (START, "start")):
            owner = (
                await session.execute(select(User).where(User.telegram_id == telegram))
            ).scalar_one()
            session.add(
                Subscription(
                    owner_id=owner.id,
                    plan_id=plans[code].id,
                    status=SubscriptionStatus.ACTIVE,
                    source=SubscriptionSource.ADMIN_GRANT,
                    started_at=now - timedelta(days=1),
                    expires_at=now + timedelta(days=30),
                )
            )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        name: {"Authorization": f"Bearer {issue_session(telegram, secret, 600)}"}
        for name, telegram in (("pro", PRO), ("other", OTHER), ("start", START), ("free", FREE))
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


def _rows(body: bytes) -> list[list[str]]:
    assert body.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))


async def test_csv_quotes_text_and_stays_on_the_owners_plan(client) -> None:
    http, heads, sessions = client
    today = datetime.now(TASHKENT).date().isoformat()
    made = await http.post("/api/tutor/groups", headers=heads["pro"], json=_body('A, "B"'))
    assert made.status == 200
    group_id = (await made.json())["created_id"]
    other = await http.post("/api/tutor/groups", headers=heads["other"], json=_body("Begona"))
    other_id = (await other.json())["created_id"]
    start = await http.post("/api/tutor/groups", headers=heads["start"], json=_body("Start"))
    start_id = (await start.json())["created_id"]
    free = await http.post("/api/tutor/groups", headers=heads["free"], json=_body("Free"))
    free_id = (await free.json())["created_id"]
    async with sessions() as session:
        group = await session.get(TutorGroup, group_id)
        assert group is not None
        card = TutorStudent(
            owner_id=group.owner_id,
            workspace_id=group.workspace_id,
            name=_NAME,
            phone="+998,1",
            status="paid",
            amount_uzs=0,
            join_code="csv5201",
        )
        hidden = TutorStudent(
            owner_id=group.owner_id,
            workspace_id=group.workspace_id,
            name="Kutilmoqda",
            status="pending",
            amount_uzs=0,
            join_code="csv5202",
        )
        session.add_all([card, hidden])
        await session.flush()
        session.add(TutorGroupMember(group_id=group.id, student_id=card.id, status="active"))
        lesson = TutorLesson(
            owner_id=group.owner_id,
            workspace_id=group.workspace_id,
            group_id=group.id,
            title="Dars",
            status="done",
            source="manual",
            starts_at=datetime(2026, 11, 10, 18, 0, tzinfo=TASHKENT),
        )
        session.add(lesson)
        await session.flush()
        session.add(TutorAttendance(lesson_id=lesson.id, student_id=card.id, status="present"))
        bill = TutorInvoice(
            workspace_id=group.workspace_id,
            group_id=group.id,
            student_id=card.id,
            kind="monthly",
            period_start=date(2026, 11, 1),
            amount_uzs=150_000,
            paid_uzs=150_000,
            due_on=date(2026, 11, 20),
            status="paid",
        )
        session.add(bill)
        await session.flush()
        session.add(
            TutorFeePayment(
                invoice_id=bill.id, amount_uzs=150_000, paid_on=date(2026, 11, 2), method="cash"
            )
        )
        await session.commit()
    students = await http.get("/api/tutor/export/students.csv", headers=heads["pro"])
    assert (
        students.status == 200
        and f"students-{today}.csv" in students.headers["Content-Disposition"]
    )
    table = _rows(await students.read())
    assert table[0] == ["name", "phone", "status", "groups"]
    assert [_NAME, "+998,1", "paid", 'A, "B"'] in table
    assert all(row[0] != "Kutilmoqda" for row in table)
    assert all(row[0] != "Begona" for row in table)
    payments = await http.get("/api/tutor/export/payments.csv?month=2026-11", headers=heads["pro"])
    paid = _rows(await payments.read())
    assert paid[0] == ["paid_on", "group", "student", "amount_uzs", "method"]
    assert ["2026-11-02", 'A, "B"', _NAME, "150000", "cash"] in paid
    missed = await http.get("/api/tutor/export/payments.csv?month=2026-10", headers=heads["pro"])
    assert _rows(await missed.read()) == [["paid_on", "group", "student", "amount_uzs", "method"]]
    marks = await http.get(
        f"/api/tutor/export/attendance.csv?group_id={group_id}&month=2026-11",
        headers=heads["pro"],
    )
    rolled = _rows(await marks.read())
    assert rolled[0] == ["student", "starts_at", "status"]
    assert [_NAME, "2026-11-10 18:00", "present"] in rolled
    foreign = await http.get(
        f"/api/tutor/export/attendance.csv?group_id={other_id}&month=2026-11",
        headers=heads["free"],
    )
    assert foreign.status == 404 and (await foreign.json())["error"] == "missing"
    own = await http.get(
        f"/api/tutor/export/attendance.csv?group_id={free_id}&month=2026-11",
        headers=heads["free"],
    )
    assert own.status == 403 and (await own.json())["error"] == "export"
    low = await http.get("/api/tutor/export/students.csv", headers=heads["start"])
    assert low.status == 403 and (await low.json())["error"] == "export"
    assert start_id
