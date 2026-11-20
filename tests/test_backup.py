"""Backup retention must drop only old dump files."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.ops.backup import parse_dsn, prune_backups


def test_prune_backups_respects_retention(tmp_path: Path) -> None:
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    keep = tmp_path / "ritm-20261118-120000.dump"
    drop = tmp_path / "ritm-20261001-120000.dump"
    other = tmp_path / "notes.txt"
    keep.write_bytes(b"ok")
    drop.write_bytes(b"old")
    other.write_text("leave")
    old = (now - timedelta(days=20)).timestamp()
    fresh = (now - timedelta(days=2)).timestamp()
    import os

    os.utime(drop, (old, old))
    os.utime(keep, (fresh, fresh))
    deleted = prune_backups(tmp_path, 14, now=now)
    assert drop in deleted
    assert not drop.exists()
    assert keep.exists()
    assert other.exists()


def test_parse_dsn_strips_the_asyncpg_driver() -> None:
    fields = parse_dsn("postgresql+asyncpg://bot:secret@postgres:5432/engagement")
    assert fields["user"] == "bot"
    assert fields["password"] == "secret"
    assert fields["host"] == "postgres"
    assert fields["port"] == "5432"
    assert fields["database"] == "engagement"
