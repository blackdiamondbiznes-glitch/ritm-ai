"""Registration button posted into the teacher's channel or group."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import EnrollCB
from app.i18n import t


def enroll_keyboard(lang: str, code: str) -> InlineKeyboardMarkup:
    """One button. A tap is delivered even when the bot chat is already open."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("enroll_button", lang),
                    callback_data=EnrollCB(c=code).pack(),
                )
            ]
        ]
    )
