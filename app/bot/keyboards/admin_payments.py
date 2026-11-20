"""Super-admin payment review keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import AdminCB, AdminPayCB, MenuCB
from app.db.models.payments import Payment
from app.i18n import t


def payments_list(lang: str, rows: list[Payment]) -> InlineKeyboardMarkup:
    """One button per pending payment, plus back to the admin home."""
    buttons = [
        [
            InlineKeyboardButton(
                text=t("pay_admin_open", lang, id=row.id, amount=_money(row.amount_uzs)),
                callback_data=AdminPayCB(a="open", id=row.id).pack(),
            )
        ]
        for row in rows
    ]
    buttons.append(
        [InlineKeyboardButton(text=t("back", lang), callback_data=MenuCB(a="admin").pack())]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


REJECT_REASONS = ("no_money", "wrong_amount", "no_ref", "unreadable")


def payment_review(lang: str, payment_id: int) -> InlineKeyboardMarkup:
    """Approve, reject, mark a fake receipt, or return to the queue."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("pay_admin_yes", lang),
                    callback_data=AdminPayCB(a="ok", id=payment_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("pay_admin_no", lang),
                    callback_data=AdminPayCB(a="no", id=payment_id).pack(),
                ),
                InlineKeyboardButton(
                    text=t("pay_admin_fake", lang),
                    callback_data=AdminPayCB(a="fk", id=payment_id).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("back", lang),
                    callback_data=AdminCB(a="pays").pack(),
                )
            ],
        ]
    )


def reject_reasons(lang: str, payment_id: int) -> InlineKeyboardMarkup:
    """Preset reasons, a typed one, or back to the request."""
    rows = [
        [
            InlineKeyboardButton(
                text=t(f"pay_reason_{code}", lang),
                callback_data=AdminPayCB(a="rr", id=payment_id, v=code).pack(),
            )
        ]
        for code in REJECT_REASONS
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=t("pay_reason_other", lang),
                callback_data=AdminPayCB(a="rt", id=payment_id).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=t("cancel", lang), callback_data=AdminPayCB(a="open", id=payment_id).pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fake_confirm(lang: str, payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("pay_admin_fake_yes", lang),
                    callback_data=AdminPayCB(a="fky", id=payment_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("cancel", lang),
                    callback_data=AdminPayCB(a="open", id=payment_id).pack(),
                )
            ],
        ]
    )


def reject_cancel(lang: str, payment_id: int) -> InlineKeyboardMarkup:
    """Leave the reject reason step."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("cancel", lang),
                    callback_data=AdminPayCB(a="open", id=payment_id).pack(),
                )
            ]
        ]
    )


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")
