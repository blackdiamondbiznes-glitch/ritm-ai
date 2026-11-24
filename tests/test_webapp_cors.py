import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.webapp.server import create_app

_DATABASE_URL = "postgresql+asyncpg://bot:bot@localhost/engagement"
_BOT_TOKEN = "1:test-token"
_ALLOWED = "https://eduflow.example.workers.dev"


def _settings(origins: str = "") -> Settings:
    return Settings(
        bot_token=_BOT_TOKEN,
        database_url=_DATABASE_URL,
        webapp_cors_origins=origins,
    )


@pytest.mark.asyncio
async def test_configured_origin_receives_cors_headers():
    app = create_app(_settings(f"{_ALLOWED}, https://another.example.workers.dev"), None)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/me/roles", headers={"Origin": _ALLOWED})

    assert response.status == 401
    assert response.headers["Access-Control-Allow-Origin"] == _ALLOWED
    assert response.headers["Vary"] == "Origin"


@pytest.mark.asyncio
async def test_unlisted_origin_never_receives_allow_origin():
    app = create_app(_settings(_ALLOWED), None)
    async with TestClient(TestServer(app)) as client:
        response = await client.get(
            "/api/cors-probe",
            headers={"Origin": "https://attacker.example.workers.dev"},
        )

    assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.asyncio
async def test_panel_keeps_same_origin_behavior():
    app = create_app(_settings(_ALLOWED), None)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/panel", headers={"Origin": _ALLOWED})

    assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.asyncio
async def test_allowed_preflight_succeeds_and_denied_preflight_has_no_cors_headers():
    app = create_app(_settings(_ALLOWED), None)
    async with TestClient(TestServer(app)) as client:
        allowed = await client.options(
            "/api/admin/workspaces",
            headers={
                "Origin": _ALLOWED,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        denied = await client.options(
            "/api/admin/workspaces",
            headers={
                "Origin": "https://attacker.example.workers.dev",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status == 204
    assert allowed.headers["Access-Control-Allow-Origin"] == _ALLOWED
    assert "POST" in allowed.headers["Access-Control-Allow-Methods"]
    assert denied.status == 403
    assert "Access-Control-Allow-Origin" not in denied.headers


@pytest.mark.asyncio
async def test_empty_allowlist_preserves_existing_options_behavior():
    app = create_app(_settings(), None)
    async with TestClient(TestServer(app)) as client:
        response = await client.options(
            "/api/admin/workspaces",
            headers={"Origin": _ALLOWED, "Access-Control-Request-Method": "GET"},
        )

    assert response.status == 405
    assert "Access-Control-Allow-Origin" not in response.headers


def test_wildcard_origins_are_rejected():
    settings = _settings("https://*.workers.dev")

    with pytest.raises(ValueError, match="WEBAPP_CORS_ORIGINS"):
        set(settings.cors_origins)
