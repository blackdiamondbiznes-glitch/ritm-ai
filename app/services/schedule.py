"""Owner-facing daily schedule and the manual 'write now' job."""

from datetime import UTC, datetime, time

from app.db.models.chats import Chat
from app.db.models.jobs import Job, JobStatus
from app.db.models.schedules import Schedule
from app.db.models.users import User
from app.db.repositories.jobs import DAILY, JobRepository
from app.db.repositories.schedules import ScheduleRepository
from app.services.access import AccessService
from app.services.leaderboard import MODULE as LEADERBOARD
from app.services.profiles import ProfileService

TIMES: dict[str, time] = {
    "0800": time(8, 0),
    "0900": time(9, 0),
    "1200": time(12, 0),
    "1800": time(18, 0),
    "2100": time(21, 0),
}


class ScheduleService:
    """Saves the clock time and enqueues an immediate daily job."""

    def __init__(
        self,
        schedules: ScheduleRepository,
        jobs: JobRepository,
        access: AccessService,
        profiles: ProfileService,
        default_time: time | None = None,
    ) -> None:
        self._schedules = schedules
        self._jobs = jobs
        self._access = access
        self._profiles = profiles
        self._default_time = default_time or TIMES["0900"]

    async def get(self, chat_id: int, module: str = DAILY) -> Schedule | None:
        """Return the saved schedule for one module."""
        return await self._schedules.get(chat_id, module)

    async def set_time(self, chat: Chat, code: str, module: str = DAILY) -> Schedule | None:
        """Turn a module on at a known local time. Unknown codes do nothing."""
        moment = parse_clock(code)
        if moment is None:
            return await self._schedules.get(chat.id, module)
        current = await self._schedules.get(chat.id, module)
        return await self._schedules.upsert(
            chat.id, moment, True, module, days=_default_days(module, current)
        )

    async def set_enabled(self, chat: Chat, enabled: bool, module: str = DAILY) -> Schedule | None:
        """Pause or resume. The clock time is kept."""
        current = await self._schedules.get(chat.id, module)
        moment = current.time_of_day if current is not None else self._default_time
        days = _default_days(module, current)
        return await self._schedules.upsert(chat.id, moment, enabled, module, days=days)

    async def set_weekday(
        self, chat: Chat, weekday: int, module: str = LEADERBOARD
    ) -> Schedule | None:
        """Set a single weekday and turn the weekly announcement on."""
        if weekday < 1 or weekday > 7:
            return await self._schedules.get(chat.id, module)
        current = await self._schedules.get(chat.id, module)
        moment = current.time_of_day if current is not None else self._default_time
        return await self._schedules.upsert(chat.id, moment, True, module, days=[weekday])

    async def enqueue_now(
        self,
        owner: User,
        chat: Chat,
        module: str = DAILY,
        extra: dict[str, object] | None = None,
    ) -> str:
        """Queue one job. Returns queued, profile, quota, module or inactive."""
        reason = await self._block(owner, chat, module)
        if reason is not None:
            return reason
        slot = "m" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        await self._jobs.add(_job(chat.id, slot, module, extra))
        return "queued"

    async def _block(self, owner: User, chat: Chat, module: str) -> str | None:
        if not chat.is_active:
            return "inactive"
        if await self._profiles.get(chat.id) is None:
            return "profile"
        if not await self._access.is_module_allowed(chat, module):
            return "module"
        if module != LEADERBOARD and await self._access.remaining_ai_quota(owner) <= 0:
            return "quota"
        return None


def _job(chat_id: int, slot: str, module: str, extra: dict[str, object] | None = None) -> Job:
    payload: dict[str, object] = {"slot": slot, "schedule_id": None}
    if extra:
        payload.update(extra)
    return Job(
        chat_id=chat_id,
        type=module,
        payload=payload,
        run_at=datetime.now(UTC),
        status=JobStatus.PENDING,
        attempts=0,
        max_attempts=5,
    )


def _default_days(module: str, current: Schedule | None) -> list[int] | None:
    if current is not None:
        return None
    if module == LEADERBOARD:
        return [1]
    return None


def parse_clock(code: str) -> time | None:
    """Accept preset codes such as 0900, or any valid HH:MM / HHMM clock."""
    raw = (code or "").strip()
    if raw in TIMES:
        return TIMES[raw]
    compact = raw.replace(":", "").replace(".", "")
    if compact in TIMES:
        return TIMES[compact]
    if compact.isdigit() and 3 <= len(compact) <= 4:
        compact = compact.zfill(4)
        hours, minutes = int(compact[:2]), int(compact[2:])
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return time(hours, minutes)
    return None
