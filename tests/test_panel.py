"""Teacher web panel: magic links, cookie sessions with an Origin check, and the Bosh payload."""

import os
from datetime import UTC, date, datetime, time, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.panel_tokens import PanelLoginToken
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.services import panel_login
from app.services.clock import TASHKENT
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
TEACH, PUPIL, ASKER = 9893500001, 9893500002, 9893500003
_IDS = (TEACH, PUPIL, ASKER)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    owners = select(User.id).where(User.telegram_id.in_(_IDS))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(owners))
    lessons = select(TutorLesson.id).where(TutorLesson.owner_id.in_(owners))
    invoices = select(TutorInvoice.id).where(TutorInvoice.group_id.in_(groups))
    await session.execute(delete(TutorFeePayment).where(TutorFeePayment.invoice_id.in_(invoices)))
    await session.execute(delete(TutorInvoice).where(TutorInvoice.group_id.in_(groups)))
    await session.execute(delete(TutorAttendance).where(TutorAttendance.lesson_id.in_(lessons)))
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(owners)))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(owners)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(owners)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(owners)))
    await session.execute(delete(PanelLoginToken).where(PanelLoginToken.user_id.in_(owners)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


async def _seed(session) -> dict:
    teacher = User(telegram_id=TEACH, full_name="Adham Hoshimov", language_code="uz")
    pupil = User(telegram_id=PUPIL, full_name="Dilnoza", language_code="uz")
    session.add_all([teacher, pupil])
    await session.flush()
    space = Workspace(owner_id=teacher.id, vertical="tutor", name="Kabinet")
    session.add(space)
    await session.flush()
    group = TutorGroup(
        owner_id=teacher.id,
        workspace_id=space.id,
        name="Ingliz tili",
        level="B1",
        weekdays="1,3,5",
        start_min=18 * 60,
        end_min=19 * 60 + 30,
        enroll_code="pnl35code",
        fee_mode="monthly",
        fee_uzs=400_000,
        billing_day=1,
    )
    session.add(group)
    await session.flush()
    dilnoza = TutorStudent(
        owner_id=teacher.id,
        workspace_id=space.id,
        name="Dilnoza",
        status="paid",
        amount_uzs=0,
        telegram_id=PUPIL,
        join_code="pnl-dil",
    )
    asker = TutorStudent(
        owner_id=teacher.id,
        workspace_id=space.id,
        name="Sardor Aliyev",
        status="pending",
        amount_uzs=0,
        telegram_id=ASKER,
        join_code="pnl-sar",
    )
    session.add_all([dilnoza, asker])
    await session.flush()
    session.add_all(
        [
            TutorGroupMember(group_id=group.id, student_id=dilnoza.id, status="active"),
            TutorGroupMember(group_id=group.id, student_id=asker.id, status="pending"),
        ]
    )
    now = datetime.now(UTC)
    today = now.astimezone(TASHKENT).date()
    late = datetime.combine(today, time(23, 30), tzinfo=TASHKENT)
    tonight = _lesson(teacher, space, group, late, "https://meet.google.com/abc-defg-hij")
    missed = _lesson(teacher, space, group, now - timedelta(hours=3), None)
    marked = _lesson(teacher, space, group, now - timedelta(days=2), None)
    session.add_all([tonight, missed, marked])
    await session.flush()
    session.add(TutorAttendance(lesson_id=marked.id, student_id=dilnoza.id, status="present"))
    overdue = TutorInvoice(
        workspace_id=space.id,
        group_id=group.id,
        student_id=dilnoza.id,
        kind="monthly",
        period_start=date(2020, 1, 1),
        amount_uzs=400_000,
        paid_uzs=100_000,
        due_on=today - timedelta(days=3),
        status="due",
    )
    session.add(overdue)
    await session.flush()
    session.add(
        TutorFeePayment(invoice_id=overdue.id, amount_uzs=100_000, paid_on=today, method="cash")
    )
    await session.commit()
    return {"teacher": teacher, "tonight": tonight.id, "missed": missed.id}


def _lesson(teacher, space, group, start, url) -> TutorLesson:
    return TutorLesson(
        owner_id=teacher.id,
        workspace_id=space.id,
        group_id=group.id,
        title="Dars",
        status="scheduled",
        source="manual",
        starts_at=start.astimezone(UTC),
        ends_at=(start + timedelta(minutes=90)).astimezone(UTC),
        meeting_url=url,
    )


@pytest.fixture
async def env():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        await session.commit()
        seeded = await _seed(session)
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    try:
        async with TestClient(TestServer(app)) as http:
            origin = str(http.make_url("/")).rstrip("/")
            yield {
                "http": http,
                "sessions": sessions,
                "origin": origin,
                "cookie": {"Cookie": f"ritm_panel={issue_session(TEACH, secret, 600)}"},
                "bearer": {"Authorization": f"Bearer {issue_session(TEACH, secret, 600)}"},
                "pupil": {"Authorization": f"Bearer {issue_session(PUPIL, secret, 600)}"},
                **seeded,
            }
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


async def test_magic_link_is_hashed_single_use_and_expires(env) -> None:
    start = datetime.now(UTC)
    async with env["sessions"]() as session:
        raw = await panel_login.issue(session, env["teacher"].id, now=start)
        stale = await panel_login.issue(
            session, env["teacher"].id, now=start - timedelta(minutes=16)
        )
        stored = (await session.execute(select(PanelLoginToken.token_hash))).scalars().all()
        assert raw not in stored and panel_login.token_hash(raw) in stored
        assert await panel_login.consume(session, stale, now=start) is None
        assert (
            await panel_login.consume(session, raw, now=start + timedelta(minutes=1))
            == env["teacher"].id
        )
        assert await panel_login.consume(session, raw, now=start + timedelta(minutes=2)) is None
        assert await panel_login.consume(session, "nope", now=start) is None
        await session.commit()


async def test_login_page_does_not_spend_and_post_sets_a_strict_cookie(env) -> None:
    http, origin = env["http"], env["origin"]
    async with env["sessions"]() as session:
        raw = await panel_login.issue(session, env["teacher"].id)
        await session.commit()
    page = await http.get(f"/panel/login?t={raw}")
    assert page.status == 200
    assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
    assert 'method="post"' in await page.text()
    refused = await http.post("/panel/login", data={"t": raw}, allow_redirects=False)
    assert refused.status == 403
    done = await http.post(
        "/panel/login", data={"t": raw}, headers={"Origin": origin}, allow_redirects=False
    )
    assert done.status == 303 and done.headers["Location"] == "/panel"
    cookie = done.headers["Set-Cookie"].lower()
    assert "ritm_panel=" in cookie and "httponly" in cookie and "secure" in cookie
    assert "samesite=lax" in cookie and "max-age=43200" in cookie
    again = await http.post(
        "/panel/login", data={"t": raw}, headers={"Origin": origin}, allow_redirects=False
    )
    assert again.status == 410


async def test_panel_page_is_never_framed(env) -> None:
    res = await env["http"].get("/panel")
    assert res.status == 200
    csp = res.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp and "script-src 'self';" in csp
    assert "unsafe-inline" not in csp
    assert "<script>" not in await res.text()
    mini = (await env["http"].get("/")).headers["Content-Security-Policy"]
    assert "frame-ancestors 'self' https://web.telegram.org" in mini


async def test_cookie_reads_tutor_api_and_writes_need_same_origin(env) -> None:
    http, cookie, origin = env["http"], env["cookie"], env["origin"]
    assert (await http.get("/api/tutor/summary", headers=cookie)).status == 200
    assert (await http.get("/api/tutor/summary")).status == 401
    body = {"name": "Adham ustoz"}
    assert (await http.post("/api/tutor/name", json=body, headers=cookie)).status == 403
    evil = {**cookie, "Origin": "https://evil.example"}
    assert (await http.post("/api/tutor/name", json=body, headers=evil)).status == 403
    ok = await http.post("/api/tutor/name", json=body, headers={**cookie, "Origin": origin})
    assert ok.status == 200
    assert (await http.post("/api/tutor/name", json=body, headers=env["bearer"])).status == 200


async def test_cookie_bootstrap_gives_the_framed_cabinet_a_token(env) -> None:
    http = env["http"]
    denied = await http.post("/api/bootstrap", json={"initData": ""}, headers=env["cookie"])
    assert denied.status == 403
    res = await http.post(
        "/api/bootstrap", json={"initData": ""}, headers={**env["cookie"], "Origin": env["origin"]}
    )
    assert res.status == 200
    assert (await res.json())["token"]


async def test_home_lists_only_exceptions(env) -> None:
    res = await env["http"].get("/api/panel/home", headers=env["cookie"])
    assert res.status == 200
    data = await res.json()
    assert data["teacher"] is True and data["both_roles"] is False
    tonight = next(row for row in data["lessons"] if row["id"] == env["tonight"])
    assert tonight["title"] == "Ingliz tili" and tonight["level"] == "B1"
    assert tonight["students"] == 1 and tonight["marked"] is False
    assert tonight["meeting_url"].startswith("https://meet.google.com/")
    assert data["unmarked"]["count"] == 1
    assert data["unmarked"]["items"][0]["id"] == env["missed"]
    assert data["overdue"] == {"count": 1, "sum_uzs": 300_000}
    assert data["requests"]["count"] == 1
    assert data["requests"]["first"]["student"] == "Sardor Aliyev"
    assert data["income"]["sum_uzs"] == 100_000 and data["income"]["payments"] == 1
    assert data["homework"] is None


async def test_link_button_is_for_teachers_and_needs_the_bot(env) -> None:
    http = env["http"]
    assert (await http.post("/api/panel/link", headers=env["pupil"])).status == 403
    assert (await http.post("/api/panel/link", headers=env["bearer"])).status == 503
