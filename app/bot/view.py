"""Show one screen. Inline menus are edited; results after text go to the bottom."""

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


async def show_screen(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None,
    *,
    alert: str | None = None,
    new: bool = False,
) -> None:
    """Answer the callback, then edit in place or post a fresh message.

    Button-only menus keep `new=False` and edit the current message.
    After a text reply, or for a terminal result such as a saved profile,
    pass `new=True` so the screen appears at the bottom and the old bot
    message is deleted.
    """
    await callback.answer(alert, show_alert=bool(alert))
    if new:
        await _post_new(callback.message, text, markup)
        return
    await _edit(callback, text, markup)


async def edit_screen(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> None:
    """Edit without answering. Caller answers exactly once later."""
    await _edit(callback, text, markup)


async def show_step(
    message: Message,
    state: FSMContext,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> None:
    """After a free-text reply, post the next step at the bottom.

    Deletes the user's message and the previous bot prompt. The new message
    id is stored as `anchor_id` so later button steps can edit it.
    """
    data = await state.get_data()
    anchor = data.get("anchor_id")
    await _delete_quiet(message)
    sent = await message.answer(text, reply_markup=markup)
    await state.update_data(anchor_id=sent.message_id)
    if isinstance(anchor, int):
        await _delete_id_quiet(message.bot, message.chat.id, anchor)


def remember_anchor(callback: CallbackQuery, payload: dict[str, object]) -> dict[str, object]:
    """Store the message id so later text steps can find the bot prompt."""
    message = callback.message
    if message is not None:
        payload["anchor_id"] = message.message_id
    return payload


async def _edit(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> None:
    message = callback.message
    if message is None or not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        logger.info("edit failed chat_id=%s", message.chat.id)
        await _post_new(message, text, markup)


async def _post_new(
    message: Message | object | None,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> Message | None:
    """Send a new message at the bottom and drop the previous bot message."""
    if message is None or not isinstance(message, Message):
        return None
    sent = await message.answer(text, reply_markup=markup)
    await _delete_quiet(message)
    return sent


async def _delete_quiet(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        return


async def _delete_id_quiet(bot: object, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)  # type: ignore[attr-defined]
    except TelegramBadRequest:
        return
