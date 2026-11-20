"""In-memory chats waiting for the owner to confirm. Not a table (phase 1 schema)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class PendingChat:
    """A chat the bot was just added to, not yet linked."""

    telegram_chat_id: int
    title: str
    chat_type: str
    username: str | None
    added_by_telegram_id: int
    added_at: datetime


class PendingChatStore:
    """Process-local pending list. Lost on restart, which is acceptable in phase 1."""

    def __init__(self, ttl_hours: int = 24) -> None:
        self._ttl = timedelta(hours=ttl_hours)
        self._items: dict[int, PendingChat] = {}

    def put(self, item: PendingChat) -> None:
        """Remember or refresh a pending chat."""
        self._purge()
        self._items[item.telegram_chat_id] = item

    def pop(self, telegram_chat_id: int) -> PendingChat | None:
        """Remove and return one pending chat."""
        self._purge()
        return self._items.pop(telegram_chat_id, None)

    def get(self, telegram_chat_id: int) -> PendingChat | None:
        """Return one pending chat without removing it."""
        self._purge()
        return self._items.get(telegram_chat_id)

    def list_for(self, telegram_user_id: int) -> list[PendingChat]:
        """Pending chats added by this Telegram user."""
        self._purge()
        rows = [row for row in self._items.values() if row.added_by_telegram_id == telegram_user_id]
        rows.sort(key=lambda row: row.added_at, reverse=True)
        return rows

    def _purge(self) -> None:
        cutoff = datetime.now(UTC) - self._ttl
        stale = [key for key, row in self._items.items() if row.added_at < cutoff]
        for key in stale:
            self._items.pop(key, None)
