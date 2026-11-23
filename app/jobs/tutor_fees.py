"""Create course invoices once per Asia/Tashkent day. The claim shares the tick transaction."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.groups import GroupRepository
from app.db.repositories.invoices import InvoiceRepository
from app.db.repositories.system_state import SystemStateRepository
from app.services.clock import Clock, utcnow
from app.services.fees import FeeService
from app.services.sessions import sessions_due

logger = logging.getLogger(__name__)
KIND = "tutor_fees"


async def refill_fees(session: AsyncSession, now: Clock | None = None) -> bool:
    """Open due invoices and mark late ones when this Tashkent day is new."""
    clock = now or utcnow
    state = SystemStateRepository(session, clock)
    day = sessions_due(clock(), await state.get(KIND))
    if day is None:
        return False
    await state.put(KIND, day)
    added = await FeeService(
        InvoiceRepository(session), GroupRepository(session), now=clock
    ).run_daily()
    logger.info("tutor fees synced day=%s added=%s", day, added)
    return True
