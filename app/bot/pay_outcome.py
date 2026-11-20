"""Messages after a payment decision. Bot buttons and the Mini App both call these,
so the owner and the admins see the same thing whichever screen made the decision."""

from __future__ import annotations

import logging

from aiogram import Bot

from app.bot.keyboards.admin_payments import payment_review
from app.bot.keyboards.payments import dispute_actions
from app.bot.notify import notify_user
from app.bot.pay_copy import approved_notice, dispute_alert, fake_notice, rejected_notice
from app.config import Settings
from app.db.models.payments import Payment
from app.db.models.plans import Plan
from app.db.models.users import User
from app.services.payments import FakeMarked, PaymentService

logger = logging.getLogger(__name__)


async def announce_approved(
    bot: Bot | None,
    payments: PaymentService,
    payment: Payment,
    owner: User | None,
    plan: Plan | None,
) -> bool:
    if bot is None or owner is None or plan is None:
        return False
    until = await payments.owner_expiry(owner.id)
    lang = owner.language_code or "uz"
    return await notify_user(bot, owner.telegram_id, approved_notice(plan, until, lang, payment))


async def announce_rejected(bot: Bot | None, payment: Payment, owner: User | None) -> bool:
    if bot is None or owner is None:
        return False
    lang = owner.language_code or "uz"
    markup = None if payment.disputed_at is not None else dispute_actions(lang, payment.id)
    text = rejected_notice(payment.reject_reason or "", lang, payment)
    return await notify_user(bot, owner.telegram_id, text, markup)


async def announce_fake(bot: Bot | None, marked: FakeMarked) -> bool:
    if bot is None:
        return False
    lang = marked.owner.language_code or "uz"
    text = fake_notice(marked.payment, lang, blocked=marked.blocked)
    return await notify_user(bot, marked.owner.telegram_id, text)


async def announce_dispute(
    bot: Bot | None, settings: Settings, payment: Payment, owner: User | None, events: list
) -> None:
    """Re-open the case for every super admin, with the full history and the receipt."""
    if bot is None:
        return
    for telegram_id in settings.admin_ids:
        text = dispute_alert(payment, owner, "uz", events)
        markup = payment_review("uz", payment.id)
        try:
            if payment.receipt_file_id and payment.receipt_kind != "document":
                await bot.send_photo(
                    telegram_id, payment.receipt_file_id, caption=text[:1024], reply_markup=markup
                )
            else:
                await bot.send_message(telegram_id, text, reply_markup=markup)
        except Exception:
            logger.info(
                "dispute notify failed telegram_id=%s payment_id=%s", telegram_id, payment.id
            )
