"""Telegram member counts with a short in-process cache. Never blocks a response for long."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol

from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

DEFAULT_TTL = 600
FAILED_TTL = 120
FETCH_TIMEOUT = 3.0
WAIT_BUDGET = 0.3


class MemberBot(Protocol):
    """The one Bot method this cache needs."""

    async def get_chat_member_count(self, chat_id: int) -> int: ...


Fetcher = Callable[[int], Awaitable[int]]


class MemberCountCache:
    """Remember getChatMemberCount per Telegram chat.

    Successes live `ttl` seconds, failures `failed_ttl` seconds so a chat that
    Telegram refuses is not retried on every request. Concurrent callers share
    one in-flight fetch, and `counts` waits at most `budget` seconds: slow
    fetches keep running in the background and fill the cache for next time.
    """

    def __init__(
        self,
        bot: MemberBot | None = None,
        *,
        ttl: float = DEFAULT_TTL,
        failed_ttl: float = FAILED_TTL,
        timeout: float = FETCH_TIMEOUT,
        budget: float = WAIT_BUDGET,
        clock: Callable[[], float] | None = None,
        fetch: Fetcher | None = None,
    ) -> None:
        self._ttl = ttl
        self._failed_ttl = failed_ttl
        self._timeout = timeout
        self._budget = budget
        self._clock = clock or time.monotonic
        self._rows: dict[int, tuple[float, int | None]] = {}
        self._inflight: dict[int, asyncio.Task[int | None]] = {}
        if fetch is not None:
            self._fetch = fetch
        elif bot is not None:
            self._fetch = bot.get_chat_member_count
        else:
            self._fetch = None

    def cached(self, telegram_chat_id: int) -> tuple[bool, int | None]:
        """(fresh, value) without any network call."""
        hit = self._rows.get(telegram_chat_id)
        if hit is None:
            return False, None
        stamp, value = hit
        ttl = self._ttl if value is not None else self._failed_ttl
        return self._clock() - stamp < ttl, value

    async def count(self, telegram_chat_id: int) -> int | None:
        """Return the cached or live count, or None when Telegram refuses or is slow."""
        result = await self.counts([telegram_chat_id])
        return result.get(telegram_chat_id)

    async def counts(
        self, telegram_chat_ids: Iterable[int], *, budget: float | None = None
    ) -> dict[int, int]:
        """Counts for many chats in parallel. Chats without a value are omitted."""
        out: dict[int, int] = {}
        if self._fetch is None:
            return out
        waiting: dict[int, asyncio.Task[int | None]] = {}
        for chat_id in dict.fromkeys(telegram_chat_ids):
            fresh, value = self.cached(chat_id)
            if fresh:
                if value is not None:
                    out[chat_id] = value
                continue
            waiting[chat_id] = self._task(chat_id)
        if waiting:
            wait = self._budget if budget is None else budget
            done, _pending = await asyncio.wait(set(waiting.values()), timeout=wait)
            for chat_id, task in waiting.items():
                if task in done and not task.cancelled() and task.result() is not None:
                    out[chat_id] = task.result()
                elif task not in done:
                    _fresh, stale = self.cached(chat_id)
                    if stale is not None:
                        out[chat_id] = stale
        return out

    def _task(self, chat_id: int) -> asyncio.Task[int | None]:
        task = self._inflight.get(chat_id)
        if task is None or task.done():
            task = asyncio.ensure_future(self._load(chat_id))
            self._inflight[chat_id] = task
        return task

    async def _load(self, chat_id: int) -> int | None:
        try:
            value: int | None = int(
                await asyncio.wait_for(self._fetch(chat_id), timeout=self._timeout)
            )
        except (TelegramAPIError, OSError, ValueError, TypeError, TimeoutError):
            logger.info("member count unavailable chat_id=%s", chat_id)
            value = None
        finally:
            self._inflight.pop(chat_id, None)
        self._rows[chat_id] = (self._clock(), value)
        return value
