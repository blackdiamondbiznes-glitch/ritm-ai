"""Rate-limited channel sends. Waits on 429. Never logs the text."""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, InputPollOption

logger = logging.getLogger(__name__)
_MAX_WAIT = 60


class ChatGone(Exception):
    """The bot can no longer post in this chat."""


class RateLimitedSender:
    """Serializes outbound posts and keeps a minimum gap between them."""

    def __init__(self, gap_seconds: float) -> None:
        self._gap = gap_seconds
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def post(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        markup: InlineKeyboardMarkup | None = None,
    ) -> int:
        """Send HTML text. Returns the Telegram message id."""
        async with self._lock:
            await self._pause()
            return await _deliver(bot, chat_id, text, markup)

    async def poll(
        self,
        bot: Bot,
        chat_id: int,
        question: str,
        options: list[str],
        correct: int,
        explanation: str | None,
    ) -> tuple[int, str]:
        """Send a non-anonymous quiz poll. Returns message id and poll id."""
        async with self._lock:
            await self._pause()
            return await _poll(bot, chat_id, question, options, correct, explanation)

    async def _pause(self) -> None:
        loop = asyncio.get_running_loop()
        delay = self._next - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        self._next = loop.time() + self._gap


async def _deliver(bot: Bot, chat_id: int, text: str, markup: InlineKeyboardMarkup | None) -> int:
    try:
        return await _once(bot, chat_id, text, markup)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(min(int(exc.retry_after), _MAX_WAIT))
        return await _once(bot, chat_id, text, markup)


async def _once(bot: Bot, chat_id: int, text: str, markup: InlineKeyboardMarkup | None) -> int:
    try:
        message = await bot.send_message(chat_id, text, reply_markup=markup)
    except TelegramForbiddenError as exc:
        logger.info("post forbidden chat_id=%s", chat_id)
        raise ChatGone from exc
    except TelegramBadRequest as exc:
        if _missing(exc):
            logger.info("post rejected chat_id=%s", chat_id)
            raise ChatGone from exc
        raise
    return int(message.message_id)


def _missing(exc: TelegramBadRequest) -> bool:
    text = str(exc).lower()
    needles = ("chat not found", "bot was kicked", "need administrator", "not enough rights")
    return any(needle in text for needle in needles)


async def _poll(
    bot: Bot,
    chat_id: int,
    question: str,
    options: list[str],
    correct: int,
    explanation: str | None,
) -> tuple[int, str]:
    try:
        return _ids(await _poll_once(bot, chat_id, question, options, correct, explanation))
    except TelegramRetryAfter as exc:
        await asyncio.sleep(min(int(exc.retry_after), _MAX_WAIT))
        return _ids(await _poll_once(bot, chat_id, question, options, correct, explanation))


def _ids(message: object) -> tuple[int, str]:
    poll = getattr(message, "poll", None)
    if poll is None:
        raise ChatGone
    return int(message.message_id), str(poll.id)  # type: ignore[attr-defined]


async def _poll_once(
    bot: Bot,
    chat_id: int,
    question: str,
    options: list[str],
    correct: int,
    explanation: str | None,
):
    try:
        return await bot.send_poll(
            chat_id,
            question,
            [InputPollOption(text=option) for option in options],
            type="quiz",
            correct_option_id=correct,
            is_anonymous=False,
            explanation=explanation,
        )
    except TelegramForbiddenError as exc:
        logger.info("poll forbidden chat_id=%s", chat_id)
        raise ChatGone from exc
    except TelegramRetryAfter:
        raise
    except TelegramBadRequest as exc:
        if _missing(exc):
            logger.info("poll rejected chat_id=%s", chat_id)
            raise ChatGone from exc
        raise
