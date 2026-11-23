"""Send one monthly tutor report per workspace on the 1st at 09:00 Tashkent."""

from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import Bot

from app.db.models.jobs import Job, JobStatus
from app.db.repositories.cabinet_stats import CabinetStatsRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.users import UserRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.jobs.runner import JobCancel
from app.services.access import AccessService
from app.services.clock import TASHKENT, utcnow
from app.services.month_report import MonthReport
from app.services.report_text import render_report

logger = logging.getLogger(__name__)
REPORT = "tutor_report"


class TutorReportHandler:
    """Deliver the private monthly message once."""

    def __init__(self, bot: Bot, access: AccessService, users: UserRepository, session) -> None:
        self._bot = bot
        self._access = access
        self._users = users
        self._session = session

    async def handle(self, job: Job) -> None:
        """Send unless the plan no longer includes reports."""
        owner_id = job.payload.get("owner_id")
        month = job.payload.get("month")
        if not isinstance(owner_id, int) or not isinstance(month, str):
            raise JobCancel("report")
        owner = await self._users.get_by_id(owner_id)
        if owner is None:
            raise JobCancel("owner")
        limits = await self._access.tutor_limits(owner)
        if not limits.reports:
            raise JobCancel("export")
        data = await MonthReport(
            CabinetStatsRepository(self._session),
            GroupRepository(self._session),
            self._access,
        ).for_workspace(owner.id, month)
        await self._bot.send_message(owner.telegram_id, render_report(data, owner.language_code))
        logger.info("tutor report sent owner_id=%s month=%s", owner.id, month)


async def enqueue_reports(session, access: AccessService, now=None) -> int:
    """Queue a report for each Pro or Ultra workspace. A second call adds nothing."""
    clock = now or utcnow
    moment = clock() if callable(clock) else clock
    local = moment.astimezone(TASHKENT)
    if local.day != 1 or local.hour < 9:
        return 0
    month = (local.date().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    jobs = JobRepository(session)
    users = UserRepository(session)
    made = 0
    for space in await WorkspaceRepository(session).list_vertical("tutor"):
        slot = f"{space.id}:{month}"
        if await jobs.has_slot(REPORT, slot):
            continue
        owner = await users.get_by_id(space.owner_id)
        if owner is None or not (await access.tutor_limits(owner)).reports:
            continue
        await jobs.add(
            Job(
                chat_id=None,
                type=REPORT,
                payload={
                    "slot": slot,
                    "owner_id": owner.id,
                    "month": month,
                    "workspace_id": space.id,
                },
                run_at=moment,
                status=JobStatus.PENDING,
                attempts=0,
                max_attempts=5,
            )
        )
        made += 1
    return made


async def prepare_reports(session, bot: Bot, access: AccessService, handlers: dict) -> None:
    """Queue due reports and register the sender for this tick."""
    await enqueue_reports(session, access)
    handlers[REPORT] = TutorReportHandler(bot, access, UserRepository(session), session)
