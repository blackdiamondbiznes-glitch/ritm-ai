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
        eduflow_bot_token="",
    )
    app = create_app(settings, None)

    async with TestClient(TestServer(app)) as client:
        response = await client.post("/api/eduflow/bootstrap", json={"initData": "bad"})
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
async def test_eduflow_bootstrap_uses_its_bot_and_maps_the_super_admin() -> None:
    telegram_id = 9900000000 + uuid4().int % 100000000
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        bot_token="1:ritm-token",
        eduflow_bot_token="2:eduflow-token",
        database_url=_URL,
        super_admin_ids=str(telegram_id),
    )
    app = create_app(settings, sessions)
    try:
        async with TestClient(TestServer(app)) as client:
            wrong_bot = await client.post(
                "/api/eduflow/bootstrap",
                json={"initData": _init_data(telegram_id, settings.bot_token)},
            )
            assert wrong_bot.status == 401

            accepted = await client.post(
                "/api/eduflow/bootstrap",
                json={"initData": _init_data(telegram_id, settings.eduflow_bot_token)},
            )
            assert accepted.status == 200
            body = await accepted.json()
            assert "super_admin" in body["roles"]
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()
