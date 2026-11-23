"""Fill group sessions once per Asia/Tashkent day. The claim shares the tick transaction."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.system_state import SystemStateRepository
from app.services.clock import Clock, utcnow
from app.services.sessions import KIND, SessionPlanner, sessions_due

logger = logging.getLogger(__name__)


async def refill_sessions(session: AsyncSession, now: Clock | None = None) -> bool:
    """Fill every group when this Tashkent day has not been claimed yet."""
    clock = now or utcnow
    state = SystemStateRepository(session, clock)
    day = sessions_due(clock(), await state.get(KIND))
    if day is None:
        return False
    await state.put(KIND, day)
    added = await SessionPlanner(
        LessonRepository(session), GroupRepository(session), now=clock
    ).fill_all()
    logger.info("tutor sessions filled day=%s added=%s", day, added)
    return True
