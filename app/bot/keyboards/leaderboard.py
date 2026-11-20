"""Leaderboard schedule and announcement keyboard."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import BoardCB, ChatCB
from app.i18n import t
from app.services.schedule import TIMES


def board_menu(lang: str, chat_id: int, weekday: int, enabled: bool) -> InlineKeyboardMarkup:
    """Weekday, clock time, pause, announce-now and back."""
    days = [_day(lang, chat_id, day, weekday) for day in range(1, 8)]
    times = [
        InlineKeyboardButton(text=moment.strftime("%H:%M"), callback_data=_time(chat_id, code))
        for code, moment in TIMES.items()
    ]
    toggle = "board_disable" if enabled else "board_enable"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            days[:4],
            days[4:],
            times[:3],
            times[3:],
            [_act(t(toggle, lang), "toggle", chat_id)],
            [_act(t("board_now", lang), "now", chat_id)],
            [
                InlineKeyboardButton(
                    text=t("back", lang),
                    callback_data=ChatCB(a="open", id=chat_id).pack(),
                )
            ],
        ]
    )


def _day(lang: str, chat_id: int, day: int, selected: int) -> InlineKeyboardButton:
    label = t(f"weekday_{day}", lang)
    if day == selected:
        label = "• " + label
    return InlineKeyboardButton(text=label, callback_data=_week(chat_id, day))


def _week(chat_id: int, day: int) -> str:
    return BoardCB(a="day", id=chat_id, v=str(day)).pack()


def _time(chat_id: int, code: str) -> str:
    return BoardCB(a="time", id=chat_id, v=code).pack()


def _act(text: str, action: str, chat_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=BoardCB(a=action, id=chat_id).pack())
