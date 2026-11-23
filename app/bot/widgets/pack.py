"""Load widget HTML and check the official size limits."""

from __future__ import annotations

import zlib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_LIMIT = 32768
ZLIB_LIMIT = 4096
KINDS = ("lesson", "fee", "attendance", "enroll", "plan", "report", "digest")


class WidgetHtmlError(ValueError):
    """The HTML is missing or larger than Telegram allows."""


@lru_cache
def load(kind: str) -> str:
    """Return the HTML for one card. The compressed size is checked once."""
    if kind not in KINDS:
        raise WidgetHtmlError(kind)
    path = ROOT / f"{kind}.html"
    html = path.read_text(encoding="utf-8")
    raw = html.encode("utf-8")
    if b"\x00" in raw or len(raw) > RAW_LIMIT:
        raise WidgetHtmlError(kind)
    packed = len(zlib.compress(raw, 9))
    if packed > ZLIB_LIMIT:
        raise WidgetHtmlError(kind)
    return html


def sizes(kind: str) -> tuple[int, int]:
    """Raw UTF-8 length and zlib-9 length, for tests."""
    raw = load(kind).encode("utf-8")
    return len(raw), len(zlib.compress(raw, 9))
