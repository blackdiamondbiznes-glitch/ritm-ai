"""Operational health snapshot for the admin screen and the HTTP probe."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.jobs import JobRepository
from app.db.repositories.system_state import SystemStateRepository
from app.services.clock import Clock, utcnow

LAST_TICK = "last_tick_at"


@dataclass(frozen=True)
class HealthReport:
    """Numbers shown on the system-status screen."""

    db_ok: bool
    db_ms: int | None
    last_tick_at: datetime | None
    tick_age_seconds: int | None
    provider: str
    model: str
    ai_configured: bool
    pending_jobs: int
    failed_24h: int

    @property
    def ok(self) -> bool:
        return self.db_ok and self.ai_configured


class HealthService:
    """Probe the database, last tick, AI config and the job queue."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        now: Clock | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._now = now or utcnow

    async def report(self) -> HealthReport:
        """Collect one snapshot. Failures in one probe do not hide the others."""
        db_ok, db_ms = await self._db()
        last = await self._last_tick()
        now = self._now()
        age = None if last is None else max(0, int((now - last).total_seconds()))
        pending = 0
        failed = 0
        if db_ok:
            jobs = JobRepository(self._session)
            pending = await jobs.count_pending()
            failed = await jobs.count_failed_since(now - timedelta(hours=24))
        return HealthReport(
            db_ok=db_ok,
            db_ms=db_ms,
            last_tick_at=last,
            tick_age_seconds=age,
            provider=self._settings.ai_provider,
            model=self._model(),
            ai_configured=self._ai_configured(),
            pending_jobs=pending,
            failed_24h=failed,
        )

    async def _db(self) -> tuple[bool, int | None]:
        started = perf_counter()
        try:
            await self._session.execute(text("SELECT 1"))
        except Exception:
            return False, None
        return True, int((perf_counter() - started) * 1000)

    async def _last_tick(self) -> datetime | None:
        row = await SystemStateRepository(self._session, now=self._now).get_row(LAST_TICK)
        if row is None:
            return None
        try:
            return datetime.fromisoformat(row.value)
        except ValueError:
            return row.updated_at

    def _model(self) -> str:
        if self._settings.ai_provider == "openai":
            return self._settings.openai_model
        return self._settings.gemini_model

    def _ai_configured(self) -> bool:
        if self._settings.ai_provider == "openai":
            return bool(self._settings.openai_api_key.strip())
        return bool(self._settings.gemini_api_key.strip())
