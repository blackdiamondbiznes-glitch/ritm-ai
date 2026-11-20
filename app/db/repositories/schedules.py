"""Schedule queries."""

from dataclasses import dataclass
from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chats import Chat, ChatProfile
from app.db.models.schedules import Schedule

MODULE = "daily_content"
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]


@dataclass(frozen=True)
class DueRow:
    """What the planner needs. No ORM object leaves the repository."""

    schedule_id: int
    chat_id: int
    timezone: str
    time_of_day: time
    days: tuple[int, ...]
    module: str


class ScheduleRepository:
    """Read and upsert daily schedules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, chat_id: int, module: str = MODULE) -> Schedule | None:
        """Return the schedule for one chat and module."""
        stmt = select(Schedule).where(Schedule.chat_id == chat_id, Schedule.module == module)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        chat_id: int,
        time_of_day: time,
        enabled: bool,
        module: str = MODULE,
        days: list[int] | None = None,
    ) -> Schedule:
        """Create or update one module slot. `days` is kept when omitted."""
        row = await self.get(chat_id, module)
        if row is None:
            row = Schedule(
                chat_id=chat_id,
                module=module,
                time_of_day=time_of_day,
                days_of_week=list(days or ALL_DAYS),
                enabled=enabled,
            )
            self._session.add(row)
        else:
            row.time_of_day = time_of_day
            row.enabled = enabled
            if days is not None:
                row.days_of_week = list(days)
        await self._session.flush()
        return row

    async def list_due_rows(self) -> list[DueRow]:
        """Enabled daily and quiz schedules on active chats that have a profile."""
        stmt = (
            select(Schedule, ChatProfile.timezone)
            .join(Chat, Chat.id == Schedule.chat_id)
            .join(ChatProfile, ChatProfile.chat_id == Schedule.chat_id)
            .where(
                Schedule.enabled.is_(True),
                Schedule.module.in_((MODULE, "quiz", "leaderboard")),
                Chat.is_active.is_(True),
            )
        )
        result = await self._session.execute(stmt)
        return [_due(row, zone) for row, zone in result.all()]


def _due(row: Schedule, zone: str) -> DueRow:
    days = tuple(int(day) for day in row.days_of_week)
    return DueRow(row.id, row.chat_id, zone, row.time_of_day, days, row.module)
