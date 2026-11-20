"""HTTP-level checks for the v2 dashboard endpoints against real Postgres."""

import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.chats import Chat, ChatType
from app.db.models.content import ContentItem, ContentKind
from app.db.models.quizzes import Quiz, QuizAnswer
from app.db.models.users import User
from app.webapp.auth import issue_session, session_secret
from app.webapp.members import MemberCountCache
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
_TG_USERS = (9300000001, 9300000002)
_TG_CHAT = -9300000001


async def _cleanup(session) -> None:
    chat_ids = select(Chat.id).where(Chat.telegram_chat_id == _TG_CHAT)
    quiz_ids = select(Quiz.id).where(Quiz.chat_id.in_(chat_ids))
    await session.execute(delete(QuizAnswer).where(QuizAnswer.quiz_id.in_(quiz_ids)))
    await session.execute(delete(Quiz).where(Quiz.chat_id.in_(chat_ids)))
    await session.execute(delete(ContentItem).where(ContentItem.chat_id.in_(chat_ids)))
    await session.execute(delete(Chat).where(Chat.telegram_chat_id == _TG_CHAT))
    await session.execute(delete(User).where(User.telegram_id.in_(_TG_USERS)))


def _init_data(telegram_id: int, token: str) -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(
            {"id": telegram_id, "first_name": "Owner", "photo_url": "https://t.me/i/u.jpg"}
        ),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
async def test_stats_and_leaderboard_over_http() -> None:
    settings = Settings(bot_token="1:test-token", database_url=_URL, super_admin_ids="505")
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _cleanup(session)
        await session.commit()
    try:
        now = datetime.now(UTC)
        async with sessions() as session:
            owner = User(telegram_id=_TG_USERS[0], language_code="uz", full_name="Owner")
            other = User(telegram_id=_TG_USERS[1], language_code="uz", full_name="Other")
            session.add_all([owner, other])
            await session.flush()
            chat = Chat(
                telegram_chat_id=_TG_CHAT,
                type=ChatType.CHANNEL,
                title="HTTP",
                owner_id=owner.id,
                added_at=now,
            )
            session.add(chat)
            await session.flush()
            session.add(
                ContentItem(
                    chat_id=chat.id, kind=ContentKind.DAILY, body="x", meta={}, published_at=now
                )
            )
            quiz = Quiz(
                chat_id=chat.id,
                question="q",
                options=["a", "b"],
                correct_index=0,
                mode="group_native",
                created_at=now,
            )
            session.add(quiz)
            await session.flush()
            session.add(
                QuizAnswer(
                    quiz_id=quiz.id,
                    user_id=other.id,
                    chosen_index=0,
                    is_correct=True,
                    answered_at=now,
                )
            )
            await session.commit()
            chat_id = chat.id

        async def _no_count(_chat_id: int) -> int:
            raise OSError("offline")

        app = create_app(settings, sessions, members=MemberCountCache(fetch=_no_count))
        secret = session_secret(settings.bot_token, settings.webapp_session_secret)
        owner_auth = {"Authorization": f"Bearer {issue_session(_TG_USERS[0], secret, 600)}"}
        other_auth = {"Authorization": f"Bearer {issue_session(_TG_USERS[1], secret, 600)}"}
        async with TestClient(TestServer(app)) as client:
            res = await client.get(f"/api/chats/{chat_id}/leaderboard", headers=owner_auth)
            assert res.status == 200
            body = await res.json()
            assert body["chat"]["id"] == chat_id
            assert body["board"]["members"][0]["name"] == "Other"
            assert body["board"]["members"][0]["points"] > 0

            # "other" answered a quiz there, so as a member they see the board, not settings.
            seen = await (
                await client.get(f"/api/chats/{chat_id}/leaderboard", headers=other_auth)
            ).json()
            assert seen["role"] == "member" and seen["board"]["me"]["rank"] == 1
            denied = await client.get(f"/api/chats/{chat_id}/report", headers=other_auth)
            assert denied.status == 403
            assert (await denied.json())["error"] == "not_owner"
            assert (await client.get(f"/api/chats/{chat_id}/leaderboard")).status == 401
            assert (
                await client.get("/api/chats/abc/leaderboard", headers=owner_auth)
            ).status == 400

            stats = await (await client.get("/api/stats", headers=owner_auth)).json()
            daily = stats["stats"]["daily"]
            assert len(daily) == 7
            assert sum(row["posts"] for row in daily) == 1
            assert sum(row["quizzes"] for row in daily) == 1
            assert sum(row["answers"] for row in daily) == 1
            card = stats["chats"][0]
            assert card["posts_total"] == 1 and card["quizzes_total"] == 1
            assert "member_count" not in card
            plan = stats["plan"]
            assert plan["ai_left"] == max(0, plan["ai_limit"] - plan["ai_used"])

            boot = await client.post("/api/bootstrap", json={"initData": "bad"})
            assert boot.status == 401
            good = await client.post(
                "/api/bootstrap", json={"initData": _init_data(_TG_USERS[0], settings.bot_token)}
            )
            assert good.status == 200
            data = await good.json()
            assert data["token"] and "owner" in data["roles"]
            assert data["user"]["photo_url"] == "https://t.me/i/u.jpg"
            assert data["dash"]["chats"][0]["id"] == chat_id
            assert len(data["dash"]["stats"]["daily"]) == 7
            assert data["dash"]["stats"]["week_counts"]["posts"]["value"] == 1
            fresh = {"Authorization": f"Bearer {data['token']}"}
            assert (
                await client.get(f"/api/chats/{chat_id}/leaderboard", headers=fresh)
            ).status == 200
            gz = await client.get("/api/stats", headers={**owner_auth, "Accept-Encoding": "gzip"})
            assert gz.headers.get("Cache-Control") == "no-store"

            listed = await (await client.get("/api/chats", headers=owner_auth)).json()
            assert listed["chats"][0]["posts_total"] == 1
            empty = await (await client.get("/api/stats", headers=other_auth)).json()
            assert empty["chats"] == []
            assert all(row["posts"] == 0 for row in empty["stats"]["daily"])
        tight = create_app(
            settings,
            sessions,
            members=MemberCountCache(fetch=_no_count),
            limiter=RateLimiter(limit=2),
        )
        async with TestClient(TestServer(tight)) as client:
            path = f"/api/chats/{chat_id}/leaderboard"
            assert (await client.get(path, headers=owner_auth)).status == 200
            assert (await client.get(path, headers=owner_auth)).status == 200
            assert (await client.get(path, headers=owner_auth)).status == 429
            # Same tunnel address, different Telegram user: separate budget.
            assert (await client.get(f"/api/chats/{chat_id}", headers=other_auth)).status == 403
    finally:
        async with sessions() as session:
            await _cleanup(session)
            await session.commit()
        await engine.dispose()
