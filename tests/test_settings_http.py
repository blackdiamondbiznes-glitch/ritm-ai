"""Settings moved from the bot chat into the Mini App: same validation, same services,
server-side permissions (owner; admins only with admins_can_edit; disconnect owner-only)."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from aiogram.enums import ChatMemberStatus, ChatType
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.audit import AuditLog
from app.db.models.chats import Chat, ChatProfile
from app.db.models.chats import ChatType as DbChatType
from app.db.models.jobs import Job
from app.db.models.payments import Payment
from app.db.models.plans import Plan
from app.db.models.schedules import Schedule
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.services.pending import PendingChat, PendingChatStore
from app.services.profiles import ProfileError, ProfileInput, validate_profile
from app.webapp.admins import ChatAdminCache
from app.webapp.auth import issue_session, session_secret
from app.webapp.members import MemberCountCache
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.pg import allow_purge

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
SUPER, OWNER, ADMIN, STRANGER = 9880000001, 9880000002, 9880000003, 9880000004
_IDS = (SUPER, OWNER, ADMIN, STRANGER)
CHAT, NEW_CHAT, OTHERS_CHAT = -9880000001, -9880000002, -9880000003

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(s) -> None:
    await allow_purge(s)
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    chats = select(Chat.id).where(or_(Chat.owner_id.in_(ids), Chat.telegram_chat_id == CHAT))
    await s.execute(delete(Job).where(Job.chat_id.in_(chats)))
    await s.execute(delete(Schedule).where(Schedule.chat_id.in_(chats)))
    await s.execute(delete(ChatProfile).where(ChatProfile.chat_id.in_(chats)))
    await s.execute(delete(AuditLog).where(AuditLog.actor_user_id.in_(ids)))
    await s.execute(delete(Payment).where(Payment.owner_id.in_(ids)))
    await s.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await s.execute(delete(Chat).where(Chat.owner_id.in_(ids)))
    await s.execute(delete(User).where(User.telegram_id.in_(_IDS)))


class _Bot:
    """Just enough of aiogram's Bot for the live rights check in link_chat."""

    id = 4242

    async def get_chat(self, chat_id):
        return SimpleNamespace(type=ChatType.SUPERGROUP, title="Yangi guruh", username=None)

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status=ChatMemberStatus.ADMINISTRATOR, can_post_messages=None)

    async def send_message(self, *_a, **_kw):
        return None


@pytest.fixture
async def world():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sessions() as s:
        await _purge(s)
        users = {
            tg: User(telegram_id=tg, full_name=f"U{tg % 10}", language_code="uz") for tg in _IDS
        }
        s.add_all(users.values())
        await s.flush()
        pro = (await s.execute(select(Plan).where(Plan.code == "pro"))).scalar_one()
        s.add(
            Subscription(
                owner_id=users[OWNER].id,
                plan_id=pro.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=now - timedelta(days=1),
                expires_at=now + timedelta(days=30),
            )
        )
        chat = Chat(
            telegram_chat_id=CHAT,
            type=DbChatType.SUPERGROUP,
            title="Sozlama chat",
            owner_id=users[OWNER].id,
            added_at=now,
        )
        s.add(chat)
        s.add_all(
            [
                Payment(
                    owner_id=users[OWNER].id,
                    plan_id=pro.id,
                    amount_uzs=39_017,
                    status="rejected",
                    ref_code="RITM-T1",
                    reject_reason="Summa mos emas",
                ),
                Payment(
                    owner_id=users[STRANGER].id,
                    plan_id=pro.id,
                    amount_uzs=29_011,
                    status="pending",
                    ref_code="RITM-T2",
                ),
            ]
        )
        await s.commit()
        ids = {tg: users[tg].id for tg in _IDS}
        ids["chat"] = chat.id
    pending = PendingChatStore()
    for tg_chat, adder in ((NEW_CHAT, OWNER), (OTHERS_CHAT, STRANGER)):
        pending.put(PendingChat(tg_chat, f"Pending {tg_chat}", "supergroup", None, adder, now))
    settings = Settings(
        bot_token="1:test-token",
        database_url=_URL,
        super_admin_ids=str(SUPER),
        support_username="@Khoshimov_Adkham",
    )

    async def no_count(_chat_id: int) -> int:
        raise OSError("offline")

    async def admins_of(chat_id: int):
        return [ADMIN] if chat_id == CHAT else []

    app = create_app(
        settings,
        sessions,
        limiter=RateLimiter(limit=10000),
        bot=_Bot(),
        members=MemberCountCache(fetch=no_count),
        admins=ChatAdminCache(fetch=admins_of),
        bot_username="ritm_airobot",
        pending=pending,
    )
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        name: {"Authorization": f"Bearer {issue_session(tg, secret, 600)}"}
        for name, tg in (
            ("super", SUPER),
            ("owner", OWNER),
            ("admin", ADMIN),
            ("stranger", STRANGER),
        )
    }
    try:
        async with TestClient(TestServer(app)) as client:
            yield {
                "client": client,
                "heads": heads,
                "ids": ids,
                "sessions": sessions,
                "pending": pending,
            }
    finally:
        async with sessions() as s:
            await _purge(s)
            await s.commit()
        await engine.dispose()


GOOD = {
    "niche_code": "edu",
    "niche_description": "Matematika 5-sinf uchun",
    "tone": "friendly",
    "audience_level": "beginner",
    "language": "uz",
    "timezone": "Asia/Tashkent",
}


async def test_profile_read_matrix_and_options(world) -> None:
    c, h, chat = world["client"], world["heads"], world["ids"]["chat"]
    path = f"/api/chats/{chat}/profile"
    assert (await c.get(path)).status == 401
    assert (await c.get(path, headers=h["stranger"])).status == 403
    assert (await c.get("/api/chats/999999999/profile", headers=h["owner"])).status == 404
    owner = await (await c.get(path, headers=h["owner"])).json()
    assert owner["profile"] is None and owner["can_edit"] is True
    assert [n["code"] for n in owner["options"]["niches"]] == [
        "lang",
        "biz",
        "fit",
        "it",
        "edu",
        "news",
    ]
    assert owner["options"]["niches"][4]["label"] == "Taʼlim"  # the bot wizard's wording
    assert "Asia/Tashkent" in owner["options"]["timezones"]
    admin = await (await c.get(path, headers=h["admin"])).json()
    assert admin["can_edit"] is False
    assert (await c.get(path, headers=h["super"])).status == 200


async def test_profile_save_uses_the_wizard_validation(world) -> None:
    c, h, chat = world["client"], world["heads"], world["ids"]["chat"]
    path = f"/api/chats/{chat}/profile"
    cases = [
        {**GOOD, "tone": "angry"},
        {**GOOD, "niche_description": "   "},
        {**GOOD, "niche_code": "x" * 201},
        {**GOOD, "timezone": "Mars/Base"},
        {**GOOD, "language": "de"},
    ]
    for body in cases:
        try:
            validate_profile(ProfileInput(**body))
            expected = None
        except ProfileError as exc:
            expected = f"input_{exc.code}"
        res = await c.put(path, json=body, headers=h["owner"])
        assert res.status == 400 and (await res.json())["error"] == expected
    assert (await c.put(path, json={**GOOD, "tone": 5}, headers=h["owner"])).status == 400
    # Admins may not edit until the owner allows it.
    assert (await c.put(path, json=GOOD, headers=h["admin"])).status == 403
    assert (await c.put(path, json=GOOD, headers=h["stranger"])).status == 403
    saved = await (await c.put(path, json=GOOD, headers=h["owner"])).json()
    assert saved["profile"]["niche_code"] == "edu"
    # A custom niche is free text, exactly like "Boshqa" in the bot.
    custom = {**GOOD, "niche_code": "Shaxmat", "timezone": "Europe/Moscow"}
    assert (await c.put(path, json=custom, headers=h["owner"])).status == 200
    # Turning post quizzes off survives a later profile edit.
    patch = await c.patch(
        f"/api/chats/{chat}",
        json={"admin_post_quiz": False, "admins_can_edit": True},
        headers=h["owner"],
    )
    assert patch.status == 200
    res = await c.put(path, json={**custom, "tone": "fun"}, headers=h["admin"])
    assert res.status == 200
    async with world["sessions"]() as s:
        profile = (
            await s.execute(select(ChatProfile).where(ChatProfile.chat_id == chat))
        ).scalar_one()
    assert profile.niche_code == "Shaxmat" and profile.tone == "fun"
    assert profile.timezone == "Europe/Moscow"
    assert "admin_post_quiz" not in (profile.modules_enabled or [])
    assert "leaderboard" in (profile.modules_enabled or [])


async def test_board_now_and_disconnect_permissions(world) -> None:
    c, h, chat = world["client"], world["heads"], world["ids"]["chat"]
    board = f"/api/chats/{chat}/board-now"
    assert (await (await c.post(board, headers=h["owner"])).json())["result"] == "profile"
    await c.put(f"/api/chats/{chat}/profile", json=GOOD, headers=h["owner"])
    assert (await (await c.post(board, headers=h["admin"])).json())["result"] == "empty"
    assert (await c.post(board, headers=h["stranger"])).status == 403
    off = f"/api/chats/{chat}/disconnect"
    await c.patch(f"/api/chats/{chat}", json={"admins_can_edit": True}, headers=h["owner"])
    res = await c.post(off, headers=h["admin"])
    assert res.status == 403 and (await res.json())["error"] == "owner_only"
    assert (await c.post(off, headers=h["stranger"])).status == 403
    assert (await c.post(off, headers=h["owner"])).status == 200
    async with world["sessions"]() as s:
        row = await s.get(Chat, chat)
        audit = (
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.action == "chat_disconnected", AuditLog.entity_id == str(chat)
                    )
                )
            )
            .scalars()
            .all()
        )
    assert row.is_active is False and len(audit) == 1


async def test_my_settings_validation_and_support(world) -> None:
    c, h = world["client"], world["heads"]
    assert (await c.get("/api/me/settings")).status == 401
    data = await (await c.get("/api/me/settings", headers=h["owner"])).json()
    assert data["language"] == "uz" and data["notify_reports"] is True
    assert data["default_timezone"] == "Asia/Tashkent"
    assert data["support"] == "Khoshimov_Adkham"
    for bad in ({"language": "de"}, {"default_timezone": "Mars/Base"}, {"notify_expiry": "no"}):
        res = await c.patch("/api/me/settings", json=bad, headers=h["owner"])
        assert res.status == 400
    # A bad field rejects the whole update.
    await c.patch(
        "/api/me/settings", json={"language": "ru", "notify_reports": "x"}, headers=h["owner"]
    )
    ok = await c.patch(
        "/api/me/settings",
        json={"language": "ru", "notify_reports": False, "default_timezone": "Asia/Dubai"},
        headers=h["owner"],
    )
    body = await ok.json()
    assert body["language"] == "ru" and body["notify_reports"] is False
    async with world["sessions"]() as s:
        user = (await s.execute(select(User).where(User.telegram_id == OWNER))).scalar_one()
    assert user.language_code == "ru" and user.ui_language_set is True
    assert user.notify_reports is False and user.default_timezone == "Asia/Dubai"
    me = await (await c.get("/api/me", headers=h["owner"])).json()
    assert me["user"]["language"] == "ru" and me["support"] == "Khoshimov_Adkham"
    # The new default zone preselects the profile of a chat without one.
    form = await (
        await c.get(f"/api/chats/{world['ids']['chat']}/profile", headers=h["owner"])
    ).json()
    assert form["default_timezone"] == "Asia/Dubai"


async def test_my_payments_are_mine_only(world) -> None:
    c, h = world["client"], world["heads"]
    rows = (await (await c.get("/api/me/payments", headers=h["owner"])).json())["payments"]
    assert [r["ref"] for r in rows] == ["RITM-T1"]
    assert rows[0]["status"] == "rejected" and rows[0]["reason"] == "Summa mos emas"
    assert rows[0]["plan"] and rows[0]["amount_uzs"] == 39_017
    other = (await (await c.get("/api/me/payments", headers=h["stranger"])).json())["payments"]
    assert [r["ref"] for r in other] == ["RITM-T2"] and other[0]["reason"] is None


async def test_connect_from_the_mini_app(world) -> None:
    c, h = world["client"], world["heads"]
    info = await (await c.get("/api/connect", headers=h["owner"])).json()
    assert [p["telegram_chat_id"] for p in info["pending"]] == [NEW_CHAT]
    assert info["links"]["group"].startswith("https://t.me/ritm_airobot?startgroup=")
    assert info["can_confirm"] is True
    # Someone else's pending chat cannot be claimed.
    res = await c.post("/api/connect", json={"telegram_chat_id": OTHERS_CHAT}, headers=h["owner"])
    assert res.status == 404
    assert (
        await c.post("/api/connect", json={"telegram_chat_id": "x"}, headers=h["owner"])
    ).status == 400
    done = await (
        await c.post("/api/connect", json={"telegram_chat_id": NEW_CHAT}, headers=h["owner"])
    ).json()
    assert done["chat_id"] and done["already"] is False
    async with world["sessions"]() as s:
        chat = await s.get(Chat, done["chat_id"])
    assert chat.owner_id == world["ids"][OWNER] and chat.is_active
    assert world["pending"].get(NEW_CHAT) is None
    # Decline only removes the caller's own pending rows.
    await c.post("/api/connect/decline", json={"telegram_chat_id": OTHERS_CHAT}, headers=h["owner"])
    assert world["pending"].get(OTHERS_CHAT) is not None
    await c.post(
        "/api/connect/decline", json={"telegram_chat_id": OTHERS_CHAT}, headers=h["stranger"]
    )
    assert world["pending"].get(OTHERS_CHAT) is None


async def test_terms_document_reuses_the_payment_offer(world) -> None:
    c, h = world["client"], world["heads"]
    assert (await c.get("/api/docs/terms")).status == 401
    doc = await (await c.get("/api/docs/terms", headers=h["stranger"])).json()
    assert doc["version"] == "2026-11-v1" and "2026-11-v1" in doc["text"]
    assert "<b>" not in doc["text"] and "Soxta" in doc["text"]


async def test_regular_user_connects_own_chat_and_becomes_owner(world) -> None:
    """A user with no chats of their own uses the same connect flow and gets the owner panel."""
    c, h = world["client"], world["heads"]
    before = await (await c.get("/api/stats", headers=h["stranger"])).json()
    assert "owner" not in before["roles"] and before["chats"] == []
    info = await (await c.get("/api/connect", headers=h["stranger"])).json()
    assert [p["telegram_chat_id"] for p in info["pending"]] == [OTHERS_CHAT]
    assert "admin=" in info["links"]["group"] and "startchannel=" in info["links"]["channel"]
    done = await (
        await c.post("/api/connect", json={"telegram_chat_id": OTHERS_CHAT}, headers=h["stranger"])
    ).json()
    assert done["chat_id"] and done["already"] is False and done["trial_started"] is True
    after = await (await c.get("/api/stats", headers=h["stranger"])).json()
    assert "owner" in after["roles"]
    assert [chat["id"] for chat in after["chats"]] == [done["chat_id"]]
    async with world["sessions"]() as s:
        chat = await s.get(Chat, done["chat_id"])
        assert chat.owner_id == world["ids"][STRANGER]
        await s.execute(delete(Job).where(Job.chat_id == chat.id))
        await s.execute(delete(Schedule).where(Schedule.chat_id == chat.id))
        await s.execute(delete(ChatProfile).where(ChatProfile.chat_id == chat.id))
        await s.commit()
