"""HTTP: link a chat, store reminder rules, and queue an announcement."""

import os
from datetime import UTC, datetime

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.chats import Chat, ChatType
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.jobs import Job
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription
from app.db.models.tutor_notices import TutorNotice
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, OTHER, STUDENT = 9864600001, 9864600002, 9864600003
_IDS = (OWNER, OTHER, STUDENT)
CHAT_TG = -100986460099

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    user_ids = list((await session.execute(ids)).scalars())
    targets = list(_IDS) + user_ids + [CHAT_TG]
    await session.execute(delete(TutorNotice).where(TutorNotice.target_id.in_(targets)))
    await session.execute(delete(Job).where(Job.type == "tutor_notify"))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(Chat).where(Chat.telegram_chat_id == CHAT_TG))
    if user_ids:
        await session.execute(delete(Subscription).where(Subscription.owner_id.in_(user_ids)))
        await session.execute(delete(Chat).where(Chat.owner_id.in_(user_ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        now = datetime.now(UTC)
        session.add_all(
            [
                User(telegram_id=OWNER, full_name="Lola", language_code="uz"),
                User(telegram_id=OTHER, full_name="Other", language_code="uz"),
                User(telegram_id=STUDENT, full_name="Ali", language_code="uz"),
            ]
        )
        await session.flush()
        owner = (await session.execute(select(User).where(User.telegram_id == OWNER))).scalar_one()
        other = (await session.execute(select(User).where(User.telegram_id == OTHER))).scalar_one()
        session.add_all(
            [
                Chat(
                    telegram_chat_id=CHAT_TG,
                    type=ChatType.GROUP,
                    title="A & B",
                    owner_id=owner.id,
                    added_at=now,
                    is_active=True,
                ),
                Chat(
                    telegram_chat_id=CHAT_TG - 1,
                    type=ChatType.GROUP,
                    title="Boshqa",
                    owner_id=other.id,
                    added_at=now,
                    is_active=True,
                ),
            ]
        )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        name: {"Authorization": f"Bearer {issue_session(telegram, secret, 600)}"}
        for name, telegram in (("owner", OWNER), ("other", OTHER))
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


async def _group(http, heads) -> int:
    created = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "Ingliz", "weekdays": [1], "start": "18:00", "end": "19:30"},
    )
    assert created.status == 200
    return (await created.json())["created_id"]


async def test_chat_link_rules_and_announcement_are_owner_scoped(client) -> None:
    http, heads, sessions = client
    group_id = await _group(http, heads)
    student = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Ali Valiyev", "status": "paid", "group_ids": [group_id]},
    )
    student_id = (await student.json())["created_id"]
    async with sessions() as session:
        owner = (await session.execute(select(User).where(User.telegram_id == OWNER))).scalar_one()
        other = (await session.execute(select(User).where(User.telegram_id == OTHER))).scalar_one()
        chat = (
            await session.execute(select(Chat).where(Chat.telegram_chat_id == CHAT_TG))
        ).scalar_one()
        foreign = (
            await session.execute(select(Chat).where(Chat.owner_id == other.id))
        ).scalar_one()
        card = await session.get(TutorStudent, student_id)
        card.telegram_id = STUDENT
        await session.commit()
        owner_id, chat_id, foreign_id = owner.id, chat.id, foreign.id
    hidden = await http.put(
        f"/api/tutor/groups/{group_id}/chat", headers=heads["other"], json={"chat_id": chat_id}
    )
    assert hidden.status == 404
    stolen = await http.put(
        f"/api/tutor/groups/{group_id}/chat", headers=heads["owner"], json={"chat_id": foreign_id}
    )
    assert stolen.status == 400 and (await stolen.json())["error"] == "chat"
    linked = await http.put(
        f"/api/tutor/groups/{group_id}/chat", headers=heads["owner"], json={"chat_id": chat_id}
    )
    body = await linked.json()
    assert linked.status == 200 and body["chat_id"] == chat_id
    assert any(item["title"] == "A & B" for item in body["chats"])
    bad = await http.put(
        f"/api/tutor/groups/{group_id}/notify",
        headers=heads["owner"],
        json={"remind_lesson_min": 10, "remind_fee_days": 3, "fee_in_group": False},
    )
    assert bad.status == 400
    saved = await http.put(
        f"/api/tutor/groups/{group_id}/notify",
        headers=heads["owner"],
        json={"remind_lesson_min": 15, "remind_fee_days": None, "fee_in_group": True},
    )
    assert saved.status == 200 and (await saved.json())["remind_lesson_min"] == 15
    empty = await http.post(
        f"/api/tutor/groups/{group_id}/announce",
        headers=heads["owner"],
        json={"text": "  ", "to_chat": True, "to_students": True},
    )
    assert empty.status == 400 and (await empty.json())["error"] == "empty"
    neither = await http.post(
        f"/api/tutor/groups/{group_id}/announce",
        headers=heads["owner"],
        json={"text": "Salom", "to_chat": False, "to_students": False},
    )
    assert neither.status == 400 and (await neither.json())["error"] == "target"
    queued = await http.post(
        f"/api/tutor/groups/{group_id}/announce",
        headers=heads["owner"],
        json={"text": "Salom <b>", "to_chat": True, "to_students": True},
    )
    assert queued.status == 200 and (await queued.json())["queued"] == 2
    async with sessions() as session:
        jobs = (await session.execute(select(Job).where(Job.type == "tutor_notify"))).scalars()
        mine = [row for row in jobs if row.payload.get("owner_id") == owner_id]
        assert len(mine) == 2 and {row.payload["template"] for row in mine} == {"notify_text"}
    old = await http.post(
        f"/api/tutor/groups/{group_id}/announce",
        headers=heads["owner"],
        json={"chat_id": chat_id},
    )
    assert old.status == 400 and (await old.json())["error"] == "send"
    cleared = await http.put(
        f"/api/tutor/groups/{group_id}/chat", headers=heads["owner"], json={"chat_id": None}
    )
    assert cleared.status == 200 and (await cleared.json())["chat_id"] is None
