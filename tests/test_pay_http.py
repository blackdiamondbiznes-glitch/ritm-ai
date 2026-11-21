"""In-app payment: the Mini App drives the same PaymentService as the bot
(quote -> offer -> draft -> receipt upload -> admin queue)."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendPhoto
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.audit import AuditLog
from app.db.models.payments import Payment, PaymentEvent
from app.db.models.subscriptions import Subscription
from app.db.models.users import User
from app.services.clock import TASHKENT
from app.webapp.admins import ChatAdminCache
from app.webapp.auth import issue_session, session_secret
from app.webapp.members import MemberCountCache
from app.webapp.pay_routes import parse_when
from app.webapp.rate_limit import RateLimiter
from app.webapp.receipts import sniff
from app.webapp.server import create_app
from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.pg import allow_purge

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
SUPER, OWNER, OTHER, BLOCKED = 9870000001, 9870000002, 9870000003, 9870000004
_IDS = (SUPER, OWNER, OTHER, BLOCKED)
JPEG = b"\xff\xd8\xff\xe0" + b"receipt-bytes" * 50
PNG = b"\x89PNG\r\n\x1a\n" + b"other" * 40

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(s) -> None:
    await allow_purge(s)
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    pays = select(Payment.id).where(Payment.owner_id.in_(ids))
    await s.execute(delete(PaymentEvent).where(PaymentEvent.payment_id.in_(pays)))
    await s.execute(
        delete(AuditLog).where(
            or_(
                AuditLog.actor_user_id.in_(ids),
                (AuditLog.entity == "user")
                & AuditLog.entity_id.in_(
                    select(text("CAST(id AS TEXT)"))
                    .select_from(User)
                    .where(User.telegram_id.in_(_IDS))
                ),
            )
        )
    )
    await s.execute(delete(Payment).where(Payment.owner_id.in_(ids)))
    await s.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await s.execute(delete(User).where(User.telegram_id.in_(_IDS)))


class _Bot:
    """Records sends. send_photo returns a message with a photo, like Telegram."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, int, object]] = []
        self.forbid: set[int] = set()
        self.bad_photo = False

    def _msg(self, kind: str, chat_id: int, file):
        if chat_id in self.forbid:
            raise TelegramForbiddenError(
                method=SendPhoto(chat_id=chat_id, photo="x"), message="blocked"
            )
        self.sent.append((kind, chat_id, file))
        fid = file if isinstance(file, str) else f"tg-{kind}-{len(self.sent)}"
        item = SimpleNamespace(file_id=fid, file_unique_id=f"u-{len(self.sent)}")
        if kind == "photo":
            return SimpleNamespace(photo=[item], document=None)
        return SimpleNamespace(photo=None, document=item)

    async def send_photo(self, chat_id, photo, **_kw):
        if self.bad_photo and not isinstance(photo, str):
            raise TelegramBadRequest(method=SendPhoto(chat_id=chat_id, photo="x"), message="dims")
        return self._msg("photo", chat_id, photo)

    async def send_document(self, chat_id, document, **_kw):
        return self._msg("document", chat_id, document)

    async def send_message(self, chat_id, text, **_kw):
        self.sent.append(("message", chat_id, text))


@pytest.fixture
async def world():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        await _purge(s)
        rows = [User(telegram_id=tg, full_name=f"P{tg % 10}", language_code="uz") for tg in _IDS]
        rows[3].payments_blocked = True
        s.add_all(rows)
        await s.commit()
    settings = Settings(
        bot_token="1:test-token",
        database_url=_URL,
        super_admin_ids=str(SUPER),
        payment_card_number="8600111122223333",
        payment_card_holder="Adham Hoshimov",
        payment_card_type="Uzcard",
        payment_card2_number="4111111111111111",
        payment_card2_holder="Adham Hoshimov",
        payment_card2_type="Visa",
        founder_slots=0,
    )
    bot = _Bot()

    async def no_count(_chat_id: int) -> int:
        raise OSError("offline")

    async def no_admins(_chat_id: int):
        return []

    app = create_app(
        settings,
        sessions,
        limiter=RateLimiter(limit=10000),
        bot=bot,
        members=MemberCountCache(fetch=no_count),
        admins=ChatAdminCache(fetch=no_admins),
    )
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {tg: {"Authorization": f"Bearer {issue_session(tg, secret, 600)}"} for tg in _IDS}
    try:
        async with TestClient(TestServer(app)) as client:
            yield {"c": client, "h": heads, "bot": bot, "sessions": sessions, "app": app}
    finally:
        async with sessions() as s:
            await _purge(s)
            await s.commit()
        await engine.dispose()


async def _start(w, tg=OWNER, plan="pro", months=1, accept=True):
    body = {"plan": plan, "months": months, "accept": accept, "terms_version": "2026-11-v1"}
    return await w["c"].post("/api/pay/start", json=body, headers=w["h"][tg])


def _form(pid, data=JPEG, last4="4321", when=None, name="chek.jpg"):
    form = FormData()
    form.add_field("payment_id", str(pid))
    form.add_field("last4", last4)
    stamp = when or (datetime.now(UTC) - timedelta(minutes=5)).astimezone(TASHKENT)
    form.add_field("when", stamp.strftime("%Y-%m-%dT%H:%M"))
    form.add_field("receipt", data, filename=name, content_type="image/jpeg")
    return form


async def _submit(w, pid, tg=OWNER, **kw):
    return await w["c"].post("/api/pay/submit", data=_form(pid, **kw), headers=w["h"][tg])


async def test_options_price_every_plan_and_period_like_the_bot(world) -> None:
    c, h = world["c"], world["h"]
    assert (await c.get("/api/pay/options")).status == 401
    data = await (await c.get("/api/pay/options", headers=h[OWNER])).json()
    by_code = {p["code"]: p for p in data["plans"]}
    assert set(by_code) == {"start", "pro", "agency"}
    pro = {p["months"]: p for p in by_code["pro"]["periods"]}
    assert pro[1]["amount"] == 39_000 and pro[1]["percent"] == 0
    assert pro[3]["percent"] == 7 and pro[3]["amount"] == 108_800  # 117 000 -7%, nearest 100
    assert pro[12]["percent"] == 15 and pro[12]["amount"] == 397_800  # 468 000 -15%
    assert by_code["start"]["monthly"] == 29_000 and by_code["agency"]["monthly"] == 69_000
    assert [card["number"] for card in data["cards"]] == [
        "8600 1111 2222 3333",
        "4111 1111 1111 1111",
    ]
    assert data["invoice"] is None and data["pending"] is None


async def test_start_needs_the_accepted_offer_and_reuses_the_draft(world) -> None:
    assert (await _start(world, accept=False)).status == 400
    first = await (await _start(world, months=3)).json()
    inv = first["invoice"]
    assert inv["ref"].startswith("RITM-") and inv["months"] == 3
    assert 108_800 <= inv["amount_uzs"] <= 108_800 + 99  # unique offset, like the bot
    again = await (await _start(world, months=3)).json()
    assert again["invoice"]["ref"] == inv["ref"]
    blocked = await _start(world, tg=BLOCKED)
    assert blocked.status == 403 and (await blocked.json())["error"] == "blocked"


async def test_submit_uploads_receipt_and_reaches_admins(world) -> None:
    w = world
    inv = (await (await _start(w)).json())["invoice"]
    bad = await _submit(w, inv["id"], data=b"GIF89a-not-allowed")
    assert bad.status == 415
    assert (await _submit(w, inv["id"], last4="12")).status == 400
    assert (
        await _submit(w, inv["id"], when=datetime.now(TASHKENT) - timedelta(days=9))
    ).status == 400
    big = JPEG + b"0" * (10 * 1024 * 1024)
    assert (await _submit(w, inv["id"], data=big)).status == 413
    assert w["bot"].sent == []  # nothing reached Telegram before the checks passed
    ok = await _submit(w, inv["id"])
    assert ok.status == 200, await ok.text()
    body = await ok.json()
    assert body["pending"]["status"] == "pending" and body["invoice"] is None
    assert body["submitted"]["ref"] == inv["ref"]
    kinds = [(kind, chat) for kind, chat, _f in w["bot"].sent]
    assert kinds[0] == ("photo", OWNER)  # copy in the owner's chat gives the file_id
    assert ("photo", SUPER) in kinds  # admin alert with the same receipt
    admin_file = next(f for kind, chat, f in w["bot"].sent if chat == SUPER and kind == "photo")
    async with w["sessions"]() as s:
        row = await s.get(Payment, inv["id"])
        assert row.status == "pending" and row.receipt_file_id == admin_file == "tg-photo-1"
        assert row.receipt_unique_id.startswith("sha256:") and row.payer_card_last4 == "4321"
        events = (
            await s.execute(select(PaymentEvent).where(PaymentEvent.payment_id == row.id))
        ).scalars()
        assert any(e.action == "submitted" and e.data.get("via") == "webapp" for e in events)
    again = await _submit(w, inv["id"])
    assert again.status == 409
    dup = await _start(w)
    assert dup.status == 409 and (await dup.json())["error"] == "duplicate"


async def test_same_file_from_another_owner_is_flagged(world) -> None:
    w = world
    first = (await (await _start(w)).json())["invoice"]
    assert (await _submit(w, first["id"])).status == 200
    second = (await (await _start(w, tg=OTHER, plan="start")).json())["invoice"]
    assert (await _submit(w, second["id"], tg=OTHER)).status == 200
    async with w["sessions"]() as s:
        row = await s.get(Payment, second["id"])
        assert row.duplicate_of_id == first["id"]
    third = await (await _start(w, tg=OWNER)).json()
    assert third.get("error") == "duplicate"


async def test_owner_without_bot_chat_keeps_the_draft(world) -> None:
    w = world
    inv = (await (await _start(w)).json())["invoice"]
    w["bot"].forbid.add(OWNER)
    res = await _submit(w, inv["id"])
    assert res.status == 409 and (await res.json())["error"] == "start_bot"
    async with w["sessions"]() as s:
        assert (await s.get(Payment, inv["id"])).status == "draft"


async def test_odd_photo_falls_back_to_document_and_cancel_works(world) -> None:
    w = world
    inv = (await (await _start(w)).json())["invoice"]
    w["bot"].bad_photo = True
    assert (await _submit(w, inv["id"], data=PNG, name="c.png")).status == 200
    async with w["sessions"]() as s:
        assert (await s.get(Payment, inv["id"])).receipt_kind == "document"
    res = await w["c"].post("/api/pay/cancel", headers=w["h"][OWNER])
    data = await res.json()
    assert data["pending"] is None and data["invoice"] is None


def test_sniff_and_when() -> None:
    assert sniff(JPEG) == ("jpg", "photo")
    assert sniff(PNG) == ("png", "photo")
    assert sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ("webp", "photo")
    assert sniff(b"%PDF-1.7") == ("pdf", "document")
    assert sniff(b"<svg>") is None
    now = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
    assert parse_when("now", now) == now
    assert parse_when("2026-11-21T08:00", now) == datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
    assert parse_when("21.11 08:00", now) is None
