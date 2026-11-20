"""Daily pg_dump sent to super admins as a Telegram document.

The scheduler only wakes `DailyBackup.run`; the due rule lives in services/backup.py
and the dump itself in ops/backup.py. Credentials go to pg_dump via PG* env vars.
"""

import asyncio
import logging
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repositories.system_state import SystemStateRepository
from app.db.repositories.users import UserRepository
from app.i18n import t
from app.ops.backup import BackupError, run_pg_dump
from app.services.backup import BACKUP_DAY, BACKUP_RESULT, backup_due
from app.services.clock import Clock, utcnow

logger = logging.getLogger(__name__)
Dump = Callable[[str, Path, float], Awaitable[int]]
_MB = 1024 * 1024
_MAX_WAIT = 60


class DailyBackup:
    """Claim today's slot in system_state, dump, send, delete the temp file."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        bot: Bot,
        settings: Settings,
        now: Clock | None = None,
        dump: Dump = run_pg_dump,
    ) -> None:
        self._sessions = sessions
        self._bot = bot
        self._settings = settings
        self._now = now or utcnow
        self._dump = dump

    async def run(self) -> None:
        """Scheduler entry. Never raises."""
        try:
            day = await self._claim()
            if day is not None:
                await self.backup_now(day)
        except Exception:
            logger.exception("backup run failed")

    async def backup_now(self, day: str) -> str:
        """Dump and deliver. Returns sent:N, too_big or failed:<code>."""
        langs = await self._admin_langs()
        with tempfile.TemporaryDirectory(prefix="ritm-backup-") as tmp:
            path = Path(tmp) / f"ritm-{day}.dump"
            try:
                size = await self._dump(
                    self._settings.database_url, path, self._settings.backup_timeout_seconds
                )
            except BackupError as exc:
                logger.warning("backup failed code=%s detail=%s", exc.code, exc.detail)
                await self._tell(langs, "backup_failed", code=exc.code)
                return await self._record(f"failed:{exc.code}")
            mb = round(size / _MB, 1)
            if size > self._settings.backup_max_mb * _MB:
                logger.warning("backup too big bytes=%s", size)
                await self._tell(langs, "backup_too_big", mb=mb, max=self._settings.backup_max_mb)
                return await self._record("too_big")
            sent = 0
            for telegram_id, lang in langs.items():
                caption = t("backup_caption", lang, day=day, mb=mb)
                sent += await self._send_file(telegram_id, path, caption)
        logger.info("backup sent day=%s bytes=%s admins=%s", day, size, sent)
        return await self._record(f"sent:{sent}")

    async def _claim(self) -> str | None:
        async with self._sessions() as session:
            state = SystemStateRepository(session)
            day = backup_due(self._now(), self._settings.backup_clock, await state.get(BACKUP_DAY))
            if day is None:
                return None
            await state.put(BACKUP_DAY, day)
            await session.commit()
            return day

    async def _record(self, result: str) -> str:
        async with self._sessions() as session:
            await SystemStateRepository(session).put(BACKUP_RESULT, result)
            await session.commit()
        return result

    async def _admin_langs(self) -> dict[int, str]:
        langs: dict[int, str] = {}
        async with self._sessions() as session:
            users = UserRepository(session)
            for telegram_id in sorted(self._settings.admin_ids):
                user = await users.get_by_telegram_id(telegram_id)
                langs[telegram_id] = user.language_code if user and user.language_code else "uz"
        return langs

    async def _tell(self, langs: dict[int, str], key: str, **params: object) -> None:
        for telegram_id, lang in langs.items():
            try:
                await self._bot.send_message(telegram_id, t(key, lang, **params))
            except TelegramAPIError:
                logger.info("backup notice not delivered telegram_id=%s", telegram_id)

    async def _send_file(self, telegram_id: int, path: Path, caption: str) -> int:
        for attempt in range(2):
            try:
                await self._bot.send_document(
                    telegram_id, FSInputFile(path, filename=path.name), caption=caption
                )
                return 1
            except TelegramRetryAfter as exc:
                if attempt:
                    break
                await asyncio.sleep(min(int(exc.retry_after), _MAX_WAIT))
            except TelegramAPIError:
                break
        logger.info("backup not delivered telegram_id=%s", telegram_id)
        return 0


def schedule_backup(scheduler: object, backup: DailyBackup, seconds: int = 60) -> None:
    """Wake the backup check every minute; it runs at most once per local day."""
    scheduler.add_job(backup.run, "interval", seconds=seconds, max_instances=1, coalesce=True)
