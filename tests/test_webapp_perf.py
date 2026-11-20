"""Speed fixes: member-count cache never blocks long, assets are versioned and gzipped."""

import asyncio
import gzip
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from app.webapp.assets import IMMUTABLE, REVALIDATE, setup_assets
from app.webapp.members import MemberCountCache
from app.webapp.rate_limit import RateLimiter

STATIC = Path(__file__).resolve().parents[1] / "app" / "webapp" / "static"


async def test_counts_run_in_parallel_and_respect_the_budget() -> None:
    calls: list[int] = []

    async def fetch(chat_id: int) -> int:
        calls.append(chat_id)
        await asyncio.sleep(0.05 if chat_id != 3 else 0.5)
        return chat_id * 10

    cache = MemberCountCache(fetch=fetch, budget=0.2, timeout=2)
    loop = asyncio.get_running_loop()
    started = loop.time()
    first = await cache.counts([1, 2, 3])
    elapsed = loop.time() - started
    assert first == {1: 10, 2: 20}
    assert elapsed < 0.4
    await asyncio.sleep(0.4)
    assert await cache.counts([1, 2, 3]) == {1: 10, 2: 20, 3: 30}
    assert sorted(calls) == [1, 2, 3]


async def test_failures_are_cached_and_inflight_fetches_are_shared() -> None:
    calls = {"n": 0}
    clock = {"t": 0.0}

    async def broken(_chat_id: int) -> int:
        calls["n"] += 1
        await asyncio.sleep(0.01)
        raise OSError("chat not found")

    cache = MemberCountCache(fetch=broken, failed_ttl=120, clock=lambda: clock["t"])
    results = await asyncio.gather(cache.count(5), cache.count(5), cache.count(5))
    assert results == [None, None, None]
    assert calls["n"] == 1
    assert await cache.count(5) is None
    assert calls["n"] == 1
    clock["t"] = 121
    assert await cache.count(5) is None
    assert calls["n"] == 2


async def test_hanging_fetch_times_out() -> None:
    async def hang(_chat_id: int) -> int:
        await asyncio.sleep(10)
        return 1

    cache = MemberCountCache(fetch=hang, timeout=0.05, budget=1)
    assert await cache.count(1) is None
    assert cache.cached(1) == (True, None)


async def test_assets_are_versioned_gzipped_and_cached() -> None:
    app = web.Application()
    store = setup_assets(app, STATIC)
    async with TestClient(TestServer(app)) as client:
        index = await client.get("/", headers={"Accept-Encoding": "gzip"})
        assert index.status == 200
        assert index.headers["Cache-Control"] == REVALIDATE
        html = await index.text()
        assert f"/s/{store.version}/app.js" in html
        assert "modulepreload" in html
        assert '"/s/app.js"' not in html

        res = await client.get(f"/s/{store.version}/ui.js", headers={"Accept-Encoding": "gzip"})
        assert res.status == 200
        assert res.headers["Cache-Control"] == IMMUTABLE
        assert res.headers["Content-Encoding"] == "gzip"
        assert res.headers["Content-Type"].startswith("text/javascript")
        raw = await res.read()
        assert raw == (STATIC / "ui.js").read_bytes()

        etag = res.headers["ETag"]
        again = await client.get(f"/s/{store.version}/ui.js", headers={"If-None-Match": etag})
        assert again.status == 304

        stale = await client.get("/s/0000000000/ui.js")
        assert stale.status == 200 and stale.headers["Cache-Control"] == REVALIDATE
        legacy = await client.get("/s/ui.js")
        assert legacy.status == 200 and legacy.headers["Cache-Control"] == REVALIDATE
        assert (await client.get(f"/s/{store.version}/nope.js")).status == 404
        assert (await client.get(f"/s/{store.version}/..%2Fassets.py")).status == 404
    assert gzip.decompress(store.files["ui.js"].gz) == (STATIC / "ui.js").read_bytes()


def test_rate_limiter_default_allows_busy_users() -> None:
    limiter = RateLimiter()
    assert all(limiter.allow("api:user:1", now=float(i) / 10) for i in range(120))
    assert not limiter.allow("api:user:1", now=12.0)
    assert limiter.allow("api:user:2", now=12.0)
