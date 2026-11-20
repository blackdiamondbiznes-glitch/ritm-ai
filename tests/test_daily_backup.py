"""Daily database backup: due rule, libpq env, a real pg_dump, and delivery to admins."""

import os
from datetime import UTC, datetime, time
from pathlib import Path

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendDocument
from app.config import Settings
from app.db.models.system_state import SystemState
from app.jobs.backup import DailyBackup
from app.ops.backup import BackupError, pg_env, run_pg_dump
from app.services.backup import BACKUP_DAY, BACKUP_RESULT, backup_due
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
pg = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
AT = time(4, 0)


def test_backup_is_due_once_per_tashkent_day() -> None:
    before = datetime(2026, 11, 21, 22, 59, tzinfo=UTC)  # 03:59 Tashkent on the 22nd
    after = datetime(2026, 11, 21, 23, 0, tzinfo=UTC)  # 04:00 Tashkent on the 22nd
    assert backup_due(before, AT, None) is None
    assert backup_due(after, AT, "2026-11-21") == "2026-11-22"
    assert backup_due(after, AT, "2026-11-22") is None
    late = datetime(2026, 11, 22, 18, 0, tzinfo=UTC)  # 23:00 Tashkent, missed 04:00
    assert backup_due(late, AT, "2026-11-21") == "2026-11-22"


def test_pg_env_keeps_password_out_of_the_url() -> None:
    env = pg_env("postgresql+asyncpg://ritm:s3cr%40t@dpg-x-a.frankfurt-postgres.render.com/ritm")
    assert env == {
        "PGHOST": "dpg-x-a.frankfurt-postgres.render.com",
        "PGPORT": "5432",
        "PGUSER": "ritm",
        "PGPASSWORD": "s3cr@t",
        "PGDATABASE": "ritm",
    }
    assert pg_env("postgresql+asyncpg://u:p@h:6543/d?ssl=require")["PGSSLMODE"] == "require"
    assert "PGSSLMODE" not in pg_env("postgresql+asyncpg://u:p@h/d")


async def test_missing_binary_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(BackupError) as info:
        await run_pg_dump(_URL, tmp_path / "x.dump", 5, binary="pg_dump_does_not_exist")
    assert info.value.code == "missing"


@pg
async def test_real_pg_dump_writes_a_custom_format_file(tmp_path: Path) -> None:
    target = tmp_path / "ritm.dump"
    size = await run_pg_dump(_URL, target, 120)
    assert size > 0 and target.read_bytes()[:5] == b"PGDMP"


@pg
async def test_bad_password_reports_exit_without_leaking(tmp_path: Path) -> None:
    url = _URL.replace("bot:bot@", "bot:WrongPass123@")
    with pytest.raises(BackupError) as info:
        await run_pg_dump(url, tmp_path / "x.dump", 60)
    assert info.value.code == "exit" and "WrongPass123" not in info.value.detail


class _Bot:
    def __init__(self, fail_for: int | None = None) -> None:
        self.documents: list[tuple[int, str, bytes, str]] = []
        self.messages: list[tuple[int, str]] = []
        self.fail_for = fail_for

    async def send_document(self, chat_id, document, caption=None):
        if chat_id == self.fail_for:
            raise TelegramForbiddenError(SendDocument(chat_id=chat_id, document="x"), "blocked")
        data = Path(document.path).read_bytes()
        self.documents.append((chat_id, document.filename, data, caption))

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))


@pytest.fixture
async def sessions():
    engine = create_async_engine(_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def clear() -> None:
        async with factory() as s:
            await s.execute(delete(SystemState).where(SystemState.key.like("backup_%")))
            await s.commit()

    await clear()
    try:
        yield factory
    finally:
        await clear()
        await engine.dispose()


def _settings(**kw) -> Settings:
    base = {"bot_token": "1:x", "database_url": _URL, "super_admin_ids": "111,222"}
    return Settings(_env_file=None, **{**base, **kw})


async def _state(sessions, key: str) -> str | None:
    async with sessions() as s:
        row = await s.scalar(select(SystemState).where(SystemState.key == key))
        return None if row is None else row.value


async def _fake_dump(url: str, path: Path, timeout: float) -> int:
    path.write_bytes(b"PGDMP-fake")
    return path.stat().st_size


@pg
async def test_backup_runs_once_a_day_and_reaches_admins(sessions) -> None:
    bot = _Bot(fail_for=222)
    now = datetime(2026, 11, 21, 23, 30, tzinfo=UTC)
    job = DailyBackup(sessions, bot, _settings(), now=lambda: now, dump=_fake_dump)
    await job.run()
    await job.run()  # same day: no second dump
    assert [(c, f, d) for c, f, d, _ in bot.documents] == [
        (111, "ritm-2026-11-22.dump", b"PGDMP-fake")
    ]
    assert "2026-11-22" in bot.documents[0][3]
    assert await _state(sessions, BACKUP_DAY) == "2026-11-22"
    assert await _state(sessions, BACKUP_RESULT) == "sent:1"
    paths = list(Path("/tmp").glob("ritm-backup-*/ritm-2026-11-22.dump"))
    assert paths == []  # temp file removed


@pg
async def test_oversize_and_failure_send_alerts(sessions) -> None:
    async def big(url: str, path: Path, timeout: float) -> int:
        path.write_bytes(b"x" * 2048)
        return 50 * 1024 * 1024

    async def broken(url: str, path: Path, timeout: float) -> int:
        raise BackupError("exit", "boom")

    bot = _Bot()
    job = DailyBackup(sessions, bot, _settings(), dump=big)
    assert await job.backup_now("2026-11-22") == "too_big"
    assert bot.documents == [] and len(bot.messages) == 2 and "50.0" in bot.messages[0][1]
    job = DailyBackup(sessions, bot, _settings(), dump=broken)
    assert await job.backup_now("2026-11-22") == "failed:exit"
    assert "exit" in bot.messages[-1][1] and await _state(sessions, BACKUP_RESULT) == "failed:exit"


@pg
async def test_backup_waits_for_the_configured_hour(sessions) -> None:
    bot = _Bot()
    early = datetime(2026, 11, 21, 22, 0, tzinfo=UTC)  # 03:00 Tashkent
    await DailyBackup(sessions, bot, _settings(), now=lambda: early, dump=_fake_dump).run()
    assert bot.documents == [] and await _state(sessions, BACKUP_DAY) is None
