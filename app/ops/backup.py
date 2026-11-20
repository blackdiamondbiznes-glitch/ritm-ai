"""Backup helpers. Never log the database password or a full DSN."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse


def dump_dsn(database_url: str) -> str:
    """Turn a SQLAlchemy URL into a libpq URL. The password stays in the result."""
    raw = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    raw = raw.replace("postgresql+psycopg://", "postgresql://", 1)
    return raw


def parse_dsn(database_url: str) -> dict[str, str]:
    """Split a URL into connection fields. Caller must not print the password."""
    parsed = urlparse(dump_dsn(database_url))
    return {
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "database": (parsed.path or "/").lstrip("/") or "postgres",
    }


def prune_backups(directory: Path, retention_days: int, now: datetime | None = None) -> list[Path]:
    """Delete ritm-*.dump files older than the retention window."""
    if retention_days <= 0:
        return []
    stamp = now or datetime.now(UTC)
    cutoff = stamp - timedelta(days=retention_days)
    deleted: list[Path] = []
    if not directory.is_dir():
        return deleted
    for path in directory.glob("ritm-*.dump"):
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if mtime < cutoff:
            path.unlink()
            deleted.append(path)
    return deleted
