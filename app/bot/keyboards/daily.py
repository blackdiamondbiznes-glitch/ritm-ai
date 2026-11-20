"""Daily-post schedule keyboard."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import ChatCB, DailyCB
from app.i18n import t
from app.services.schedule import TIMES


def daily_menu(lang: str, chat_id: int, enabled: bool) -> InlineKeyboardMarkup:
    """Clock times, pause, write-now and back."""
    times = [
        InlineKeyboardButton(text=moment.strftime("%H:%M"), callback_data=_time(chat_id, code))
        for code, moment in TIMES.items()
    ]
    toggle = "daily_disable" if enabled else "daily_enable"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            times[:3],
            times[3:],
            [_btn(t(toggle, lang), "toggle", chat_id)],
            [_btn(t("daily_now", lang), "now", chat_id)],
            [
                InlineKeyboardButton(
                    text=t("back", lang),
                    callback_data=ChatCB(a="open", id=chat_id).pack(),
                )
            ],
        ]
    )


def _time(chat_id: int, code: str) -> str:
    return DailyCB(a="time", id=chat_id, v=code).pack()


def _btn(text: str, action: str, chat_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=DailyCB(a=action, id=chat_id).pack())
