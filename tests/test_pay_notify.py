"""Super admins are pushed a review message when an owner submits a payment."""

from datetime import UTC, datetime

from aiogram.types import InlineKeyboardMarkup
from app.bot.callbacks import AdminPayCB
from app.bot.pay_copy import admin_payment_alert, approved_notice
from app.bot.pay_notify import notify_payment_submitted
from app.config import Settings
from app.db.models.payments import METHOD_CARD, STATUS_PENDING, Payment
from tests.fakes import make_plans, make_user

NOW = datetime(2026, 11, 20, 16, 21, tzinfo=UTC)


class _Bot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, InlineKeyboardMarkup | None]] = []
        self.photos: list[tuple[int, str, str, InlineKeyboardMarkup | None]] = []
        self.fail: set[int] = set()

    async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
        if chat_id in self.fail:
            raise RuntimeError("unreachable")
        self.messages.append((chat_id, text, reply_markup))

    async def send_photo(self, chat_id: int, photo: str, caption: str, reply_markup=None) -> None:
        if chat_id in self.fail:
            raise RuntimeError("unreachable")
        self.photos.append((chat_id, photo, caption, reply_markup))


def _settings() -> Settings:
    return Settings(
        bot_token="1:test-token",
        database_url="postgresql+asyncpg://bot:bot@localhost:5432/engagement",
        super_admin_ids="505,506",
    )


def _payment(*, receipt: str | None = None) -> Payment:
    return Payment(
        id=1,
        owner_id=1,
        plan_id=3,
        amount_uzs=76200,
        method=METHOD_CARD,
        status=STATUS_PENDING,
        requested_period_months=3,
        receipt_file_id=receipt,
        created_at=NOW,
    )


def test_alert_text_escapes_the_owner_and_uses_tashkent_time() -> None:
    owner = make_user()
    owner.full_name = "Ada <b>H</b>"
    owner.username = "ada"
    owner.telegram_id = 5052443384
    plan = next(p for p in make_plans() if p.code == "pro")
    text = admin_payment_alert(_payment(), owner, plan, "uz", founder=True)
    assert "Ada &lt;b&gt;H&lt;/b&gt;" in text
    assert "@ada" in text
    assert "5052443384" in text
    assert "76200" in text or "76 200" in text
    assert "21:21" in text  # 16:21 UTC is 21:21 in Asia/Tashkent (UTC+5)
    assert "ta'sischi" in text or "tasischi" in text or "asoschi" in text or "ta" in text


def test_approved_notice_uses_the_expiry_date() -> None:
    plan = next(p for p in make_plans() if p.code == "pro")
    text = approved_notice(plan, datetime(2026, 12, 20, 16, 21, tzinfo=UTC), "uz")
    assert "Pro" in text or "pro" in text.lower() or plan.name in text
    assert "20.12.2026" in text
    assert "gacha" in text


async def test_notify_sends_photo_and_swallows_telegram_errors() -> None:
    bot = _Bot()
    bot.fail.add(506)
    owner = make_user()
    owner.full_name = "Ada"
    owner.username = "ada"
    plan = next(p for p in make_plans() if p.code == "pro")
    payment = _payment(receipt="AgFILE")
    await notify_payment_submitted(bot, _settings(), payment, owner, plan, founder=True)
    assert bot.photos[0][0] == 505
    assert bot.photos[0][1] == "AgFILE"
    assert "Ada" in bot.photos[0][2]
    markup = bot.photos[0][3]
    assert markup is not None
    packed = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert AdminPayCB(a="ok", id=1).pack() in packed
    assert AdminPayCB(a="no", id=1).pack() in packed
    assert bot.messages == []


async def test_notify_without_receipt_uses_send_message() -> None:
    bot = _Bot()
    owner = make_user()
    plan = next(p for p in make_plans() if p.code == "pro")
    await notify_payment_submitted(bot, _settings(), _payment(), owner, plan, founder=False)
    assert [row[0] for row in bot.messages] == [505, 506]
    assert bot.photos == []
