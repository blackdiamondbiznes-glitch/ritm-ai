"""ChatAdminCache: TTLs, timeouts, fail-closed, shared in-flight calls, budget."""

import asyncio
from types import SimpleNamespace

from app.webapp.admins import ChatAdminCache, bot_fetcher


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Fetch:
    def __init__(self, answers: dict, delay: float = 0.0) -> None:
        self.answers = answers
        self.delay = delay
        self.calls: list[int] = []

    async def __call__(self, chat_id: int):
        self.calls.append(chat_id)
        if self.delay:
            await asyncio.sleep(self.delay)
        value = self.answers[chat_id]
        if isinstance(value, BaseException):
            raise value
        return value


async def test_admin_list_is_cached_until_ttl() -> None:
    clock, fetch = Clock(), Fetch({-1: [10, 11]})
    cache = ChatAdminCache(fetch=fetch, ttl=60, clock=clock)
    assert await cache.is_admin(-1, 10)
    assert await cache.is_admin(-1, 11)
    assert not await cache.is_admin(-1, 12)
    assert fetch.calls == [-1]
    clock.now += 59
    assert await cache.is_admin(-1, 10) and fetch.calls == [-1]
    fetch.answers[-1] = [11]  # 10 was demoted in Telegram
    clock.now += 2
    assert not await cache.is_admin(-1, 10)
    assert fetch.calls == [-1, -1]


async def test_failures_fail_closed_and_are_retried_after_failed_ttl() -> None:
    clock, fetch = Clock(), Fetch({-1: OSError("kicked"), -2: RuntimeError("boom")})
    cache = ChatAdminCache(fetch=fetch, failed_ttl=15, clock=clock)
    assert await cache.admins(-1) is None
    assert not await cache.is_admin(-1, 10)
    assert not await cache.is_admin(-2, 10)  # unexpected errors also deny, never raise
    assert fetch.calls == [-1, -2]
    clock.now += 16
    fetch.answers[-1] = [10]
    assert await cache.is_admin(-1, 10)
    assert fetch.calls == [-1, -2, -1]


async def test_slow_telegram_times_out_and_denies() -> None:
    fetch = Fetch({-1: [10]}, delay=1.0)
    cache = ChatAdminCache(fetch=fetch, timeout=0.05)
    started = asyncio.get_running_loop().time()
    assert not await cache.is_admin(-1, 10)
    assert asyncio.get_running_loop().time() - started < 0.5


async def test_concurrent_callers_share_one_request() -> None:
    fetch = Fetch({-1: [10]}, delay=0.05)
    cache = ChatAdminCache(fetch=fetch)
    results = await asyncio.gather(*(cache.is_admin(-1, 10) for _ in range(20)))
    assert all(results) and fetch.calls == [-1]


async def test_admin_of_respects_budget_and_finishes_in_background() -> None:
    fast, slow = Fetch({-1: [10], -2: [99]}), Fetch({-3: [10]}, delay=0.2)

    async def fetch(chat_id: int):
        return await (slow if chat_id == -3 else fast)(chat_id)

    cache = ChatAdminCache(fetch=fetch, budget=0.05)
    started = asyncio.get_running_loop().time()
    assert await cache.admin_of([-1, -2, -3, -1], 10) == {-1}
    assert asyncio.get_running_loop().time() - started < 0.15
    await asyncio.sleep(0.25)  # the slow list kept loading and is now cached
    assert await cache.admin_of([-1, -2, -3], 10) == {-1, -3}
    assert fast.calls == [-1, -2] and slow.calls == [-3]


async def test_disabled_cache_and_forget() -> None:
    assert not ChatAdminCache().enabled
    assert await ChatAdminCache().admin_of([-1], 10) == set()
    assert not await ChatAdminCache().is_admin(-1, 10)
    fetch = Fetch({-1: [10]})
    cache = ChatAdminCache(fetch=fetch)
    await cache.is_admin(-1, 10)
    cache.forget(-1)
    await cache.is_admin(-1, 10)
    assert fetch.calls == [-1, -1]


async def test_bot_fetcher_skips_bots() -> None:
    class Bot:
        async def get_chat_administrators(self, chat_id: int):
            return [
                SimpleNamespace(user=SimpleNamespace(id=10, is_bot=False)),
                SimpleNamespace(user=SimpleNamespace(id=77, is_bot=True)),
                SimpleNamespace(user=None),
            ]

    assert await bot_fetcher(Bot())(-1) == [10]
