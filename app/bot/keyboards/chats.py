"""Chat list and chat card keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import ChatCB, MenuCB
from app.db.models.chats import Chat
from app.i18n import t


def chat_list(lang: str, chats: list[Chat]) -> InlineKeyboardMarkup:
    """One button per active chat."""
    rows = [[_title(chat)] for chat in chats[:20]]
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data=MenuCB(a="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_card(
    lang: str,
    chat_id: int,
    *,
    admin_quiz: bool | None = None,
    leaderboard: bool = False,
) -> InlineKeyboardMarkup:
    """Daily post, quiz, rating, optional admin-post toggle, edit, disconnect, back."""
    rows = [
        [_act(t("daily_open", lang), "daily", chat_id)],
        [_act(t("quiz_open", lang), "quiz", chat_id)],
    ]
    if leaderboard:
        rows.append([_act(t("board_open", lang), "board", chat_id)])
    if admin_quiz is not None:
        key = "apq_on" if admin_quiz else "apq_off"
        rows.append([_act(t(key, lang), "apq", chat_id)])
    rows.extend(
        [
            [_act(t("chat_edit", lang), "edit", chat_id)],
            [_act(t("chat_disconnect", lang), "ask", chat_id)],
            [_act(t("back", lang), "list", 0)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def disconnect_confirm(lang: str, chat_id: int) -> InlineKeyboardMarkup:
    """Yes or back to the card."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_act(t("chat_disconnect_yes", lang), "yes", chat_id)],
            [_act(t("back", lang), "open", chat_id)],
        ]
    )


def _title(chat: Chat) -> InlineKeyboardButton:
    title = chat.title.strip() or "Chat"
    if len(title) > 40:
        title = title[:39] + "…"
    return InlineKeyboardButton(text=title, callback_data=ChatCB(a="open", id=chat.id).pack())


def _act(text: str, action: str, chat_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=ChatCB(a=action, id=chat_id).pack())
