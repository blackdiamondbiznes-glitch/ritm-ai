"""Per-user preferences shared by the bot and the Mini App (one place for validation)."""

from __future__ import annotations

from typing import Any

from app.db.models.users import User
from app.services.profiles import LANGUAGES, TIMEZONES

UI_LANGUAGES = ("uz", "ru", "en")
NOTIFY_KEYS = ("notify_reports", "notify_expiry")


class PrefsError(Exception):
    """Invalid preference input. `code` is `choice` or `bad_request`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def needs_language(user: User) -> bool:
    """True until the user has picked a UI language (new users only)."""
    return not bool(getattr(user, "ui_language_set", True))


def set_language(user: User, code: str) -> None:
    """Save the UI language. Raises PrefsError for unknown codes."""
    if code not in UI_LANGUAGES or code not in LANGUAGES:
        raise PrefsError("choice")
    user.language_code = code
    user.ui_language_set = True


def default_zone(user: User | None, fallback: str) -> str:
    """The user's preferred zone for new chat profiles, else the configured default."""
    zone = getattr(user, "default_timezone", None) if user is not None else None
    return zone if zone in TIMEZONES else fallback


def prefs_payload(user: User, fallback_zone: str) -> dict[str, Any]:
    return {
        "language": user.language_code or "uz",
        "languages": list(UI_LANGUAGES),
        "default_timezone": default_zone(user, fallback_zone),
        "timezones": sorted(TIMEZONES),
        "notify_reports": bool(user.notify_reports),
        "notify_expiry": bool(user.notify_expiry),
    }


def update_prefs(user: User, body: dict[str, Any]) -> None:
    """Apply a partial update. Validates everything before changing anything."""
    if not isinstance(body, dict):
        raise PrefsError("bad_request")
    changes: dict[str, Any] = {}
    if "language" in body:
        code = body["language"]
        if not isinstance(code, str) or code not in UI_LANGUAGES:
            raise PrefsError("choice")
        changes["language"] = code
    if "default_timezone" in body:
        zone = body["default_timezone"]
        if not isinstance(zone, str) or zone not in TIMEZONES:
            raise PrefsError("choice")
        changes["default_timezone"] = zone
    for key in NOTIFY_KEYS:
        if key in body:
            if not isinstance(body[key], bool):
                raise PrefsError("bad_request")
            changes[key] = body[key]
    if "language" in changes:
        set_language(user, changes.pop("language"))
    for key, value in changes.items():
        setattr(user, key, value)
