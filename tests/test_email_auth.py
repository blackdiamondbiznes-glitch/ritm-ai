"""Email-account field validation and password hashing."""

from unittest.mock import Mock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request
from app.config import Settings
from app.webapp.auth import issue_account_session, session_secret
from app.webapp.email_auth import (
    EmailAccountError,
    hash_password,
    normalize_email,
    validate_signup,
    verify_password,
)
from app.webapp.rate_limit import RateLimiter
from app.webapp.routes import _context
from app.webapp.server import create_app


def test_email_is_normalized_and_signup_role_is_limited() -> None:
    assert normalize_email("  Teacher@Example.COM ") == "teacher@example.com"
    assert validate_signup(" Dilnoza ", "correct-horse-battery", "teacher") == (
        "Dilnoza",
        "correct-horse-battery",
        "teacher",
    )
    with pytest.raises(EmailAccountError, match="role"):
        validate_signup("Name", "correct-horse-battery", "super_admin")


@pytest.mark.parametrize("role", ["teacher", "student", "community_owner"])
def test_signup_allows_only_the_supported_account_roles(role) -> None:
    assert validate_signup("Name", "correct-horse-battery", role)[2] == role


@pytest.mark.parametrize(
    ("email", "password", "role", "code"),
    [
        ("not-an-email", "correct-horse-battery", "teacher", "email"),
        ("teacher@example.com", "short", "teacher", "password"),
        ("teacher@example.com", "correct-horse-battery", "unknown", "role"),
    ],
)
def test_signup_rejects_invalid_fields(email, password, role, code) -> None:
    if code == "email":
        with pytest.raises(EmailAccountError, match=code):
            normalize_email(email)
    else:
        with pytest.raises(EmailAccountError, match=code):
            validate_signup("Name", password, role)


def test_password_hash_is_salted_and_verified() -> None:
    first = hash_password("correct-horse-battery")
    second = hash_password("correct-horse-battery")
    assert first != second
    assert "correct-horse-battery" not in first
    assert verify_password("correct-horse-battery", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("correct-horse-battery", "malformed")


async def test_eduflow_bootstrap_reports_missing_bot_configuration() -> None:
    settings = Settings(
        bot_token="1:test-token",
        database_url="postgresql+asyncpg://bot:bot@localhost/test",
    )
    app = create_app(settings, None)

    async with TestClient(TestServer(app)) as client:
        response = await client.post("/api/eduflow/bootstrap", json={"initData": "bad"})
        body = await response.json()

    assert response.status == 503
    assert body == {"error": "eduflow_auth_unavailable"}


async def test_signup_endpoint_rejects_super_admin_without_creating_an_account() -> None:
    settings = Settings(
        bot_token="1:test-token",
        database_url="postgresql+asyncpg://bot:bot@localhost/test",
    )
    app = create_app(settings, None)

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/email/signup",
            json={
                "email": "attacker@example.com",
                "name": "Attacker",
                "password": "correct-horse-battery",
                "role": "super_admin",
                "owner_id": 1,
                "is_super_admin": True,
            },
        )
        body = await response.json()

    assert response.status == 400
    assert body == {"error": "role"}


@pytest.mark.asyncio
async def test_email_session_resolves_user_from_signed_account_id() -> None:
    settings = Settings(
        bot_token="1:test-token",
        database_url="postgresql+asyncpg://bot:bot@localhost/test",
    )
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    token = issue_account_session(73, secret, settings.webapp_session_ttl)
    user = Mock(id=73, telegram_id=None, is_blocked=False)
    session = Mock()
    app = create_app(settings, Mock(return_value=session), limiter=RateLimiter(limit=100))
    request = make_mocked_request(
        "POST",
        "/api/tutor/groups?owner_id=900",
        headers={"Authorization": f"Bearer {token}"},
        app=app,
    )

    class Users:
        def __init__(self, _session):
            pass

        async def get_by_id(self, user_id):
            assert user_id == 73
            return user

        async def get_by_telegram_id(self, _telegram_id):
            raise AssertionError("email account must not resolve through Telegram identity")

    context = object()
    with (
        patch("app.webapp.routes.UserRepository", Users),
        patch("app.webapp.routes.build_context", return_value=context) as build_context,
    ):
        result = await _context(request)

    assert result is context
    build_context.assert_called_once_with(session, settings, user, app["admins"])
