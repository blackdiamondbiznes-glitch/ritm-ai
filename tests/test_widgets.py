"""Private-chat widget HTML, fallbacks, and query handlers."""

from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerWidgetQuery, EditMessageWidgetData, SendWidget
from aiogram.types import Chat, Message, Update, WidgetQuery, WidgetQueryTypeData
from aiogram.types import User as TgUser
from app.bot.errors import install_errors
from app.bot.middlewares import install_middlewares
from app.bot.routers import setup_routers
from app.bot.widgets.pack import KINDS, RAW_LIMIT, ZLIB_LIMIT, sizes
from app.bot.widgets.send import clip_data, send_card
from app.config import Settings
from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.jobs import Job
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.models.widget_messages import WidgetMessage
from app.db.models.workspaces import Workspace
from app.db.repositories.widget_messages import WidgetMessageRepository
from app.services.clock import TASHKENT
from app.services.pending import PendingChatStore
from app.services.widget_cards import enroll_ref, lesson_data
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.notify_world import CHAT_TG, STUDENT, handler, open_db, require_postgres, service, world
from tests.test_payment_bot_flow import Recorder, _release_module_routers

TEACHER, PUPIL, STRANGER = 9771000001, 9771000002, 9771000003
_IDS = (TEACHER, PUPIL, STRANGER)
_URL = __import__("os").environ.get(
    "DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement"
)
_AT = datetime(2026, 11, 21, 18, 0, tzinfo=TASHKENT)
_NOW = datetime(2026, 11, 21, 17, 0, tzinfo=TASHKENT)


def test_every_widget_fits_telegram_limits() -> None:
    for kind in KINDS:
        raw, packed = sizes(kind)
        assert 1 <= raw <= RAW_LIMIT
        assert packed <= ZLIB_LIMIT


def test_clip_data_stays_within_1024_bytes() -> None:
    payload = clip_data(
        lesson_data("uz", "G" * 80, "W" * 80, datetime.now(UTC), "H" * 500, "2026-12-01")
    )
    assert len(payload.encode("utf-8")) <= 1024
    assert enroll_ref(12, 34) == (12 << 32) | 34


def test_allowed_updates_include_widget_query() -> None:
    dp = Dispatcher()
    setup_routers(dp)
    assert "widget_query" in dp.resolve_used_update_types()


@pytest.mark.asyncio
async def test_send_card_falls_back_when_send_widget_fails() -> None:
    class _Bot:
        def __init__(self) -> None:
            self.texts: list[str] = []

        async def send_widget(self, **_kw):
            raise TelegramBadRequest(method=SendWidget(chat_id=1, html="<p>x</p>"), message="bad")

        async def send_message(self, chat_id, text, **_kw):
            self.texts.append(text)
            return Message(
                message_id=1,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="private"),
                text=text,
            )

    bot = _Bot()
    message = await send_card(
        bot, chat_id=10, kind="digest", data={"l": "uz", "soon": 1, "late": 0}, caption="fallback"
    )
    assert bot.texts == ["fallback"]
    assert message is not None and message.message_id == 1


class _WidgetBot:
    def __init__(self) -> None:
        self.widgets: list[dict] = []
        self.messages: list[tuple[int, str]] = []
        self._ids = count(3000)

    async def send_widget(self, **kwargs):
        self.widgets.append(kwargs)
        return Message(
            message_id=next(self._ids),
            date=datetime.now(UTC),
            chat=Chat(id=int(kwargs["chat_id"]), type="private"),
            caption=kwargs.get("caption") or "",
        )

    async def send_message(self, chat_id: int, text: str, **_kw):
        self.messages.append((chat_id, text))
        return Message(
            message_id=next(self._ids),
            date=datetime.now(UTC),
            chat=Chat(id=chat_id, type="private"),
            text=text,
        )


@pytest.fixture
async def db():
    async for factory in open_db():
        yield factory


@pytest.mark.asyncio
async def test_student_notice_is_a_widget_and_the_group_stays_text(db) -> None:
    bot = _WidgetBot()
    async with db() as session:
        await world(session, _NOW, start=_AT)
        await service(session, _NOW).enqueue_due(_NOW)
        rows = (
            (await session.execute(select(Job).where(Job.type == "tutor_notify"))).scalars().all()
        )
        worker = handler(session, bot, _NOW)
        for row in rows:
            await worker.handle(row)
        await session.commit()
    student = [item for item in bot.widgets if item["chat_id"] == STUDENT]
    group = [item for item in bot.messages if item[0] == CHAT_TG]
    assert len(student) == 1
    assert "html" in student[0] and student[0]["allow_queries"] is True
    assert len(group) == 1
    assert not any(item["chat_id"] == CHAT_TG for item in bot.widgets)


async def _purge(session) -> None:
    owners = select(User.id).where(User.telegram_id.in_(_IDS))
    await session.execute(delete(WidgetMessage).where(WidgetMessage.telegram_id.in_(_IDS)))
    await session.execute(
        delete(TutorAttendance).where(
            TutorAttendance.lesson_id.in_(
                select(TutorLesson.id).where(TutorLesson.owner_id.in_(owners))
            )
        )
    )
    await session.execute(
        delete(TutorGroupMember).where(
            TutorGroupMember.group_id.in_(
                select(TutorGroup.id).where(TutorGroup.owner_id.in_(owners))
            )
        )
    )
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(owners)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(owners)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(owners)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(owners)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def query_world():
    require_postgres()
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    started = datetime.now(UTC) - timedelta(hours=1)
    async with sessions() as session:
        await _purge(session)
        teacher = User(telegram_id=TEACHER, full_name="Adham", language_code="uz")
        pupil_user = User(telegram_id=PUPIL, full_name="Vali", language_code="uz")
        stranger = User(telegram_id=STRANGER, full_name="Kim", language_code="uz")
        session.add_all([teacher, pupil_user, stranger])
        await session.flush()
        space = Workspace(owner_id=teacher.id, vertical="tutor", name="Kabinet")
        session.add(space)
        await session.flush()
        group = TutorGroup(
            owner_id=teacher.id,
            workspace_id=space.id,
            name="B1",
            weekdays="1",
            start_min=600,
            end_min=690,
            enroll_code="w1dgetcode1",
        )
        session.add(group)
        await session.flush()
        pupil = TutorStudent(
            owner_id=teacher.id,
            workspace_id=space.id,
            name="Vali",
            status="paid",
            amount_uzs=0,
            telegram_id=PUPIL,
            join_code="wjoinvali01",
        )
        session.add(pupil)
        await session.flush()
        session.add(TutorGroupMember(group_id=group.id, student_id=pupil.id, status="active"))
        lesson = TutorLesson(
            owner_id=teacher.id,
            workspace_id=space.id,
            group_id=group.id,
            title="Dars",
            status="scheduled",
            source="manual",
            starts_at=started,
            ends_at=started + timedelta(minutes=90),
        )
        session.add(lesson)
        await session.flush()
        repo = WidgetMessageRepository(session)
        await repo.remember("attendance", lesson.id, TEACHER, 555)
        await repo.remember("attendance", lesson.id, STRANGER, 556)
        await session.commit()
        ids = {"lesson": lesson.id, "student": pupil.id}
    settings = Settings(bot_token="1:widget-token", database_url=_URL, throttle_seconds=0)
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

    async def tap(tg: int, data: str, message_id: int = 555) -> None:
        query = WidgetQuery(
            id=str(next(seq)),
            from_user=TgUser(id=tg, is_bot=False, first_name="Tap"),
            chat_instance="inst",
            type=WidgetQueryTypeData(type="data"),
            data=data,
            chat=Chat(id=tg, type="private"),
            message_id=message_id,
        )
        await dp.feed_update(bot, Update(update_id=next(seq), widget_query=query))

    yield {"tap": tap, "rec": rec, "ids": ids, "sessions": sessions}
    async with sessions() as session:
        await _purge(session)
        await session.commit()
    await bot.session.close()


@pytest.mark.asyncio
async def test_teacher_can_mark_attendance_from_the_widget(query_world) -> None:
    ids = query_world["ids"]
    await query_world["tap"](TEACHER, f"p:{ids['student']}")
    answers = [call for call in query_world["rec"].calls if isinstance(call, AnswerWidgetQuery)]
    edits = [call for call in query_world["rec"].calls if isinstance(call, EditMessageWidgetData)]
    assert answers and answers[-1].data is None
    assert edits and '"done":1' in (edits[-1].chat_data or "")
    async with query_world["sessions"]() as session:
        row = (
            await session.execute(
                select(TutorAttendance).where(
                    TutorAttendance.lesson_id == ids["lesson"],
                    TutorAttendance.student_id == ids["student"],
                )
            )
        ).scalar_one()
        assert row.status == "present"


@pytest.mark.asyncio
async def test_stranger_widget_tap_is_answered_and_rejected(query_world) -> None:
    ids = query_world["ids"]
    await query_world["tap"](STRANGER, f"p:{ids['student']}", message_id=556)
    answers = [call for call in query_world["rec"].calls if isinstance(call, AnswerWidgetQuery)]
    edits = [call for call in query_world["rec"].calls if isinstance(call, EditMessageWidgetData)]
    assert answers and answers[0].data == "missing"
    assert not edits
    async with query_world["sessions"]() as session:
        found = (
            (
                await session.execute(
                    select(TutorAttendance).where(TutorAttendance.lesson_id == ids["lesson"])
                )
            )
            .scalars()
            .all()
        )
        assert found == []
