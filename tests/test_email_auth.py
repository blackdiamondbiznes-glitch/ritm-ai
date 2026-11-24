"""Email-account field validation and password hashing."""

import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.users import User
from app.webapp.email_auth import (
    EmailAccountError,
    hash_password,
    normalize_email,
    validate_signup,
    verify_password,
)
from app.webapp.server import create_app
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement"
)


def _init_data(telegram_id: int, token: str) -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": telegram_id, "first_name": "Test"}),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_email_is_normalized_and_signup_role_is_limited() -> None:
    assert normalize_email("  Teacher@Example.COM ") == "teacher@example.com"
    assert validate_signup(" Dilnoza ", "correct-horse-battery", "teacher") == (
        "Dilnoza",
        "correct-horse-battery",
        "teacher",
    )
    with pytest.raises(EmailAccountError, match="role"):
        validate_signup("Name", "correct-horse-battery", "super_admin")


def test_eduflow_owner_ids_do_not_change_legacy_admin_ids() -> None:
    settings = Settings(
        bot_token="1:test-token",
        database_url="postgresql+asyncpg://bot:bot@localhost/test",
        super_admin_ids="101",
        eduflow_owner_telegram_ids="201, 202",
    )

    assert settings.admin_ids == frozenset({101})
    assert settings.eduflow_owner_ids == frozenset({201, 202})


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
    assert first.startswith("$argon2id$")
    assert "correct-horse-battery" not in first
    assert verify_password("correct-horse-battery", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("correct-horse-battery", "malformed")


async def test_eduflow_telegram_login_reports_missing_bot_configuration() -> None:
    settings = Settings(
        bot_token="1:test-token",
        database_url="postgresql+asyncpg://bot:bot@localhost/test",
        eduflow_bot_token="",
    )
    app = create_app(settings, None)

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/eduflow/telegram-login", json={"initData": "bad"}
        )
        body = await response.json()

    assert response.status == 503
    assert body == {"error": "eduflow_auth_unavailable"}


@pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
async def test_email_signup_and_login_over_http() -> None:
    email = f"auth-{uuid4().hex}@example.test"
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(bot_token="1:ritm-token", database_url=_URL)
    app = create_app(settings, sessions)
    try:
        async with TestClient(TestServer(app)) as client:
            created = await client.post(
                "/api/email/signup",
                json={
                    "name": "Test User",
                    "email": email,
                    "password": "correct-horse-battery",
                    "role": "teacher",
                },
            )
            assert created.status == 201
            signup = await created.json()
            assert signup["user"]["email"] == email
            assert "teacher" in signup["roles"]

            signed_in = await client.post(
                "/api/email/login",
                json={"email": email, "password": "correct-horse-battery"},
            )
            assert signed_in.status == 200
            assert (await signed_in.json())["user"]["email"] == email

            rejected = await client.post(
                "/api/email/login", json={"email": email, "password": "incorrect-password"}
            )
            assert rejected.status == 401
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.email == email))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
async def test_eduflow_telegram_login_is_scoped_to_its_bot_and_owner_list() -> None:
    telegram_id = 9900000000 + uuid4().int % 100000000
    ordinary_id = telegram_id + 1
    email = f"linked-{uuid4().hex}@example.test"
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        bot_token="1:ritm-token",
        eduflow_bot_token="2:eduflow-token",
        database_url=_URL,
        eduflow_owner_telegram_ids=str(telegram_id),
    )
    app = create_app(settings, sessions)
    try:
        async with TestClient(TestServer(app)) as client:
            legacy = await client.post(
                "/api/bootstrap", json={"initData": _init_data(telegram_id, settings.bot_token)}
            )
            assert legacy.status == 200
            assert "super_admin" not in (await legacy.json())["roles"]

            wrong_bot = await client.post(
                "/api/eduflow/telegram-login",
                json={"initData": _init_data(telegram_id, settings.bot_token)},
            )
            assert wrong_bot.status == 401

            accepted = await client.post(
                "/api/eduflow/telegram-login",
                json={"initData": _init_data(telegram_id, settings.eduflow_bot_token)},
            )
            assert accepted.status == 200
            body = await accepted.json()
            assert "super_admin" in body["roles"]

            linked = await client.post(
                "/api/email/link",
                headers={"Authorization": f"Bearer {body['token']}"},
                json={
                    "email": email,
                    "password": "correct-horse-battery",
                    "role": "teacher",
                },
            )
            assert linked.status == 200
            linked_body = await linked.json()
            assert linked_body["user"]["email"] == email
            assert "super_admin" in linked_body["roles"]

            email_login = await client.post(
                "/api/email/login",
                json={"email": email, "password": "correct-horse-battery"},
            )
            assert email_login.status == 200
            email_session = await email_login.json()
            assert "super_admin" in email_session["roles"]

            refreshed = await client.get(
                "/api/me", headers={"Authorization": f"Bearer {email_session['token']}"}
            )
            assert refreshed.status == 200
            assert "super_admin" in (await refreshed.json())["roles"]

            ordinary = await client.post(
                "/api/eduflow/telegram-login",
                json={"initData": _init_data(ordinary_id, settings.eduflow_bot_token)},
            )
            assert ordinary.status == 200
            assert "super_admin" not in (await ordinary.json())["roles"]
    finally:
        async with sessions() as session:
            await session.execute(
                delete(User).where(User.telegram_id.in_((telegram_id, ordinary_id)))
            )
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
async def test_email_login_rate_limit() -> None:
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(bot_token="1:ritm-token", database_url=_URL)
    app = create_app(settings, sessions)
    async with TestClient(TestServer(app)) as client:
        for _ in range(10):
            response = await client.post(
                "/api/email/login",
                json={"email": "absent@example.test", "password": "wrong-password"},
            )
            assert response.status == 401
            await response.read()
        limited = await client.post(
            "/api/email/login",
            json={"email": "absent@example.test", "password": "wrong-password"},
        )
        assert limited.status == 429
        await limited.read()
    await engine.dispose()
