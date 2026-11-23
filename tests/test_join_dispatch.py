"""/start join_ and enroll_ through the real dispatcher, middlewares and Postgres.

A personal link from a second account must always get an answer."""

from datetime import UTC, datetime
from itertools import count

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Chat,
    ChatMemberBanned,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    MessageEntity,
    Update,
)
from aiogram.types import User as TgUser
from app.bot.errors import install_errors
from app.bot.middlewares import install_middlewares
from app.bot.routers import setup_routers
from app.config import Settings
from app.db.models.groups import TutorGroup
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.i18n import t
from app.services.pending import PendingChatStore
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.test_payment_bot_flow import _URL, Recorder, _detach, _release_module_routers

TEACHER, NEWBIE, KNOWN = 9760000001, 9760000002, 9760000003
_IDS = (TEACHER, NEWBIE, KNOWN)
CODE, ENROLL = "a1b2c3d4e5", "f6e5d4c3b2"

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(s) -> None:
    owners = select(User.id).where(User.telegram_id.in_(_IDS))
    await s.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(owners)))
    await s.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(owners)))
    await s.execute(delete(Workspace).where(Workspace.owner_id.in_(owners)))
    await s.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def world():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        await _purge(s)
        teacher = User(telegram_id=TEACHER, full_name="Teacher", language_code="uz")
        known = User(telegram_id=KNOWN, full_name="Known", language_code="uz", ui_language_set=True)
        s.add_all([teacher, known])
        await s.flush()
        space = Workspace(owner_id=teacher.id, vertical="tutor", name="Kabinet")
        s.add(space)
        await s.flush()
        s.add(
            TutorStudent(
                owner_id=teacher.id,
                workspace_id=space.id,
                name="TEST Vali",
                status="paid",
                amount_uzs=0,
                join_code=CODE,
            )
        )
        s.add(
            TutorGroup(
                owner_id=teacher.id,
                workspace_id=space.id,
                name="B1",
                weekdays="1,3,5",
                start_min=600,
                end_min=690,
                enroll_code=ENROLL,
            )
        )
        await s.commit()
    settings = Settings(bot_token="1:join-token", database_url=_URL, throttle_seconds=5)
    rec = Recorder()
    bot = Bot(
        settings.bot_token, session=rec, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp["pending"] = PendingChatStore(ttl_hours=1)
    install_middlewares(dp, settings, sessions)
    _release_module_routers()
    setup_routers(dp)
    install_errors(dp)
    seq = count(1)

    async def start(tg: int, payload: str) -> None:
        text = f"/start {payload}".strip()
        msg = Message(
            message_id=next(seq),
            date=datetime.now(UTC),
            chat=Chat(id=tg, type="private"),
            from_user=TgUser(id=tg, is_bot=False, first_name="Second", language_code="uz"),
            text=text,
            entities=[MessageEntity(type="bot_command", offset=0, length=6)],
        )
        await dp.feed_update(bot, Update(update_id=next(seq), message=msg))

    async def member(tg: int) -> None:
        who = TgUser(id=tg, is_bot=False, first_name="Second")
        me = TgUser(id=1, is_bot=True, first_name="Ritm")
        event = ChatMemberUpdated(
            chat=Chat(id=tg, type="private"),
            from_user=who,
            date=datetime.now(UTC),
            old_chat_member=ChatMemberBanned(user=me, until_date=0),
            new_chat_member=ChatMemberMember(user=me),
        )
        await dp.feed_update(bot, Update(update_id=next(seq), my_chat_member=event))

    try:
        yield {"member": member, "start": start, "rec": rec, "sessions": sessions}
    finally:
        _detach(dp)
        async with sessions() as s:
            await _purge(s)
            await s.commit()
        await engine.dispose()


async def test_new_account_claims_a_personal_link(world) -> None:
    await world["start"](NEWBIE, f"join_{CODE}")
    assert world["rec"].texts(NEWBIE) == [t("join_ok", "uz")]
    async with world["sessions"]() as s:
        row = (
            await s.execute(select(TutorStudent).where(TutorStudent.join_code == CODE))
        ).scalar_one()
        assert row.telegram_id == NEWBIE


async def test_returning_account_claims_and_repeats_get_answers(world) -> None:
    await world["start"](KNOWN, f"join_{CODE}")
    await world["start"](KNOWN, f"join_{CODE}")
    await world["start"](NEWBIE, f"join_{CODE}")
    assert world["rec"].texts(KNOWN) == [t("join_ok", "uz"), t("join_ok", "uz")]
    assert world["rec"].texts(NEWBIE) == [t("join_taken", "uz")]


async def test_every_payload_answers(world) -> None:
    await world["start"](KNOWN, "join_zzzzzz9999")
    await world["start"](TEACHER, f"join_{CODE}")
    await world["start"](KNOWN, "join_bad!")
    await world["start"](NEWBIE, f"enroll_{ENROLL}")
    await world["start"](NEWBIE, "enroll_zzzzzz9999")
    assert world["rec"].texts(KNOWN) == [t("join_missing", "uz"), t("join_missing", "uz")]
    teacher = world["rec"].texts(TEACHER)
    assert teacher[0] == t("join_own", "uz")
    assert "B1" in teacher[1]  # the new group request reaches the teacher
    assert world["rec"].texts(NEWBIE) == [t("enroll_pending", "uz"), t("enroll_missing", "uz")]


async def test_start_right_after_my_chat_member_is_answered(world) -> None:
    await world["member"](NEWBIE)
    await world["start"](NEWBIE, f"join_{CODE}")
    assert world["rec"].texts(NEWBIE) == [t("join_ok", "uz")]


async def test_throttle_runs_once_per_update_even_when_handlers_skip(world) -> None:
    from aiogram import Router
    from aiogram.dispatcher.event.bases import SkipHandler

    settings = Settings(bot_token="1:join-token", database_url=_URL, throttle_seconds=5)
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    install_middlewares(dp, settings, world["sessions"])
    seen: list[str] = []
    router = Router(name="skip-chain")

    @router.message()
    async def first(message: Message) -> None:
        seen.append("first")
        raise SkipHandler()

    @router.message()
    async def second(message: Message) -> None:
        seen.append("second")

    dp.include_router(router)
    msg = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=KNOWN, type="private"),
        from_user=TgUser(id=KNOWN, is_bot=False, first_name="Known"),
        text="salom",
    )
    await dp.feed_update(Bot("1:join-token", session=Recorder()), Update(update_id=1, message=msg))
    assert seen == ["first", "second"]
