"""End-to-end bot payment flow through the real dispatcher, middlewares and Postgres.

Telegram is replaced by a recording session; nothing leaves the box."""

import os
from datetime import UTC, datetime
from itertools import count

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update
from aiogram.types import User as TgUser
from app.bot.middlewares import install_middlewares
from app.bot.routers import setup_routers
from app.config import Settings
from app.db.models.audit import AuditLog
from app.db.models.chats import Chat as ChatRow
from app.db.models.chats import ChatType
from app.db.models.payments import Payment, PaymentEvent
from app.db.models.subscriptions import Subscription
from app.db.models.users import User
from app.services.pending import PendingChatStore
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.pg import allow_purge

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, ADMIN = 9750000001, 9750000009
_IDS = (OWNER, ADMIN)
CHAT = -9750000001
CARD_A, CARD_B = "8600000000000001", "4000000000000002"  # placeholders, never real numbers

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


class Recorder(BaseSession):
    """Answers every Bot API call locally and keeps what was sent."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._ids = count(1000)

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - not used
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        returning = getattr(method, "__returning__", None)
        if (
            returning is Message
            or getattr(returning, "__args__", None)
            and Message in returning.__args__
        ):
            chat_id = getattr(method, "chat_id", OWNER)
            return Message(
                message_id=next(self._ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(chat_id), type="private"),
                text=getattr(method, "text", None) or getattr(method, "caption", None) or "",
            )
        return True

    def texts(self, chat_id: int) -> list[str]:
        out = []
        for call in self.calls:
            if int(getattr(call, "chat_id", 0) or 0) != chat_id:
                continue
            text = getattr(call, "text", None) or getattr(call, "caption", None)
            if text:
                out.append(text)
        return out

    def last_markup(self, chat_id: int):
        for call in reversed(self.calls):
            if int(getattr(call, "chat_id", 0) or 0) == chat_id and getattr(
                call, "reply_markup", None
            ):
                return call.reply_markup
        return None


async def _purge(s) -> None:
    await allow_purge(s)
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    pays = select(Payment.id).where(Payment.owner_id.in_(ids))
    await s.execute(delete(PaymentEvent).where(PaymentEvent.payment_id.in_(pays)))
    await s.execute(delete(AuditLog).where(AuditLog.actor_user_id.in_(ids)))
    await s.execute(delete(Payment).where(Payment.owner_id.in_(ids)))
    await s.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await s.execute(delete(ChatRow).where(ChatRow.owner_id.in_(ids)))
    await s.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def bot_world():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        await _purge(s)
        owner = User(telegram_id=OWNER, full_name="Flow Owner", language_code="uz")
        admin = User(telegram_id=ADMIN, full_name="Flow Admin", language_code="uz")
        s.add_all([owner, admin])
        await s.flush()
        s.add(
            ChatRow(
                telegram_chat_id=CHAT,
                type=ChatType.GROUP,
                title="Flow chat",
                owner_id=owner.id,
                added_at=datetime.now(UTC),
            )
        )
        await s.commit()
    settings = Settings(
        bot_token="1:flow-token",
        database_url=_URL,
        super_admin_ids=str(ADMIN),
        throttle_seconds=0,
        payment_card_number=CARD_A,
        payment_card_holder="Test Holder",
        payment_card_type="Uzcard",
        payment_card2_number=CARD_B,
        payment_card2_holder="Test Holder",
        payment_card2_type="Visa",
    )
    session = Recorder()
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp["pending"] = PendingChatStore(ttl_hours=1)
    install_middlewares(dp, settings, sessions)
    _release_module_routers()
    setup_routers(dp)
    seq = count(1)

    def user(tg: int) -> TgUser:
        return TgUser(id=tg, is_bot=False, first_name="Flow", language_code="uz")

    async def press(tg: int, data: str) -> None:
        msg = Message(
            message_id=500,
            date=datetime.now(UTC),
            chat=Chat(id=tg, type="private"),
            text="menu",
            from_user=user(tg),
        )
        cq = CallbackQuery(
            id=str(next(seq)), from_user=user(tg), chat_instance="ci", data=data, message=msg
        )
        await dp.feed_update(bot, Update(update_id=next(seq), callback_query=cq))

    async def say(tg: int, text: str | None = None, photo: str | None = None) -> None:
        kwargs = {"text": text} if text is not None else {}
        if photo:
            kwargs["photo"] = [
                PhotoSize(file_id=f"f-{photo}", file_unique_id=photo, width=600, height=900)
            ]
        msg = Message(
            message_id=next(seq) + 600,
            date=datetime.now(UTC),
            chat=Chat(id=tg, type="private"),
            from_user=user(tg),
            **kwargs,
        )
        await dp.feed_update(bot, Update(update_id=next(seq), message=msg))

    async def payment() -> Payment | None:
        async with sessions() as s:
            owner_id = select(User.id).where(User.telegram_id == OWNER).scalar_subquery()
            return (
                (
                    await s.execute(
                        select(Payment)
                        .where(Payment.owner_id == owner_id)
                        .order_by(Payment.id.desc())
                    )
                )
                .scalars()
                .first()
            )

    try:
        yield {"press": press, "say": say, "rec": session, "payment": payment, "sessions": sessions}
    finally:
        _detach(dp)
        async with sessions() as s:
            await _purge(s)
            await s.commit()
        await engine.dispose()


def _release_module_routers() -> None:
    """Another test may have attached the module-level routers to its own dispatcher."""
    import app.bot.routers as package
    from aiogram import Router

    for name in dir(package):
        router = getattr(getattr(package, name), "router", None)
        if isinstance(router, Router):
            router._parent_router = None


def _detach(router) -> None:
    """Routers are module singletons: release them so the next test can include them again."""
    for child in list(router.sub_routers):
        _detach(child)
        child._parent_router = None
    router.sub_routers.clear()


def _buttons(markup) -> list[str]:
    return [
        b.callback_data
        for row in (markup.inline_keyboard if markup else [])
        for b in row
        if b.callback_data
    ]


async def test_owner_pays_admin_rejects_owner_disputes_admin_approves(bot_world) -> None:
    press, say, rec, payment = (
        bot_world["press"],
        bot_world["say"],
        bot_world["rec"],
        bot_world["payment"],
    )
    await press(OWNER, "p:start:-")
    assert "p:plan:pro" in _buttons(rec.last_markup(OWNER))
    await press(OWNER, "p:plan:pro")
    await press(OWNER, "p:months:pro-1")
    assert any("7." in text for text in rec.texts(OWNER)), "terms screen with 7 points"
    assert await payment() is None, "nothing is created before the terms are accepted"
    await press(OWNER, "p:terms:pro-1")
    draft = await payment()
    assert draft.status == "draft" and draft.ref_code.startswith("RITM-")
    invoice = rec.texts(OWNER)[-1]
    assert (
        draft.ref_code in invoice
        and "8600 0000 0000 0001" in invoice
        and "4000 0000 0000 0002" in invoice
    )
    assert f"{draft.amount_uzs:,}".replace(",", " ") in invoice
    assert draft.terms_version and draft.terms_accepted_at is not None

    await press(OWNER, f"p:paid:{draft.id}")
    await say(OWNER, "12")
    assert "4" in rec.texts(OWNER)[-1]  # asks again for 4 digits
    await say(OWNER, "*5577")
    await press(OWNER, "p:now:-")
    await say(OWNER, "chek yo'q")  # text instead of a receipt
    assert (await payment()).status == "draft"
    await say(OWNER, photo="uniq-flow-1")
    sent = await payment()
    assert sent.status == "pending" and sent.payer_card_last4 == "5577"
    assert sent.receipt_unique_id == "uniq-flow-1" and sent.transfer_at is not None
    assert sent.ref_code in rec.texts(OWNER)[-1]
    assert any(sent.ref_code in text for text in rec.texts(ADMIN)), "admins got the alert"

    await press(ADMIN, f"ap:no:{sent.id}:-")
    assert (await payment()).status == "pending", "reject needs a reason first"
    await press(ADMIN, f"ap:rr:{sent.id}:no_money")
    rejected = await payment()
    assert rejected.status == "rejected" and rejected.reject_reason
    assert f"p:dispute:{sent.id}" in _buttons(rec.last_markup(OWNER))

    await press(OWNER, f"p:dispute:{sent.id}")
    await say(OWNER, "Pul 14:02 da yechildi, bank SMS bor")
    disputed = await payment()
    assert disputed.status == "disputed" and "SMS" in disputed.dispute_text
    assert any("SMS" in text for text in rec.texts(ADMIN))

    await press(ADMIN, f"ap:ok:{sent.id}:-")
    approved = await payment()
    assert approved.status == "approved"
    assert approved.ref_code in rec.texts(OWNER)[-1]
    async with bot_world["sessions"]() as s:
        actions = (
            (
                await s.execute(
                    select(PaymentEvent.action)
                    .where(PaymentEvent.payment_id == sent.id)
                    .order_by(PaymentEvent.id)
                )
            )
            .scalars()
            .all()
        )
    assert actions == ["created", "submitted", "rejected", "disputed", "approved"]


async def test_fake_receipt_twice_blocks_the_owner(bot_world) -> None:
    press, say, payment = bot_world["press"], bot_world["say"], bot_world["payment"]
    for round_ in (1, 2):
        await press(OWNER, "p:months:pro-1")
        await press(OWNER, "p:terms:pro-1")
        draft = await payment()
        await press(OWNER, f"p:paid:{draft.id}")
        await say(OWNER, "1234")
        await press(OWNER, "p:now:-")
        await say(OWNER, photo=f"fake-{round_}")
        await press(ADMIN, f"ap:fk:{draft.id}:-")
        await press(ADMIN, f"ap:fky:{draft.id}:-")
        assert (await payment()).is_fake is True
    async with bot_world["sessions"]() as s:
        owner = (await s.execute(select(User).where(User.telegram_id == OWNER))).scalar_one()
    assert owner.payments_blocked is True and owner.fake_receipts == 2
    before = (await payment()).id
    await press(OWNER, "p:terms:pro-1")
    assert (await payment()).id == before, "a blocked owner cannot open a new request"
