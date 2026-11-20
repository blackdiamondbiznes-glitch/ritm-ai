"""M2 permission matrix over HTTP on real Postgres: owner, Telegram admin, member,
stranger and super admin against every Mini App endpoint, plus member stats."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.chats import Chat, ChatType
from app.db.models.content import ContentItem, ContentKind
from app.db.models.quizzes import Quiz, QuizAnswer
from app.db.models.schedules import Schedule
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.webapp.admins import ChatAdminCache
from app.webapp.auth import issue_session, session_secret
from app.webapp.members import MemberCountCache
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, ADMIN, MEMBER, STRANGER, SUPER = 9500000001, 9500000002, 9500000003, 9500000004, 9500000005
_USERS = (OWNER, ADMIN, MEMBER, STRANGER, SUPER)
CHAT_A, CHAT_B, CHAT_OFF = -9500000001, -9500000002, -9500000003
_CHATS = (CHAT_A, CHAT_B, CHAT_OFF)

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _cleanup(session) -> None:
    chat_ids = select(Chat.id).where(Chat.telegram_chat_id.in_(_CHATS))
    quiz_ids = select(Quiz.id).where(Quiz.chat_id.in_(chat_ids))
    user_ids = select(User.id).where(User.telegram_id.in_(_USERS))
    await session.execute(delete(QuizAnswer).where(QuizAnswer.quiz_id.in_(quiz_ids)))
    await session.execute(delete(Quiz).where(Quiz.chat_id.in_(chat_ids)))
    await session.execute(delete(ContentItem).where(ContentItem.chat_id.in_(chat_ids)))
    await session.execute(delete(Schedule).where(Schedule.chat_id.in_(chat_ids)))
    await session.execute(delete(Chat).where(Chat.telegram_chat_id.in_(_CHATS)))
    await session.execute(delete(Subscription).where(Subscription.owner_id.in_(user_ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_USERS)))


class _Telegram:
    """getChatAdministrators stand-in: ADMIN administers chat A only."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    async def __call__(self, chat_id: int) -> list[int]:
        self.calls.append(chat_id)
        if chat_id == CHAT_A:
            return [OWNER, ADMIN]
        if chat_id == CHAT_B:
            return [OWNER]
        raise OSError("bot is not a member")


async def _seed(sessions) -> dict[str, int]:
    now = datetime.now(UTC)
    async with sessions() as s:
        users = {
            tg: User(telegram_id=tg, full_name=f"U{tg % 100}", language_code="uz") for tg in _USERS
        }
        s.add_all(users.values())
        await s.flush()
        s.add(
            Subscription(
                owner_id=users[OWNER].id,
                plan_id=3,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=now - timedelta(days=1),
                expires_at=now + timedelta(days=30),
            )
        )
        a = Chat(
            telegram_chat_id=CHAT_A,
            type=ChatType.GROUP,
            title="A",
            owner_id=users[OWNER].id,
            added_at=now,
        )
        b = Chat(
            telegram_chat_id=CHAT_B,
            type=ChatType.GROUP,
            title="B",
            owner_id=users[OWNER].id,
            added_at=now,
        )
        off = Chat(
            telegram_chat_id=CHAT_OFF,
            type=ChatType.GROUP,
            title="Off",
            owner_id=users[OWNER].id,
            added_at=now,
            is_active=False,
        )
        s.add_all([a, b, off])
        await s.flush()
        s.add(
            ContentItem(chat_id=a.id, kind=ContentKind.DAILY, body="x", meta={}, published_at=now)
        )
        await s.flush()

        def quiz(chat, question, when):
            row = Quiz(
                chat_id=chat.id,
                question=question,
                options=["Ha", "Yo'q", "Bilmayman"],
                correct_index=0,
                mode="group_native",
                created_at=when,
            )
            s.add(row)
            return row

        old = now - timedelta(days=40)
        qa1, qa2, qa3 = quiz(a, "A1", now), quiz(a, "A2", now), quiz(a, "A-old", old)
        qb1, qoff = quiz(b, "B1", now), quiz(off, "Off1", now)
        await s.flush()
        m, adm = users[MEMBER], users[ADMIN]

        def answer(q, user, chosen, when):
            s.add(
                QuizAnswer(
                    quiz_id=q.id,
                    user_id=user.id,
                    chosen_index=chosen,
                    is_correct=chosen == 0,
                    answered_at=when,
                )
            )

        t = now - timedelta(minutes=30)
        answer(qa1, m, 0, t)  # correct, this week
        answer(qa2, m, 1, t + timedelta(minutes=1))  # wrong, this week
        answer(qa3, m, 0, old)  # correct, 40 days ago
        answer(qb1, m, 0, t + timedelta(minutes=2))  # correct, chat B
        answer(qoff, m, 0, t + timedelta(minutes=3))  # inactive chat: hidden from member view
        answer(qa1, adm, 0, t)
        answer(qa2, adm, 0, t)  # admin leads chat A this week with 2 correct
        await s.commit()
        return {"A": a.id, "B": b.id, "OFF": off.id, "member_id": m.id}


@pytest.fixture
async def world():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        await _cleanup(s)
        await s.commit()
    ids = await _seed(sessions)
    telegram = _Telegram()
    settings = Settings(bot_token="1:test-token", database_url=_URL, super_admin_ids=str(SUPER))

    async def no_count(_chat_id: int) -> int:
        raise OSError("offline")

    app = create_app(
        settings,
        sessions,
        limiter=RateLimiter(limit=10000),
        members=MemberCountCache(fetch=no_count),
        admins=ChatAdminCache(fetch=telegram),
    )
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        name: {"Authorization": f"Bearer {issue_session(tg, secret, 600)}"}
        for name, tg in (
            ("owner", OWNER),
            ("admin", ADMIN),
            ("member", MEMBER),
            ("stranger", STRANGER),
            ("super", SUPER),
        )
    }
    try:
        async with TestClient(TestServer(app)) as client:
            yield client, ids, heads, telegram, sessions
    finally:
        async with sessions() as s:
            await _cleanup(s)
            await s.commit()
        await engine.dispose()


# Expected status per role for chat A. `member` answered quizzes in A; `admin` is a
# live Telegram admin of A but not its owner; `super` is in SUPER_ADMIN_IDS.
MATRIX = [
    (
        "GET",
        "/api/chats/{A}",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 403, "stranger": 403},
    ),
    (
        "GET",
        "/api/chats/{A}/report",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 403, "stranger": 403},
    ),
    (
        "GET",
        "/api/chats/{A}/leaderboard",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 200, "stranger": 403},
    ),
    (
        "POST",
        "/api/chats/{A}/post-now",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 403, "stranger": 403},
    ),
    (
        "POST",
        "/api/chats/{A}/quiz-now",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 403, "stranger": 403},
    ),
    (
        "PATCH",
        "/api/chats/{A}",
        {"daily_time": "10:00", "daily_enabled": False},
        {"owner": 200, "super": 200, "admin": 403, "member": 403, "stranger": 403},
    ),
    (
        "PATCH",
        "/api/chats/{A}",
        {"admins_can_edit": False},
        {"owner": 200, "super": 200, "admin": 403, "member": 403, "stranger": 403},
    ),
    # Chat B: the admin is not a Telegram admin there; the member answered there.
    (
        "GET",
        "/api/chats/{B}",
        None,
        {"owner": 200, "super": 200, "admin": 403, "member": 403, "stranger": 403},
    ),
    (
        "GET",
        "/api/chats/{B}/leaderboard",
        None,
        {"owner": 200, "super": 200, "admin": 403, "member": 200, "stranger": 403},
    ),
    (
        "GET",
        "/api/stats",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 200, "stranger": 200},
    ),
    (
        "GET",
        "/api/chats",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 200, "stranger": 200},
    ),
    (
        "GET",
        "/api/plan",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 200, "stranger": 200},
    ),
    (
        "GET",
        "/api/me/stats",
        None,
        {"owner": 200, "super": 200, "admin": 200, "member": 200, "stranger": 200},
    ),
    (
        "GET",
        "/api/chats/999999999",
        None,
        {"owner": 404, "super": 404, "admin": 404, "member": 404, "stranger": 404},
    ),
]


async def test_permission_matrix(world) -> None:
    client, ids, heads, _telegram, _sessions = world
    failures = []
    for method, raw, body, expected in MATRIX:
        path = raw.format(A=ids["A"], B=ids["B"])
        for role, status in expected.items():
            res = await client.request(method, path, headers=heads[role], json=body)
            if res.status != status:
                failures.append(f"{method} {path} as {role}: {res.status} != {status}")
    for method, raw, _body, _expected in MATRIX:
        res = await client.request(method, raw.format(A=ids["A"], B=ids["B"]))
        if res.status != 401:
            failures.append(f"{method} {raw} anonymous: {res.status}")
    assert not failures, "\n".join(failures)


async def test_owner_can_delegate_editing_to_admins(world) -> None:
    client, ids, heads, _telegram, _sessions = world
    path = f"/api/chats/{ids['A']}"
    admin_view = await (await client.get(path, headers=heads["admin"])).json()
    assert admin_view["access"] == {
        "role": "admin",
        "can_edit": False,
        "can_act": True,
        "can_manage_admins": False,
        "admins_can_edit": False,
    }
    on = await client.patch(path, headers=heads["owner"], json={"admins_can_edit": True})
    assert on.status == 200 and (await on.json())["access"]["admins_can_edit"] is True
    edit = await client.patch(
        path, headers=heads["admin"], json={"daily_time": "11:30", "daily_enabled": True}
    )
    assert edit.status == 200
    saved = await edit.json()
    assert saved["daily"]["time"] == "11:30" and saved["access"]["can_edit"] is True
    # Delegated admins still cannot change the delegation itself.
    grab = await client.patch(path, headers=heads["admin"], json={"admins_can_edit": False})
    assert grab.status == 403 and (await grab.json())["error"] == "owner_only"
    cards = (await (await client.get("/api/chats", headers=heads["admin"])).json())["chats"]
    assert [(c["id"], c["role"], c["can_edit"]) for c in cards] == [(ids["A"], "admin", True)]


async def test_roles_in_bootstrap_payloads(world) -> None:
    client, ids, heads, _telegram, _sessions = world

    async def dash(role):
        return await (await client.get("/api/stats", headers=heads[role])).json()

    owner = await dash("owner")
    assert owner["roles"] == ["owner"]
    assert sorted((c["id"], c["role"]) for c in owner["chats"]) == sorted(
        [(ids["A"], "owner"), (ids["B"], "owner")]
    )
    admin = await dash("admin")
    assert admin["roles"] == ["admin", "member"]
    assert [(c["id"], c["role"]) for c in admin["chats"]] == [(ids["A"], "admin")]
    assert admin["member"]["totals"]["correct"] == 2
    member = await dash("member")
    assert member["roles"] == ["member"] and member["chats"] == []
    assert {c["id"] for c in member["member"]["chats"]} == {ids["A"], ids["B"]}
    stranger = await dash("stranger")
    assert stranger["roles"] == [] and stranger["chats"] == [] and stranger["member"] is None
    sup = await dash("super")
    assert sup["roles"] == ["super_admin"]


async def test_member_stats_are_exact(world) -> None:
    client, ids, heads, _telegram, _sessions = world
    data = (await (await client.get("/api/me/stats", headers=heads["member"])).json())["member"]
    by_chat = {c["id"]: c for c in data["chats"]}
    assert set(by_chat) == {ids["A"], ids["B"]}  # the inactive chat is left out
    a, b = by_chat[ids["A"]], by_chat[ids["B"]]
    assert (a["answers"], a["correct"], a["accuracy"], a["points_total"]) == (3, 2, 67, 20)
    assert (a["week_points"], a["week_rank"], a["week_members"]) == (10, 2, 2)
    assert (b["answers"], b["correct"], b["accuracy"], b["week_points"], b["week_rank"]) == (
        1,
        1,
        100,
        10,
        1,
    )
    assert data["totals"] == {
        "answers": 4,
        "correct": 3,
        "accuracy": 75,
        "points_total": 30,
        "week_points": 20,
    }
    history = data["history"]
    assert [h["question"] for h in history] == ["Off1", "B1", "A2", "A1", "A-old"]
    a2 = history[2]
    assert (a2["chosen"], a2["correct"], a2["is_correct"], a2["chat_title"]) == (
        "Yo'q",
        "Ha",
        False,
        "A",
    )
    board = await (
        await client.get(f"/api/chats/{ids['A']}/leaderboard", headers=heads["member"])
    ).json()
    assert board["board"]["me"] == {"rank": 2, "points": 10, "correct": 1, "answers": 2}
    assert [row.get("me", False) for row in board["board"]["members"]] == [False, True]
    assert (await (await client.get("/api/me/stats", headers=heads["stranger"])).json()) == {
        "member": None
    }


async def test_admin_lookups_are_cached_and_owners_skip_telegram(world) -> None:
    client, ids, heads, telegram, _sessions = world
    for _ in range(3):
        assert (await client.get(f"/api/chats/{ids['A']}", headers=heads["owner"])).status == 200
    assert telegram.calls == []
    for _ in range(3):
        assert (await client.get(f"/api/chats/{ids['A']}", headers=heads["admin"])).status == 200
    assert telegram.calls.count(CHAT_A) == 1
