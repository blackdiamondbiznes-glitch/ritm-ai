"""A link enrollment waits for the teacher and does not duplicate the card."""

import os

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.bot.enroll_notice import teacher_notifier
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.users import UserRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.enrollment import PENDING_CAP, EnrollmentService
from app.services.workspaces import WorkspaceService
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, OTHER, PUPIL = 9860000001, 9860000002, 9860000003
_IDS = (OWNER, OTHER, PUPIL)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


class _Bot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_kwargs: object) -> None:
        self.sent.append((chat_id, text))

    async def get_chat_member_count(self, chat_id: int) -> int:
        return 0

    async def get_chat_administrators(self, chat_id: int) -> list:
        return []


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    group_ids = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(group_ids)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    bot = _Bot()
    async with sessions() as session:
        await _purge(session)
        session.add_all(
            [
                User(telegram_id=OWNER, full_name="Owner", language_code="uz"),
                User(telegram_id=OTHER, full_name="Other", language_code="uz"),
                User(telegram_id=PUPIL, full_name="Vali <b>", language_code="uz"),
            ]
        )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000), bot=bot)
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        "owner": {"Authorization": f"Bearer {issue_session(OWNER, secret, 600)}"},
        "pupil": {"Authorization": f"Bearer {issue_session(PUPIL, secret, 600)}"},
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions, bot
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


def _svc(session) -> EnrollmentService:
    users = UserRepository(session)
    return EnrollmentService(
        GroupRepository(session),
        StudentRepository(session),
        users,
        WorkspaceService(WorkspaceRepository(session), users),
        None,
    )


async def _group(http, heads) -> int:
    created = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "Ingliz", "weekdays": [1, 3], "start": "08:00", "end": "09:00"},
    )
    assert created.status == 200
    return (await created.json())["created_id"]


async def test_request_stays_hidden_until_the_teacher_approves(client) -> None:
    http, heads, sessions, bot = client
    group_id = await _group(http, heads)
    async with sessions() as session:
        group = await session.get(TutorGroup, group_id)
        assert group is not None
        service = _svc(session)
        notes: list[tuple[str, str]] = []

        async def notify(owner, name, group_name, *_args):
            notes.append((name, group_name))
            await teacher_notifier(bot)(owner, name, group_name)

        first = await service.enroll(group.enroll_code, PUPIL, "Vali <b>", notify=notify)
        second = await service.enroll(group.enroll_code, PUPIL, "Vali <b>", notify=notify)
        assert first == "pending"
        assert second == "already"
        cards = (
            await session.execute(
                select(func.count())
                .select_from(TutorStudent)
                .where(
                    TutorStudent.owner_id == group.owner_id,
                    TutorStudent.telegram_id == PUPIL,
                )
            )
        ).scalar_one()
        assert cards == 1
        await session.commit()
    assert len(notes) == 1
    assert bot.sent and "&lt;b&gt;" in bot.sent[0][1]
    hidden = await http.get(f"/api/tutor/groups/{group_id}", headers=heads["owner"])
    assert (await hidden.json())["members"] == []
    listed = await http.get("/api/tutor/students", headers=heads["owner"])
    assert (await listed.json())["students"] == []
    waiting = await http.get("/api/tutor/requests", headers=heads["owner"])
    body = await waiting.json()
    assert body["requests"][0]["name"] == "Vali <b>"
    assert body["requests"][0]["group_id"] == group_id
    empty = await http.get("/api/me/boards", headers=heads["pupil"])
    assert (await empty.json())["boards"] == []
    student_id = body["requests"][0]["student_id"]
    approved = await http.post(
        f"/api/tutor/requests/{group_id}/{student_id}/approve",
        headers=heads["owner"],
        json={},
    )
    assert approved.status == 200
    opened = await http.get(f"/api/tutor/groups/{group_id}", headers=heads["owner"])
    assert [item["name"] for item in (await opened.json())["members"]] == ["Vali <b>"]
    pupils = await http.get("/api/tutor/students", headers=heads["owner"])
    assert (await pupils.json())["students"][0]["status"] == "debtor"
    assert any(chat_id == PUPIL and "Ingliz" in text for chat_id, text in bot.sent)
    shown = await http.get("/api/me/boards", headers=heads["pupil"])
    assert (await shown.json())["boards"][0]["name"] == "Ingliz"


async def test_reject_removes_a_card_that_had_nothing_else(client) -> None:
    http, heads, sessions, bot = client
    group_id = await _group(http, heads)
    async with sessions() as session:
        group = await session.get(TutorGroup, group_id)
        assert group is not None
        assert await _svc(session).enroll(group.enroll_code, PUPIL, "Vali") == "pending"
        await session.commit()
    waiting = await http.get("/api/tutor/requests", headers=heads["owner"])
    student_id = (await waiting.json())["requests"][0]["student_id"]
    rejected = await http.post(
        f"/api/tutor/requests/{group_id}/{student_id}/reject",
        headers=heads["owner"],
        json={},
    )
    assert rejected.status == 200
    assert (await rejected.json())["requests"] == []
    listed = await http.get("/api/tutor/students", headers=heads["owner"])
    assert (await listed.json())["students"] == []
    assert any(chat_id == PUPIL for chat_id, _text in bot.sent)


async def test_fifty_pending_requests_block_the_next_one(client) -> None:
    _http, _heads, sessions, _bot = client
    async with sessions() as session:
        owner = (await session.execute(select(User).where(User.telegram_id == OWNER))).scalar_one()
        space = await WorkspaceService(
            WorkspaceRepository(session), UserRepository(session)
        ).ensure(owner)
        group = TutorGroup(
            owner_id=owner.id,
            workspace_id=space.id,
            name="Tola",
            weekdays="1",
            start_min=480,
            end_min=540,
            enroll_code="busycode01",
        )
        session.add(group)
        await session.flush()
        service = _svc(session)
        for index in range(PENDING_CAP):
            result = await service.enroll(group.enroll_code, 9861000000 + index, "Oquvchi")
            assert result == "pending"
        assert await service.enroll(group.enroll_code, 9861999999, "Yana") == "busy"
        await session.rollback()
