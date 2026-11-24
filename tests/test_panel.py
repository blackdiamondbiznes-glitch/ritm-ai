"""Teacher web panel: magic links, cookie sessions with an Origin check, and the Bosh payload."""

import os
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from aiohttp import web
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
from playwright.async_api import async_playwright
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
    return {
        "teacher": teacher,
        "tonight": tonight.id,
        "missed": missed.id,
        "group": group.id,
        "space": space.id,
        "dilnoza": dilnoza.id,
    }


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


async def _fresh(env) -> str:
    async with env["sessions"]() as session:
        raw = await panel_login.issue(session, env["teacher"].id)
        await session.commit()
    return raw


async def _post_login(env, raw, headers):
    return await env["http"].post(
        "/panel/login", data={"t": raw}, headers=headers, allow_redirects=False
    )


async def test_login_page_lets_the_browser_send_its_origin(env) -> None:
    page = await env["http"].get("/panel/login?t=abc")
    assert page.headers["Referrer-Policy"] == "same-origin"
    assert "no-referrer" not in await page.text()
    assert (await env["http"].get("/panel")).headers["Referrer-Policy"] == "same-origin"


@pytest.mark.parametrize(
    "headers",
    [
        {"Referer": "{origin}/panel/login?t=x"},
        {"Origin": "null", "Sec-Fetch-Site": "same-origin"},
        {"Origin": "null", "Referer": "{origin}/panel/login"},
    ],
)
async def test_login_accepts_null_or_missing_origin_from_our_own_page(env, headers) -> None:
    sent = {k: v.format(origin=env["origin"]) for k, v in headers.items()}
    res = await _post_login(env, await _fresh(env), sent)
    assert res.status == 303 and "ritm_panel=" in res.headers["Set-Cookie"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "null"},
        {"Origin": "https://evil.example"},
        {"Origin": "null", "Referer": "https://evil.example/x"},
        {"Origin": "null", "Sec-Fetch-Site": "cross-site", "Referer": "{origin}/panel"},
    ],
)
async def test_refused_login_is_friendly_and_keeps_the_token(env, headers) -> None:
    raw = await _fresh(env)
    sent = {k: v.format(origin=env["origin"]) for k, v in headers.items()}
    refused = await _post_login(env, raw, sent)
    assert refused.status == 403
    assert refused.content_type == "text/html"
    body = await refused.text()
    assert 'method="post"' in body and '"error"' not in body
    retry = await _post_login(env, raw, {"Origin": env["origin"]})
    assert retry.status == 303


async def test_https_origin_behind_the_proxy_matches(env) -> None:
    """TLS ends at Render: the app sees http while the browser says https."""
    host = env["origin"].split("://", 1)[1]
    headers = {"Origin": f"https://{host.upper()}", "X-Forwarded-Proto": "https"}
    assert (await _post_login(env, await _fresh(env), headers)).status == 303


def test_public_url_compare_ignores_scheme_case_slash_and_default_port() -> None:
    from aiohttp.test_utils import make_mocked_request
    from app.webapp.routes import same_origin

    app = web.Application()
    app["settings"] = Settings(
        bot_token="1:t", database_url=_URL, webapp_url="https://Ritm-AI.onrender.com/"
    )

    def check(headers: dict) -> bool:
        req = make_mocked_request(
            "POST", "/panel/login", headers={"Host": "10.0.0.5:10000", **headers}, app=app
        )
        return same_origin(req)

    assert check({"Origin": "https://ritm-ai.onrender.com"})
    assert check({"Origin": "https://ritm-ai.onrender.com:443"})
    assert check({"Origin": "http://RITM-AI.onrender.com"})
    assert check({"Origin": "null", "Referer": "https://ritm-ai.onrender.com/panel"})
    assert not check({"Origin": "https://ritm-ai.onrender.com.evil.example"})
    assert not check({"Origin": "null"})
    assert not check({"Origin": "garbage:::"})


async def test_cookie_writes_use_the_same_fallback(env) -> None:
    http, cookie = env["http"], env["cookie"]
    body = {"name": "Adham ustoz"}
    same = {**cookie, "Origin": "null", "Sec-Fetch-Site": "same-origin"}
    assert (await http.post("/api/tutor/name", json=body, headers=same)).status == 200
    cross = {**cookie, "Sec-Fetch-Site": "cross-site", "Referer": env["origin"] + "/panel"}
    assert (await http.post("/api/tutor/name", json=body, headers=cross)).status == 403
    referer = {**cookie, "Referer": env["origin"] + "/panel"}
    assert (await http.post("/api/tutor/name", json=body, headers=referer)).status == 200


STATIC = Path(__file__).resolve().parents[1] / "app" / "webapp" / "static"
PAGES = (
    "panel.js",
    "panel_kit.js",
    "panel_schedule.js",
    "panel_people.js",
    "panel_money.js",
    "panel_settings.js",
)
ROUTES = ("home", "schedule", "groups", "students", "attendance", "fees", "reports", "settings")


def _pack_keys(lang: str) -> set[str]:
    keys: set[str] = set()
    for path in STATIC.glob(f"i18n_*_{lang}.js"):
        keys |= set(re.findall(r"^  (\w+):", path.read_text(encoding="utf-8"), re.M))
    return keys


def test_every_panel_string_exists_in_all_three_languages() -> None:
    used: set[str] = set()
    for name in PAGES:
        used |= set(re.findall(r'\bt\("(\w+)"', (STATIC / name).read_text(encoding="utf-8")))
    assert len(used) > 100
    for lang in ("uz", "ru", "en"):
        assert not used - _pack_keys(lang), lang


def test_every_sidebar_section_is_a_native_page() -> None:
    shell = (STATIC / "panel.js").read_text(encoding="utf-8")
    html = (STATIC / "panel.html").read_text(encoding="utf-8")
    for route in ROUTES:
        assert f'href="#/{route}"' in html
        if route != "home":
            assert re.search(rf"^  {route}: ", shell, re.M), route
    joined = "".join((STATIC / name).read_text(encoding="utf-8") for name in PAGES)
    assert "<iframe" not in joined and "embed=1" not in joined
    assert "pnlFrameLead" not in joined
    # The panel CSP has no 'unsafe-inline': no inline style attributes or handlers.
    assert 'style="' not in joined and not re.search(r"\son[a-z]+=\"", joined)
    for name in PAGES[1:]:
        assert f'<link rel="modulepreload" href="/s/{name}">' in html


async def test_panel_modules_are_served_versioned(env) -> None:
    http = env["http"]
    page = await (await http.get("/panel")).text()
    paths = re.findall(r'href="(/s/[0-9a-f]+/panel_\w+\.js)"', page)
    assert len(paths) == 5
    for path in paths:
        res = await http.get(path)
        assert res.status == 200 and "javascript" in res.headers["Content-Type"]


async def test_home_carries_the_bot_and_a_two_week_unmarked_window(env) -> None:
    async with env["sessions"]() as session:
        teacher = await session.get(User, env["teacher"].id)
        group = await session.get(TutorGroup, env["group"])
        space = await session.get(Workspace, env["space"])
        old = _lesson(teacher, space, group, datetime.now(UTC) - timedelta(days=10), None)
        ancient = _lesson(teacher, space, group, datetime.now(UTC) - timedelta(days=20), None)
        session.add_all([old, ancient])
        await session.commit()
        old_id, ancient_id = old.id, ancient.id
    data = await (await env["http"].get("/api/panel/home", headers=env["cookie"])).json()
    assert "bot_username" in data
    ids = {item["id"] for item in data["unmarked"]["items"]}
    assert {env["missed"], old_id} <= ids and ancient_id not in ids
    assert data["unmarked"]["count"] == 2


async def test_marking_from_the_panel_clears_the_unmarked_lesson(env) -> None:
    http, headers = env["http"], {**env["cookie"], "Origin": env["origin"]}
    sheet = await (
        await http.get(f"/api/tutor/sessions/{env['missed']}/attendance", headers=headers)
    ).json()
    marks = [{"student_id": row["student_id"], "status": "present"} for row in sheet["students"]]
    saved = await http.put(
        f"/api/tutor/sessions/{env['missed']}/attendance", json={"marks": marks}, headers=headers
    )
    assert saved.status == 200
    data = await (await http.get("/api/panel/home", headers=env["cookie"])).json()
    assert env["missed"] not in {item["id"] for item in data["unmarked"]["items"]}


async def test_panel_writes_go_through_the_shared_tutor_api(env) -> None:
    """Payments and group edits from the panel use the cookie plus a same-origin check."""
    http, headers = env["http"], {**env["cookie"], "Origin": env["origin"]}
    invoices = await (await http.get("/api/tutor/invoices", headers=headers)).json()
    target = invoices[0]["id"]
    body = {"amount_uzs": 50_000, "paid_on": date.today().isoformat(), "method": "cash"}
    blocked = await http.post(
        f"/api/tutor/invoices/{target}/payments", json=body, headers=env["cookie"]
    )
    assert blocked.status == 403
    paid = await http.post(f"/api/tutor/invoices/{target}/payments", json=body, headers=headers)
    assert paid.status in (200, 403)
    if paid.status == 403:
        assert (await paid.json())["error"] == "limit_fees"
    notify = {"remind_lesson_min": 30, "remind_fee_days": 1, "fee_in_group": False}
    res = await http.put(f"/api/tutor/groups/{env['group']}/notify", json=notify, headers=headers)
    assert res.status == 200
    week = date.today().isoformat()
    sessions = await http.get(f"/api/tutor/sessions?from={week}&to={week}", headers=headers)
    assert sessions.status == 200


def test_panel_phone_layout_and_fee_contract():
    """Phone header wraps instead of truncating; the fee form stays inside the API limits."""
    static = Path(__file__).resolve().parents[1] / "app" / "webapp" / "static"
    css = (static / "panel.css").read_text(encoding="utf-8")
    assert "text-overflow: ellipsis" not in css.split(".pn-lead {", 2)[-1].split("}", 1)[0]
    assert '"actions actions actions"' in css
    people = (static / "panel_people.js").read_text(encoding="utf-8")
    assert 'name="due_days"' not in people  # built through input(), limits below
    assert 'max="31"' in people and 'max="60"' not in people
    assert "pdNoFeeRule" in people and "pdCardDebts" in people
    money = (static / "panel_money.js").read_text(encoding="utf-8")
    assert "pdCardDebt" in money and "pdTotalDebt" in money


async def test_panel_browser_layout_and_keyboard_navigation(env) -> None:
    """Haqiqiy panel planshet va kompyuterda ochilib, klaviaturadan boshqariladi."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or None
        )
        context = await browser.new_context(viewport={"width": 1024, "height": 900})
        token = env["cookie"]["Cookie"].split("=", 1)[1]
        await context.add_cookies(
            [
                {
                    "name": "ritm_panel",
                    "value": token,
                    "url": env["origin"],
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        page = await context.new_page()
        try:
            await page.goto(f"{env['origin']}/panel")
            await page.locator("#pn-main h1").wait_for()

            for width in (768, 1024, 1280):
                await page.set_viewport_size({"width": width, "height": 900})
                metrics = await page.evaluate(
                    """() => ({
                        viewport: document.documentElement.clientWidth,
                        content: document.documentElement.scrollWidth,
                        main: document.querySelector("#pn-main").getBoundingClientRect().width
                    })"""
                )
                assert metrics["viewport"] == width
                assert metrics["content"] <= width
                assert metrics["main"] > 0

            await page.locator(".pn-skip").focus()
            await page.keyboard.press("Tab")
            assert await page.evaluate(
                "document.activeElement.getAttribute('data-route') === 'home'"
            )
            await page.keyboard.press("Tab")
            assert await page.evaluate(
                "document.activeElement.getAttribute('data-route') === 'schedule'"
            )
            await page.keyboard.press("Enter")
            await page.wait_for_function("location.hash === '#/schedule'")
            await page.locator("#pn-main h1").wait_for()
        finally:
            await context.close()
            await browser.close()
