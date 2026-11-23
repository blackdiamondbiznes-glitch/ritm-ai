"""Online lesson links (Zoom, Meet, Teams...). Only plain http(s) URLs are kept."""

from __future__ import annotations

from urllib.parse import urlsplit

URL_MAX = 500


def clean_meeting_url(value: object) -> str | None:
    """Return a trimmed http(s) URL, None for empty, or raise ValueError."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("link")
    text = value.strip()
    if not text:
        return None
    if len(text) > URL_MAX or any(ch.isspace() for ch in text):
        raise ValueError("link")
    parts = urlsplit(text)
    if (
        parts.scheme.lower() not in {"http", "https"}
        or not parts.hostname
        or "." not in parts.hostname
    ):
        raise ValueError("link")
    return text
