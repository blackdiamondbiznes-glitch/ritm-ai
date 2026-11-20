"""Admin keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import AdminCB, MenuCB
from app.db.models.plans import Plan
from app.i18n import t

_DAYS = ("7", "30", "90", "180")


def plan_choices(lang: str, plans: list[Plan]) -> InlineKeyboardMarkup:
    """One button per active plan."""
    rows = [
        [InlineKeyboardButton(text=plan.name, callback_data=AdminCB(a="plan", v=plan.code).pack())]
        for plan in plans
    ]
    rows.append(_cancel(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def day_choices(lang: str) -> InlineKeyboardMarkup:
    """Grant length. Not a price."""
    rows = [
        [InlineKeyboardButton(text=days, callback_data=AdminCB(a="days", v=days).pack())]
        for days in _DAYS
    ]
    rows.append(_cancel(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def block_choices(lang: str) -> InlineKeyboardMarkup:
    """Block or unblock, then the handler asks for an id."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("admin_do_block", lang),
                    callback_data=AdminCB(a="do", v="block").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("admin_do_unblock", lang),
                    callback_data=AdminCB(a="do", v="unblock").pack(),
                )
            ],
            _cancel(lang),
        ]
    )


def _cancel(lang: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=t("cancel", lang), callback_data=MenuCB(a="home").pack())]
