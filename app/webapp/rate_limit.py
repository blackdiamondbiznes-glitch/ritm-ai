"""In-memory request counters. Process-local and good enough for a single bot."""

from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    """Allow `limit` events per `window` seconds for each key."""

    def __init__(self, limit: int = 120, window: int = 60) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        """True when this hit is within the budget. False means 429."""
        stamp = now if now is not None else time.monotonic()
        start = stamp - self.window
        recent = [item for item in self._hits[key] if item > start]
        if len(recent) >= self.limit:
            self._hits[key] = recent
            return False
        recent.append(stamp)
        self._hits[key] = recent
        return True
