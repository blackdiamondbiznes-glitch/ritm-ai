"""M3 super-admin API on real Postgres: permission matrix, shared payment decisions,
receipt proxy, audit, grants. Only SUPER_ADMIN_IDS may use /api/admin/*."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.audit import AuditLog
from app.db.models.chats import Chat, ChatType
from app.db.models.payments import Payment, PaymentEvent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatRepository
from app.db.repositories.payments import PaymentEventRepository, PaymentRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.access import AccessService
from app.services.payments import PaymentService, Receipt
from app.services.workspaces import WorkspaceService
from app.webapp.admins import ChatAdminCache
from app.webapp.auth import issue_session, session_secret
from app.webapp.members import MemberCountCache
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.pg import allow_purge

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
SUPER, OWNER, OTHER, STRANGER = 9700000001, 9700000002, 9700000003, 9700000004
_IDS = (SUPER, OWNER, OTHER, STRANGER)
CHAT = -9700000001
TERMS = "2026-11-v1"

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(s) -> None:
    await allow_purge(s)
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    pays = select(Payment.id).where(Payment.owner_id.in_(ids))
    await s.execute(delete(PaymentEvent).where(PaymentEvent.payment_id.in_(pays)))
    await s.execute(delete(AuditLog).where(AuditLog.actor_user_id.in_(ids)))
    await s.execute(delete(Payment).where(Payment.owner_id.in_(ids)))
    await s.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await s.execute(delete(Chat).where(or_(Chat.telegram_chat_id == CHAT, Chat.owner_id.in_(ids))))
    await s.execute(delete(User).where(User.telegram_id.in_(_IDS)))


class _Bot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **_kw):
        self.sent.append((chat_id, text, reply_markup))

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **_kw):
        self.sent.append((chat_id, caption or "", reply_markup))


def _service(s) -> PaymentService:
    plans, subs, users = PlanRepository(s), SubscriptionRepository(s), UserRepository(s)
    access = AccessService(
        plans, subs, ChatRepository(s), UsageRepository(s), users, founder_slots=20
    )
    return PaymentService(
        PaymentRepository(s),
        plans,
        subs,
        users,
        access,
        AuditRepository(s),
        events=PaymentEventRepository(s),
        terms_version=TERMS,
    )


async def _submitted(sessions, tg: int, uniq: str) -> int:
    async with sessions() as s:
        owner = await UserRepository(s).get_by_telegram_id(tg)
        svc = _service(s)
        draft = await svc.start(owner, "pro", 1, terms_version=TERMS)
        done = await svc.submit(
            owner,
            draft.id,
            receipt=Receipt(f"file-{uniq}", uniq),
            card_last4="9876",
            transfer_at=datetime.now(UTC) - timedelta(minutes=3),
        )
        await s.commit()
        return done.payment.id


@pytest.fixture
async def world():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        await _purge(s)
        users = {
            tg: User(telegram_id=tg, full_name=f"Ega {tg % 10}", language_code="uz") for tg in _IDS
        }
        s.add_all(users.values())
        await s.flush()
        chat = Chat(
            telegram_chat_id=CHAT,
            type=ChatType.GROUP,
            title="Trust chat",
            owner_id=users[OWNER].id,
            added_at=datetime.now(UTC),
        )
        s.add(chat)
        await s.commit()
        ids = {tg: users[tg].id for tg in _IDS}
        ids["chat"] = chat.id
    pay_id = await _submitted(sessions, OWNER, "rcpt-1")
    bot = _Bot()
    settings = Settings(bot_token="1:test-token", database_url=_URL, super_admin_ids=str(SUPER))

    async def no_count(_chat_id: int) -> int:
        raise OSError("offline")

    async def no_admins(_chat_id: int):
        return []

    fetched: list[str] = []

    async def receipt_fetch(file_id: str, kind):
        fetched.append(file_id)
        return b"\xff\xd8\xffJPEGDATA", "image/jpeg"

    app = create_app(
        settings,
        sessions,
        limiter=RateLimiter(limit=10000),
        bot=bot,
        members=MemberCountCache(fetch=no_count),
        admins=ChatAdminCache(fetch=no_admins),
    )
    app["receipt_fetch"] = receipt_fetch
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        name: {"Authorization": f"Bearer {issue_session(tg, secret, 600)}"}
        for name, tg in (
            ("super", SUPER),
            ("owner", OWNER),
            ("other", OTHER),
            ("stranger", STRANGER),
        )
    }
    try:
        async with TestClient(TestServer(app)) as client:
            yield {
                "client": client,
                "heads": heads,
                "ids": ids,
                "pay": pay_id,
                "bot": bot,
                "sessions": sessions,
                "fetched": fetched,
            }
    finally:
        async with sessions() as s:
            await _purge(s)
            await s.commit()
        await engine.dispose()


def _endpoints(w) -> list[tuple[str, str, dict | None, int]]:
    """(method, path, body, status expected for the super admin)."""
    owner = w["ids"][OWNER]
    pay = w["pay"]
    return [
        ("GET", "/api/admin/overview", None, 200),
        ("GET", "/api/admin/workspaces", None, 200),
        ("GET", "/api/admin/tenants?q=Ega", None, 200),
        ("GET", f"/api/admin/tenants/{owner}", None, 200),
        ("GET", "/api/admin/payments?status=queue", None, 200),
        ("GET", f"/api/admin/payments/{pay}", None, 200),
        ("GET", f"/api/admin/payments/{pay}/receipt", None, 200),
        ("GET", "/api/admin/chats?q=Trust", None, 200),
        ("GET", "/api/admin/audit", None, 200),
        ("GET", "/api/admin/charts?days=30", None, 200),
        # Mutations: invalid on purpose (no reason) so the matrix does not change state.
        ("POST", f"/api/admin/payments/{pay}/reject", {"reason": ""}, 400),
        ("POST", f"/api/admin/tenants/{owner}/grant", {"plan": "pro", "days": 5}, 400),
        ("POST", f"/api/admin/tenants/{owner}/extend", {"days": 5}, 400),
        ("POST", f"/api/admin/tenants/{owner}/payments-block", {"blocked": False}, 400),
        ("POST", "/api/admin/workspaces/1/grant", {"plan": "free", "days": 30}, 404),
        ("POST", "/api/admin/payments/999999999/approve", {}, 404),
        ("POST", "/api/admin/payments/999999999/fake", {}, 404),
    ]


async def test_admin_permission_matrix(world) -> None:
    client, heads = world["client"], world["heads"]
    failures = []
    for method, path, body, want in _endpoints(world):
        for role in ("owner", "other", "stranger"):
            res = await client.request(method, path, headers=heads[role], json=body)
            if res.status != 403 or (await res.json()) != {"error": "forbidden"}:
                failures.append(f"{method} {path} as {role}: {res.status}")
        res = await client.request(method, path, json=body)
        if res.status != 401:
            failures.append(f"{method} {path} anonymous: {res.status}")
        res = await client.request(method, path, headers=heads["super"], json=body)
        if res.status != want:
            failures.append(f"{method} {path} as super: {res.status} != {want}")
    assert not failures, "\n".join(failures)
    # Non-super attempts never touched the payment.
    detail = await (
        await client.get(f"/api/admin/payments/{world['pay']}", headers=heads["super"])
    ).json()
    assert detail["status"] == "pending"
    assert [e["action"] for e in detail["events"]] == ["created", "submitted"]


async def test_workspace_admin_api_scopes_grant_and_preserves_legacy_subscription(world) -> None:
    client, heads, sessions = world["client"], world["heads"], world["sessions"]
    async with sessions() as session:
        owner = await UserRepository(session).get_by_id(world["ids"][OWNER])
        free = await PlanRepository(session).get_by_code("free")
        assert owner is not None and free is not None
        now = datetime.now(UTC)
        legacy = Subscription(
            owner_id=owner.id,
            plan_id=free.id,
            status=SubscriptionStatus.TRIAL,
            source=SubscriptionSource.TRIAL,
            started_at=now,
            expires_at=now + timedelta(days=5),
        )
        session.add(legacy)
        workspace = await WorkspaceService(
            WorkspaceRepository(session), UserRepository(session)
        ).ensure(owner, vertical="tutor")
        await session.commit()
        workspace_id = workspace.id

    listed = await client.get("/api/admin/workspaces", headers=heads["super"])
    assert listed.status == 200
    workspace_data = next(
        row for row in (await listed.json())["workspaces"] if row["id"] == workspace_id
    )
    assert workspace_data["plan"]["code"] == "free"
    assert workspace_data["subscription"] is None

    granted = await client.post(
        f"/api/admin/workspaces/{workspace_id}/grant",
        headers=heads["super"],
        json={"plan": "free", "days": 30, "reason": "EduFlow sinovi"},
    )
    assert granted.status == 200
    body = await granted.json()
    assert body["id"] == workspace_id
    assert body["subscription"]["status"] == "active"

    async with sessions() as session:
        still_legacy = await SubscriptionRepository(session).get_open(owner.id)
        workspace_subscription = await SubscriptionRepository(session).get_open(
            owner.id, workspace_id
        )
        assert still_legacy is not None and still_legacy.id == legacy.id
        assert still_legacy.status is SubscriptionStatus.TRIAL
        assert workspace_subscription is not None
        assert workspace_subscription.status is SubscriptionStatus.ACTIVE


async def test_bootstrap_roles_and_overview_numbers(world) -> None:
    client, heads = world["client"], world["heads"]
    roles = (await (await client.get("/api/stats", headers=heads["super"])).json())["roles"]
    assert "super_admin" in roles
    assert (
        "super_admin"
        not in (await (await client.get("/api/stats", headers=heads["owner"])).json())["roles"]
    )
    data = await (await client.get("/api/admin/overview", headers=heads["super"])).json()
    for key in (
        "tenants",
        "active_by_plan",
        "trials",
        "mrr_uzs",
        "revenue_month_uzs",
        "founder_used",
        "founder_left",
        "payments_pending",
        "jobs_failed_24h",
        "ai_used_month",
    ):
        assert key in data
    assert data["payments_pending"] >= 1 and data["tenants"] >= 1
    assert data["founder_left"] == max(0, data["founder_slots"] - data["founder_used"])


async def test_approve_from_mini_app_uses_the_shared_service(world) -> None:
    client, heads, bot = world["client"], world["heads"], world["bot"]
    before = await (await client.get("/api/admin/overview", headers=heads["super"])).json()
    res = await client.post(
        f"/api/admin/payments/{world['pay']}/approve", headers=heads["super"], json={}
    )
    assert res.status == 200
    data = await res.json()
    assert data["status"] == "approved"
    last = data["events"][-1]
    assert last["action"] == "approved" and last["data"]["via"] == "webapp"
    assert last["actor"]["telegram_id"] == SUPER
    # Owner receives the receipt message with the reference code.
    assert any(
        chat == OWNER and data["ref"] in text and "tasdiqlandi" in text
        for chat, text, _ in bot.sent
    )
    again = await client.post(
        f"/api/admin/payments/{world['pay']}/reject", headers=heads["super"], json={"reason": "x"}
    )
    assert again.status == 409
    after = await (await client.get("/api/admin/overview", headers=heads["super"])).json()
    assert after["revenue_month_uzs"] == before["revenue_month_uzs"] + data["amount_uzs"]
    tenant = await (
        await client.get(f"/api/admin/tenants/{world['ids'][OWNER]}", headers=heads["super"])
    ).json()
    assert tenant["plan"]["code"] == "pro" and tenant["payments"][0]["status"] == "approved"


async def test_reject_with_reason_sends_dispute_button_and_fake_blocks(world) -> None:
    client, heads, bot = world["client"], world["heads"], world["bot"]
    res = await client.post(
        f"/api/admin/payments/{world['pay']}/reject",
        headers=heads["super"],
        json={"reason": "Pul tushmagan"},
    )
    assert res.status == 200
    notice = next((m for c, t, m in bot.sent if c == OWNER and "Pul tushmagan" in t), None)
    assert notice is not None
    assert notice.inline_keyboard[0][0].callback_data == f"p:dispute:{world['pay']}"
    # Fake twice (second request reuses the receipt and is flagged as a duplicate).
    fake1 = await client.post(
        f"/api/admin/payments/{world['pay']}/fake",
        headers=heads["super"],
        json={"note": "tahrirlangan"},
    )
    assert fake1.status == 200 and (await fake1.json())["is_fake"] is True
    second = await _submitted(world["sessions"], OWNER, "rcpt-1")
    detail = await (
        await client.get(f"/api/admin/payments/{second}", headers=heads["super"])
    ).json()
    assert detail["duplicate_of"] == world["pay"]
    assert [d["id"] for d in detail["duplicates"]] == [world["pay"]]
    assert detail["owner_flags"]["fake_receipts"] == 1
    fake2 = await client.post(f"/api/admin/payments/{second}/fake", headers=heads["super"], json={})
    assert (await fake2.json())["owner_flags"]["payments_blocked"] is True
    plan = await (await client.get("/api/plan", headers=heads["owner"])).json()
    assert plan["payments_blocked"] is True
    unblock = await client.post(
        f"/api/admin/tenants/{world['ids'][OWNER]}/payments-block",
        headers=heads["super"],
        json={"blocked": False, "reason": "Bank ko'chirmasi bilan tasdiqlandi"},
    )
    assert (await unblock.json())["user"]["payments_blocked"] is False
    audit = await (await client.get("/api/admin/audit", headers=heads["super"])).json()
    actions = [row["action"] for row in audit["audit"]]
    assert (
        "payments_unblocked" in actions
        and "marked_fake" in actions
        and "duplicate_receipt" in actions
    )


async def test_receipt_proxy_is_cached_and_never_leaks_telegram_urls(world) -> None:
    client, heads = world["client"], world["heads"]
    path = f"/api/admin/payments/{world['pay']}/receipt"
    first = await client.get(path, headers=heads["super"])
    assert first.status == 200 and first.content_type == "image/jpeg"
    assert await first.read() == b"\xff\xd8\xffJPEGDATA"
    assert "private" in first.headers["Cache-Control"]
    await client.get(path, headers=heads["super"])
    assert world["fetched"] == ["file-rcpt-1"]


async def test_grant_and_extend_require_reason_and_are_audited(world) -> None:
    client, heads = world["client"], world["heads"]
    owner = world["ids"][OWNER]
    res = await client.post(
        f"/api/admin/tenants/{owner}/grant",
        headers=heads["super"],
        json={"plan": "pro", "days": 10, "reason": "Hamkorlik sinovi"},
    )
    assert res.status == 200 and (await res.json())["plan"]["code"] == "pro"
    ext = await client.post(
        f"/api/admin/tenants/{owner}/extend",
        headers=heads["super"],
        json={"days": 5, "reason": "Texnik nosozlik uchun kompensatsiya"},
    )
    assert ext.status == 200
    body = await ext.json()
    assert {"code": "pro", "name": body["plan"]["name"]} in body["plans"]
    assert [row["action"] for row in body["audit"]][:2] == ["plan_extended", "plan_granted"]
    async with world["sessions"]() as s:
        rows = (
            (
                await s.execute(
                    select(AuditLog)
                    .where(AuditLog.actor_user_id == world["ids"][SUPER])
                    .order_by(AuditLog.id)
                )
            )
            .scalars()
            .all()
        )
    assert [r.action for r in rows] == ["plan_granted", "plan_extended"]
    assert rows[0].data["reason"] == "Hamkorlik sinovi" and rows[1].data["days"] == 5
    bad = await client.post(
        f"/api/admin/tenants/{owner}/grant",
        headers=heads["super"],
        json={"plan": "nope", "days": 3, "reason": "x"},
    )
    assert bad.status == 400 and (await bad.json())["error"] == "bad_plan"


async def test_chart_endpoints_permission_matrix(world) -> None:
    """Chat charts reuse M2 roles: owner and super admin may view, others get 403."""
    client, heads = world["client"], world["heads"]
    chat = world["ids"]["chat"]
    expected = {
        f"/api/charts?chat={chat}&days=30": {
            "super": 200,
            "owner": 200,
            "other": 403,
            "stranger": 403,
        },
        "/api/charts?chat=999999999": {"super": 404, "owner": 404, "other": 404, "stranger": 404},
        "/api/charts?chat=abc": {"super": 400, "owner": 400, "other": 400, "stranger": 400},
        "/api/charts?chat=all&days=90": {"super": 200, "owner": 200, "other": 200, "stranger": 200},
        "/api/me/charts?weeks=12": {"super": 200, "owner": 200, "other": 200, "stranger": 200},
    }
    failures = []
    for path, by_role in expected.items():
        if (await client.get(path)).status != 401:
            failures.append(f"{path} anonymous")
        for role, want in by_role.items():
            res = await client.get(path, headers=heads[role])
            if res.status != want:
                failures.append(f"{path} as {role}: {res.status} != {want}")
    assert not failures, "\n".join(failures)
    mine = await (await client.get("/api/charts?chat=all", headers=heads["owner"])).json()
    assert [c["id"] for c in mine["chats"]] == [chat] and len(mine["series"]) == 7
    # A user without chats sees an empty, zero-filled "all" view, never someone else's chat.
    other = await (await client.get("/api/charts?chat=all", headers=heads["other"])).json()
    assert other["chats"] == [] and all(row["answers"] == 0 for row in other["series"])
    data = await (await client.get("/api/admin/charts", headers=heads["super"])).json()
    assert len(data["months"]) == 12 and len(data["daily"]) == 30
