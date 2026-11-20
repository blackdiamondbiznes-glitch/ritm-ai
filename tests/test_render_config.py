"""Render deployment: database URL, PORT, Telegram mode and the webhook route."""

import asyncio
import logging
import os
import socket

import aiohttp
import pytest
from aiogram import Bot, Dispatcher
from aiohttp.test_utils import TestClient, TestServer
from app.bot.telegram_mode import clear_webhook, start_webhook, webhook_routes
from app.config import Settings
from app.db.url import normalize_database_url
from app.webapp.server import create_app, start_webapp
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
TOKEN = "123456:TEST-token"


def _settings(**kw) -> Settings:
    base = {"bot_token": TOKEN, "database_url": _URL}
    return Settings(_env_file=None, **{**base, **kw})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@dpg-x-a/db", "postgresql+asyncpg://u:p@dpg-x-a/db"),
        (
            "postgresql://u:p@dpg-x-a.frankfurt-postgres.render.com/db",
            "postgresql+asyncpg://u:p@dpg-x-a.frankfurt-postgres.render.com/db",
        ),
        (
            "postgresql+asyncpg://bot:bot@localhost:5432/e",
            "postgresql+asyncpg://bot:bot@localhost:5432/e",
        ),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
        (
            "postgresql://u:p@h/db?sslmode=disable&application_name=ritm",
            "postgresql+asyncpg://u:p@h/db?application_name=ritm",
        ),
        ("postgresql://u:p%40x@h/db", "postgresql+asyncpg://u:p%40x@h/db"),
        ("", ""),
    ],
)
def test_database_url_is_normalised_for_asyncpg(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected


def test_settings_accept_render_database_url() -> None:
    settings = _settings(database_url="postgres://u:p@dpg-abc-a/ritm")
    assert settings.database_url == "postgresql+asyncpg://u:p@dpg-abc-a/ritm"


def test_telegram_mode_defaults_to_polling_and_rejects_typos() -> None:
    assert _settings().telegram_mode == "polling"
    assert _settings(telegram_mode=" Webhook ").telegram_mode == "webhook"
    assert _settings(telegram_mode="off").telegram_mode == "off"
    with pytest.raises(ValidationError):
        _settings(telegram_mode="hook")


def test_render_port_and_public_url() -> None:
    local = _settings()
    assert local.http_port == 8081 and local.public_base_url is None and local.webhook_url is None
    render = _settings(port=10000, render_external_url="https://ritm-ai.onrender.com")
    assert render.http_port == 10000
    assert render.public_webapp_url == "https://ritm-ai.onrender.com"
    assert render.webhook_url == f"https://ritm-ai.onrender.com/tg/{render.webhook_token}"
    # An explicit WEBAPP_URL (custom domain) wins over the onrender.com name.
    custom = _settings(
        webapp_url="https://app.example.uz/", render_external_url="https://x.onrender.com"
    )
    assert custom.public_webapp_url == "https://app.example.uz"
    assert custom.webhook_url.startswith("https://app.example.uz/tg/")
    assert _settings(webapp_url="http://insecure").webhook_url is None


def test_webhook_secret_is_stable_and_never_the_token() -> None:
    one = _settings().webhook_token
    assert one == _settings().webhook_token and len(one) == 48
    assert TOKEN not in one and one != _settings(bot_token="999:other").webhook_token
    assert _settings(webhook_secret="My_secret-1").webhook_token == "My_secret-1"
    with pytest.raises(ValueError):
        _ = _settings(webhook_secret="bad secret!").webhook_token


@pytest.fixture
async def sessions():
    engine = create_async_engine(_URL)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_health_and_webhook_share_the_public_port(sessions) -> None:
    settings = _settings(telegram_mode="webhook", render_external_url="https://ritm.onrender.com")
    bot = Bot(token=TOKEN)
    seen = []
    dispatcher = Dispatcher()

    @dispatcher.message()
    async def _echo(message) -> None:
        seen.append(message.text)

    app = create_app(settings, sessions, bot=bot)
    webhook_routes(dispatcher, bot, settings)(app)
    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "A"},
            "text": "hi",
        },
    }
    try:
        async with TestClient(TestServer(app)) as client:
            health = await client.get("/health")
            assert health.status == 200 and (await health.text()) == "ok\n"
            path = settings.webhook_path
            assert (await client.post(path, json=update)).status == 401
            bad = {"X-Telegram-Bot-Api-Secret-Token": "wrong"}
            assert (await client.post(path, json=update, headers=bad)).status == 401
            good = {"X-Telegram-Bot-Api-Secret-Token": settings.webhook_token}
            assert (await client.post(path, json=update, headers=good)).status == 200
            assert (await client.post("/tg/guess", json=update, headers=good)).status in (404, 405)
            for _ in range(50):
                if seen:
                    break
                await asyncio.sleep(0.02)
            assert seen == ["hi"]
    finally:
        await bot.session.close()


class _FakeBot:
    def __init__(self) -> None:
        self.calls = []

    async def set_webhook(self, **kw) -> bool:
        self.calls.append(("set", kw))
        return True

    async def delete_webhook(self, **kw) -> bool:
        self.calls.append(("delete", kw))
        return True


async def test_webhook_registration_keeps_pending_updates() -> None:
    settings = _settings(render_external_url="https://ritm.onrender.com")
    bot = _FakeBot()
    await start_webhook(bot, settings, ["message", "callback_query"])
    kind, kw = bot.calls[0]
    assert kind == "set" and kw["url"] == settings.webhook_url
    assert kw["secret_token"] == settings.webhook_token and kw["drop_pending_updates"] is False
    assert kw["allowed_updates"] == ["message", "callback_query"]
    await clear_webhook(bot)
    assert bot.calls[1] == ("delete", {"drop_pending_updates": False})
    with pytest.raises(RuntimeError):
        await start_webhook(_FakeBot(), _settings(), [])


def test_off_mode_skips_scheduler_and_telegram_setup() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    off = source.index('if mode == "off":')
    assert source.index('if mode != "off":') < source.index("scheduler.start()")
    assert off < source.index("await setup_commands(bot)")
    assert off < source.index("await clear_webhook(bot)")


async def test_webhook_secret_never_reaches_the_logs(sessions, caplog) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    settings = _settings(
        telegram_mode="webhook", render_external_url="https://ritm.onrender.com", port=port
    )
    bot = Bot(token=TOKEN)
    dispatcher = Dispatcher()
    caplog.set_level(logging.DEBUG)
    runner = await start_webapp(
        settings, sessions, bot=bot, configure=webhook_routes(dispatcher, bot, settings)
    )
    assert runner is not None
    try:
        async with aiohttp.ClientSession() as http:
            url = f"http://127.0.0.1:{port}{settings.webhook_path}"
            async with http.post(url, json={"update_id": 1}) as response:
                assert response.status == 401
            async with http.get(f"http://127.0.0.1:{port}/health") as response:
                assert response.status == 200
    finally:
        await runner.cleanup()
        await bot.session.close()
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert settings.webhook_token not in logged and TOKEN not in logged
