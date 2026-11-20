"""Notify super admins of a new payment request. Failures must not block the owner."""

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.admin_payments import payment_review
from app.bot.pay_copy import admin_payment_alert
from app.config import Settings
from app.db.models.payments import Payment
from app.db.models.plans import Plan
from app.db.models.users import User

logger = logging.getLogger(__name__)


async def notify_payment_submitted(
    bot: Bot,
    settings: Settings,
    payment: Payment,
    owner: User,
    plan: Plan | None,
    *,
    founder: bool,
    lang: str = "uz",
    duplicates: list | None = None,
) -> None:
    """Message every super admin with the receipt attached (photo or document)."""
    text = admin_payment_alert(payment, owner, plan, lang, founder=founder, duplicates=duplicates)
    markup = payment_review(lang, payment.id)
    kind = getattr(payment, "receipt_kind", None) or "photo"
    for telegram_id in settings.admin_ids:
        try:
            await _deliver(bot, telegram_id, text, markup, payment.receipt_file_id, kind)
        except Exception:
            logger.info(
                "pay notify failed telegram_id=%s payment_id=%s",
                telegram_id,
                payment.id,
            )


async def _deliver(
    bot: Bot,
    telegram_id: int,
    text: str,
    markup: InlineKeyboardMarkup,
    receipt_file_id: str | None,
    kind: str = "photo",
) -> None:
    if receipt_file_id and len(text) <= 1024:
        if kind == "document":
            await bot.send_document(telegram_id, receipt_file_id, caption=text, reply_markup=markup)
        else:
            await bot.send_photo(telegram_id, receipt_file_id, caption=text, reply_markup=markup)
        return
    if receipt_file_id:
        if kind == "document":
            await bot.send_document(telegram_id, receipt_file_id)
        else:
            await bot.send_photo(telegram_id, receipt_file_id)
    await bot.send_message(telegram_id, text, reply_markup=markup)
