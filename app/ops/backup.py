"""Backup helpers. Never log the database password or a full DSN."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

_SSL_OFF = {"", "disable", "false", "0"}


class BackupError(Exception):
    """pg_dump could not produce a file. `code` is safe to log; `detail` has no password."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


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


def pg_env(database_url: str) -> dict[str, str]:
    """libpq environment for pg_dump. The password travels in PGPASSWORD, never in argv."""
    fields = parse_dsn(database_url)
    env = {
        "PGHOST": fields["host"],
        "PGPORT": fields["port"],
        "PGUSER": fields["user"],
        "PGPASSWORD": fields["password"],
        "PGDATABASE": fields["database"],
    }
    query = dict(parse_qsl(urlparse(dump_dsn(database_url)).query))
    ssl = (query.get("sslmode") or query.get("ssl") or "").lower()
    if ssl not in _SSL_OFF:
        env["PGSSLMODE"] = "require" if ssl in {"true", "1", "prefer", "allow"} else ssl
    return env


async def run_pg_dump(
    database_url: str, target: Path, timeout: float, binary: str = "pg_dump"
) -> int:
    """Write a compressed custom-format dump to `target` and return its size in bytes."""
    secrets = pg_env(database_url)
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "--format=custom",
            "--compress=6",
            "--no-owner",
            "--no-acl",
            f"--file={target}",
            env={**os.environ, **secrets},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise BackupError("missing") from exc
    try:
        _out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise BackupError("timeout") from exc
    if proc.returncode != 0:
        raise BackupError("exit", _clean(err, secrets["PGPASSWORD"]))
    return target.stat().st_size


def _clean(stderr: bytes | None, password: str) -> str:
    """Last stderr line, short, with the password removed just in case."""
    lines = (stderr or b"").decode("utf-8", "replace").strip().splitlines()
    text = lines[-1] if lines else ""
    if password:
        text = text.replace(password, "***")
    return text[:200]
