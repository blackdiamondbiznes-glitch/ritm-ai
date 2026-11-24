"""Telegram initData HMAC checks and short-lived session tokens."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_SKEW_SECONDS = 60


class AuthError(Exception):
    """initData or the session token was rejected. `code` is a stable machine tag."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age: int,
    now: int | None = None,
) -> dict[str, object]:
    """Return parsed fields when the HMAC and auth_date are valid."""
    if not init_data or not bot_token:
        raise AuthError("invalid")
    fields = dict(parse_qsl(init_data, strict_parsing=False, keep_blank_values=True))
    received = fields.pop("hash", "")
    if not received:
        raise AuthError("invalid")
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise AuthError("tampered")
    try:
        auth_date = int(fields.get("auth_date", ""))
    except ValueError as exc:
        raise AuthError("invalid") from exc
    stamp = now if now is not None else int(time.time())
    if auth_date > stamp + MAX_SKEW_SECONDS:
        raise AuthError("expired")
    if max_age >= 0 and stamp - auth_date > max_age:
        raise AuthError("expired")
    return _decorate(fields)


def _decorate(fields: dict[str, str]) -> dict[str, object]:
    parsed: dict[str, object] = dict(fields)
    raw_user = fields.get("user")
    if raw_user:
        try:
            user = json.loads(raw_user)
        except json.JSONDecodeError as exc:
            raise AuthError("invalid") from exc
        if not isinstance(user, dict) or "id" not in user:
            raise AuthError("invalid")
        parsed["user"] = user
    return parsed


def telegram_user_id(fields: dict[str, object]) -> int:
    """Extract the Telegram user id from validated initData."""
    user = fields.get("user")
    if isinstance(user, dict) and user.get("id") is not None:
        try:
            return int(user["id"])
        except (TypeError, ValueError) as exc:
            raise AuthError("invalid") from exc
    raise AuthError("invalid")


def issue_session(telegram_id: int, secret: str, ttl: int, *, now: int | None = None) -> str:
    """Sign a telegram_id and expiry. The secret never appears in the token body."""
    exp = (now if now is not None else int(time.time())) + max(60, ttl)
    payload = f"{telegram_id}:{exp}"
    return f"{payload}:{_sign(payload, secret)}"


def read_session(token: str, secret: str, *, now: int | None = None) -> int:
    """Return the telegram_id when the signature is valid and the token is fresh."""
    if not token or not secret or token.count(":") != 2:
        raise AuthError("unauthorized")
    user_s, exp_s, signature = token.split(":")
    payload = f"{user_s}:{exp_s}"
    if not hmac.compare_digest(_sign(payload, secret), signature):
        raise AuthError("unauthorized")
    try:
        telegram_id = int(user_s)
        exp = int(exp_s)
    except ValueError as exc:
        raise AuthError("unauthorized") from exc
    stamp = now if now is not None else int(time.time())
    if exp < stamp:
        raise AuthError("unauthorized")
    return telegram_id


def issue_account_session(user_id: int, secret: str, ttl: int, *, now: int | None = None) -> str:
    """Sign an internal account id without colliding with legacy Telegram sessions."""
    exp = (now if now is not None else int(time.time())) + max(60, ttl)
    payload = f"account:{user_id}:{exp}"
    return f"{payload}:{_sign(payload, secret)}"


def read_account_session(token: str, secret: str, *, now: int | None = None) -> int:
    """Return the internal account id when a hybrid account token is valid."""
    if not token or not secret or token.count(":") != 3:
        raise AuthError("unauthorized")
    kind, user_s, exp_s, signature = token.split(":")
    payload = f"{kind}:{user_s}:{exp_s}"
    if kind != "account" or not hmac.compare_digest(_sign(payload, secret), signature):
        raise AuthError("unauthorized")
    try:
        user_id = int(user_s)
        exp = int(exp_s)
    except ValueError as exc:
        raise AuthError("unauthorized") from exc
    stamp = now if now is not None else int(time.time())
    if user_id <= 0 or exp < stamp:
        raise AuthError("unauthorized")
    return user_id


def session_secret(bot_token: str, configured: str = "") -> str:
    """Use an explicit secret when set, otherwise derive one from the bot token."""
    if configured.strip():
        return configured.strip()
    return hmac.new(b"ritm-webapp-session", bot_token.encode(), hashlib.sha256).hexdigest()


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
