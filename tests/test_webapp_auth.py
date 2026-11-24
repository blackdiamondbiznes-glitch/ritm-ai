"""Telegram initData HMAC and Mini App session tokens."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.webapp.auth import (
    AuthError,
    issue_account_session,
    issue_session,
    read_account_session,
    read_session,
    session_secret,
    telegram_user_id,
    validate_init_data,
)

TOKEN = "123456:TEST-bot-token"
NOW = 1_700_000_000


def _signed(fields: dict[str, str], *, token: str = TOKEN, digest: str | None = None) -> str:
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    hashed = digest or hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields) + "&hash=" + hashed


def _fields(auth_date: int = NOW - 60) -> dict[str, str]:
    user = {"id": 9700000001, "first_name": "Test", "username": "test_user", "language_code": "uz"}
    encoded = json.dumps(user, separators=(",", ":"))
    return {"auth_date": str(auth_date), "query_id": "AAE", "user": encoded}


def test_valid_init_data_returns_the_telegram_user() -> None:
    parsed = validate_init_data(_signed(_fields()), TOKEN, max_age=86400, now=NOW)
    assert telegram_user_id(parsed) == 9700000001
    assert parsed["user"]["username"] == "test_user"


def test_tampered_init_data_is_rejected() -> None:
    raw = _signed(_fields(), digest="0" * 64)
    try:
        validate_init_data(raw, TOKEN, max_age=86400, now=NOW)
    except AuthError as exc:
        assert exc.code == "tampered"
    else:
        raise AssertionError("tampered")


def test_expired_init_data_is_rejected() -> None:
    raw = _signed(_fields(auth_date=NOW - 90_000))
    try:
        validate_init_data(raw, TOKEN, max_age=86400, now=NOW)
    except AuthError as exc:
        assert exc.code == "expired"
    else:
        raise AssertionError("expired")


def test_session_token_roundtrip_and_expiry() -> None:
    secret = session_secret(TOKEN, "")
    token = issue_session(42, secret, ttl=60, now=NOW)
    assert read_session(token, secret, now=NOW) == 42
    try:
        read_session(token, secret, now=NOW + 120)
    except AuthError as exc:
        assert exc.code == "unauthorized"
    else:
        raise AssertionError("expired session")
    try:
        read_session(token[:-2] + "ab", secret, now=NOW)
    except AuthError as exc:
        assert exc.code == "unauthorized"
    else:
        raise AssertionError("tampered session")


def test_account_session_is_distinct_from_legacy_telegram_session() -> None:
    secret = session_secret(TOKEN, "")
    token = issue_account_session(42, secret, ttl=60, now=NOW)
    assert read_account_session(token, secret, now=NOW) == 42
    try:
        read_session(token, secret, now=NOW)
    except AuthError as exc:
        assert exc.code == "unauthorized"
    else:
        raise AssertionError("account token accepted as Telegram token")
    try:
        read_account_session(token[:-2] + "ab", secret, now=NOW)
    except AuthError as exc:
        assert exc.code == "unauthorized"
    else:
        raise AssertionError("tampered account token")


def test_time_is_not_used_as_auth_date_when_signing() -> None:
    # A blank init string is invalid, not expired.
    try:
        validate_init_data("", TOKEN, max_age=1, now=int(time.time()))
    except AuthError as exc:
        assert exc.code == "invalid"
    else:
        raise AssertionError("invalid")
