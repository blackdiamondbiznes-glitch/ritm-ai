"""Screens post at the bottom after text input or a terminal result."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import DeleteMessage, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser
from app.bot.view import show_screen, show_step

_CHAT = Chat(id=50, type="private")
_USER = TgUser(id=50, is_bot=False, first_name="Ada")
_DATE = datetime(2026, 11, 20, tzinfo=UTC)


class _Bot:
    def __init__(self) -> None:
        self.id = 1
        self.calls: list[object] = []
        self.direct_deletes: list[tuple[int, int]] = []
        self.raise_on_delete = False

    async def __call__(self, method: object) -> object:
        self.calls.append(method)
        if isinstance(method, DeleteMessage):
            if self.raise_on_delete:
                raise TelegramBadRequest(method=method, message="message to delete not found")
            return True
        if isinstance(method, SendMessage):
            return Message(message_id=99, date=_DATE, chat=_CHAT, text=method.text)
        return True

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        if self.raise_on_delete:
            raise TelegramBadRequest(method=MagicMock(), message="message to delete not found")
        self.direct_deletes.append((chat_id, message_id))
        return True


def _message(bot: _Bot, message_id: int = 10, text: str = "old") -> Message:
    return Message(message_id=message_id, date=_DATE, chat=_CHAT, text=text).as_(bot)


def _callback(bot: _Bot, message: Message) -> CallbackQuery:
    return CallbackQuery(
        id="1", from_user=_USER, chat_instance="x", data="w:save:-", message=message
    ).as_(bot)


def _of(bot: _Bot, kind: type) -> list[object]:
    return [call for call in bot.calls if isinstance(call, kind)]


def _state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=50, user_id=50),
    )


async def test_show_screen_edits_in_place_by_default() -> None:
    bot = _Bot()
    await show_screen(_callback(bot, _message(bot)), "Menyu", None)
    edits = _of(bot, EditMessageText)
    assert len(edits) == 1
    assert edits[0].text == "Menyu"
    assert not _of(bot, SendMessage)
    assert not _of(bot, DeleteMessage)


async def test_show_screen_new_posts_at_bottom_and_deletes_old() -> None:
    bot = _Bot()
    await show_screen(
        _callback(bot, _message(bot, message_id=10)), "Profil saqlandi.", None, new=True
    )
    sent = _of(bot, SendMessage)
    assert len(sent) == 1
    assert sent[0].text == "Profil saqlandi."
    deleted = _of(bot, DeleteMessage)
    assert len(deleted) == 1
    assert deleted[0].message_id == 10
    assert not _of(bot, EditMessageText)


async def test_show_screen_new_ignores_failed_delete() -> None:
    bot = _Bot()
    bot.raise_on_delete = True
    await show_screen(_callback(bot, _message(bot)), "Profil saqlandi.", None, new=True)
    assert len(_of(bot, SendMessage)) == 1
    assert len(_of(bot, DeleteMessage)) == 1


async def test_show_step_posts_new_message_and_drops_old_prompt() -> None:
    bot = _Bot()
    state = _state()
    await state.set_data({"anchor_id": 10, "chat_id": 7})
    await show_step(
        _message(bot, message_id=11, text="Kanal haqida..."), state, "Ohangni tanlang.", None
    )
    sent = _of(bot, SendMessage)
    assert len(sent) == 1
    assert sent[0].text == "Ohangni tanlang."
    deleted_ids = [call.message_id for call in _of(bot, DeleteMessage)]
    assert 11 in deleted_ids
    assert bot.direct_deletes == [(50, 10)]
    data = await state.get_data()
    assert data["anchor_id"] == 99
