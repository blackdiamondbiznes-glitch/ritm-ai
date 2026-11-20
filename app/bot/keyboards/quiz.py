"""Quiz schedule keyboard and the answer buttons posted into the chat."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import ChatCB, PickCB, QuizCB
from app.i18n import t
from app.services.schedule import TIMES


def quiz_menu(lang: str, chat_id: int, enabled: bool) -> InlineKeyboardMarkup:
    """Clock times, pause, send-now and back."""
    times = [
        InlineKeyboardButton(text=moment.strftime("%H:%M"), callback_data=_time(chat_id, code))
        for code, moment in TIMES.items()
    ]
    toggle = "quiz_disable" if enabled else "quiz_enable"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            times[:3],
            times[3:],
            [_btn(t(toggle, lang), "toggle", chat_id)],
            [_btn(t("quiz_now", lang), "now", chat_id)],
            [
                InlineKeyboardButton(
                    text=t("back", lang),
                    callback_data=ChatCB(a="open", id=chat_id).pack(),
                )
            ],
        ]
    )


def link_keyboard(lang: str, url: str) -> InlineKeyboardMarkup:
    """One URL button. The channel itself never receives the answer choices."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("quiz_link", lang), url=url)]]
    )


def answer_keyboard(quiz_id: int, options: tuple[str, ...] | list[str]) -> InlineKeyboardMarkup:
    """One button per option. The label is the choice, not a letter."""
    rows = []
    for index, label in enumerate(options):
        text = label if len(label) <= 40 else label[:39] + "…"
        rows.append(
            [InlineKeyboardButton(text=text, callback_data=PickCB(id=quiz_id, v=str(index)).pack())]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _time(chat_id: int, code: str) -> str:
    return QuizCB(a="time", id=chat_id, v=code).pack()


def _btn(text: str, action: str, chat_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=QuizCB(a=action, id=chat_id).pack())
