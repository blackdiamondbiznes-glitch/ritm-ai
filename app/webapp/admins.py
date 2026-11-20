"""Live Telegram admin lists with a short cache. The client is never trusted.

One getChatAdministrators call per chat answers "is this user an admin?" for
everyone in that chat for `ttl` seconds. Failures fail closed (not an admin) and
are remembered for `failed_ttl` seconds so a broken chat is not retried on every
request. Concurrent callers share one in-flight call.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol

from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

ADMIN_TTL = 60.0
FAILED_TTL = 15.0
FETCH_TIMEOUT = 3.0
DISCOVERY_BUDGET = 1.0
CONCURRENCY = 8

Fetcher = Callable[[int], Awaitable[Iterable[int]]]


class AdminBot(Protocol):
    async def get_chat_administrators(self, chat_id: int) -> list: ...


def bot_fetcher(bot: AdminBot) -> Fetcher:
    """Human admin ids from aiogram ChatMember objects. Bots are skipped."""

    async def fetch(chat_id: int) -> list[int]:
        members = await bot.get_chat_administrators(chat_id)
        out: list[int] = []
        for member in members:
            user = getattr(member, "user", None)
            if user is None or getattr(user, "is_bot", False):
                continue
            out.append(int(user.id))
        return out

    return fetch


class ChatAdminCache:
    """Admin id sets per Telegram chat id."""

    def __init__(
        self,
        bot: AdminBot | None = None,
        *,
        ttl: float = ADMIN_TTL,
        failed_ttl: float = FAILED_TTL,
        timeout: float = FETCH_TIMEOUT,
        budget: float = DISCOVERY_BUDGET,
        concurrency: int = CONCURRENCY,
        clock: Callable[[], float] | None = None,
        fetch: Fetcher | None = None,
    ) -> None:
        self._ttl = ttl
        self._failed_ttl = failed_ttl
        self._timeout = timeout
        self._budget = budget
        self._clock = clock or time.monotonic
        self._gate = asyncio.Semaphore(max(1, concurrency))
        self._rows: dict[int, tuple[float, frozenset[int] | None]] = {}
        self._inflight: dict[int, asyncio.Task[frozenset[int] | None]] = {}
        if fetch is not None:
            self._fetch: Fetcher | None = fetch
        elif bot is not None:
            self._fetch = bot_fetcher(bot)
        else:
            self._fetch = None

    @property
    def enabled(self) -> bool:
        return self._fetch is not None

    def _fresh(self, chat_id: int) -> tuple[bool, frozenset[int] | None]:
        hit = self._rows.get(chat_id)
        if hit is None:
            return False, None
        stamp, admins = hit
        ttl = self._ttl if admins is not None else self._failed_ttl
        return self._clock() - stamp < ttl, admins

    async def admins(self, telegram_chat_id: int) -> frozenset[int] | None:
        """Current admin ids, or None when Telegram did not answer."""
        if self._fetch is None:
            return None
        fresh, admins = self._fresh(telegram_chat_id)
        if fresh:
            return admins
        return await self._task(telegram_chat_id)

    async def is_admin(self, telegram_chat_id: int, telegram_user_id: int) -> bool:
        """Fail closed: unknown means no."""
        admins = await self.admins(telegram_chat_id)
        return admins is not None and telegram_user_id in admins

    async def admin_of(self, telegram_chat_ids: Iterable[int], telegram_user_id: int) -> set[int]:
        """Which of these chats the user administers. Waits at most `budget` seconds.

        Chats still loading after the budget are left out this time; their lists
        keep loading in the background and are used on the next request.
        """
        found: set[int] = set()
        if self._fetch is None:
            return found
        waiting: dict[int, asyncio.Task[frozenset[int] | None]] = {}
        for chat_id in dict.fromkeys(telegram_chat_ids):
            fresh, admins = self._fresh(chat_id)
            if fresh:
                if admins is not None and telegram_user_id in admins:
                    found.add(chat_id)
                continue
            waiting[chat_id] = self._task(chat_id)
        if waiting:
            done, _pending = await asyncio.wait(set(waiting.values()), timeout=self._budget)
            for chat_id, task in waiting.items():
                if task in done and not task.cancelled():
                    admins = task.result()
                    if admins is not None and telegram_user_id in admins:
                        found.add(chat_id)
        return found

    def forget(self, telegram_chat_id: int) -> None:
        self._rows.pop(telegram_chat_id, None)

    def _task(self, chat_id: int) -> asyncio.Task[frozenset[int] | None]:
        task = self._inflight.get(chat_id)
        if task is None or task.done():
            task = asyncio.ensure_future(self._load(chat_id))
            self._inflight[chat_id] = task
        return task

    async def _load(self, chat_id: int) -> frozenset[int] | None:
        admins: frozenset[int] | None
        try:
            async with self._gate:
                ids = await asyncio.wait_for(self._fetch(chat_id), timeout=self._timeout)
            admins = frozenset(int(item) for item in ids)
        except (TelegramAPIError, OSError, ValueError, TypeError, TimeoutError):
            logger.info("admin list unavailable chat_id=%s", chat_id)
            admins = None
        except Exception:  # noqa: BLE001 - permission checks must fail closed, never 500
            logger.exception("admin list failed chat_id=%s", chat_id)
            admins = None
        finally:
            self._inflight.pop(chat_id, None)
        self._rows[chat_id] = (self._clock(), admins)
        return admins
