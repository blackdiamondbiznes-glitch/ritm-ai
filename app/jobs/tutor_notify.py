"""Send one queued tutor notice. Quiet hours and a full quota skip without retry."""

from __future__ import annotations

import logging
from datetime import datetime
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.bot.widgets.dispatch import send_notice
from app.bot.widgets.markup import with_join
from app.db.models.jobs import Job
from app.db.repositories.jobs import JobRepository
from app.db.repositories.tutor_notices import TutorNoticeRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.i18n import t
from app.jobs.runner import JobCancel, JobPostpone
from app.services.access import AccessService
from app.services.clock import utcnow
from app.services.notify_queue import deliver
from app.services.notify_rules import METRIC, NOTIFY, language, month_ref, period_key, quiet_wake

logger = logging.getLogger(__name__)
_DEAD = ("chat not found", "bot was kicked")


class TutorNotifyHandler:
    """Deliver the payload once. A blocked chat is skipped and not retried."""

    def __init__(
        self,
        bot: Bot,
        notes: TutorNoticeRepository,
        users: UserRepository,
        usage: UsageRepository,
        access: AccessService,
        jobs: JobRepository,
        now=utcnow,
        session=None,
        widgets_enabled: bool = True,
    ) -> None:
        self._bot = bot
        self._notes = notes
        self._users = users
        self._usage = usage
        self._access = access
        self._jobs = jobs
        self._now = now
        self._session = session
        self._widgets = widgets_enabled

    async def handle(self, job: Job) -> None:
        """Send, skip, or ask the runner to try again later."""
        notice_id = job.payload.get("notification_id")
        if not isinstance(notice_id, int):
            raise JobCancel("notice")
        row = await self._notes.get(notice_id)
        if row is None or row.status in {"sent", "skipped"}:
            raise JobCancel("sent")
        moment = self._now()
        await self._quiet(job, row, moment)
        if job.payload.get("quota"):
            await self._quota(job, row, moment)
        text = _render(
            str(job.payload.get("template") or ""),
            job.payload.get("lang"),
            job.payload.get("params"),
        )
        chat_id = int(job.payload["telegram_id"])
        sent = False
        try:
            if self._session is not None and self._widgets:
                try:
                    sent = await send_notice(
                        self._bot,
                        self._session,
                        row,
                        chat_id=chat_id,
                        lang=str(job.payload.get("lang") or "uz"),
                        caption=text,
                        enabled=True,
                        params=job.payload.get("params")
                        if isinstance(job.payload.get("params"), dict)
                        else None,
                    )
                except (TelegramForbiddenError, TelegramBadRequest):
                    raise
                except Exception:
                    logger.exception("notice widget failed id=%s", row.id)
            if not sent:
                params = job.payload.get("params")
                link = params.get("meeting_url") if isinstance(params, dict) else None
                markup = with_join(None, link, str(job.payload.get("lang") or "uz"))
                if markup is None:
                    await self._bot.send_message(chat_id, text)
                else:
                    await self._bot.send_message(chat_id, text, reply_markup=markup)
        except TelegramForbiddenError as exc:
            await self._skip(row, "blocked")
            raise JobCancel("blocked") from exc
        except TelegramBadRequest as exc:
            if not any(needle in str(exc).lower() for needle in _DEAD):
                raise
            await self._skip(row, "chat")
            raise JobCancel("chat") from exc
        row.status = "sent"
        await self._notes.save(row)
        if job.payload.get("quota"):
            owner_id = int(job.payload["owner_id"])
            await self._usage.bump(owner_id, METRIC, period_key(moment))
        logger.info("notice sent id=%s kind=%s", row.id, row.kind)

    async def _quiet(self, job: Job, row, now: datetime) -> None:
        wake = quiet_wake(now)
        if wake is None:
            return
        if job.payload.get("kind") == "lesson" and _too_late(job, wake):
            await self._skip(row, "quiet")
            raise JobCancel("quiet")
        raise JobPostpone(wake)

    async def _quota(self, job: Job, row, now: datetime) -> None:
        owner = await self._users.get_by_id(int(job.payload["owner_id"]))
        if owner is None:
            await self._skip(row, "owner")
            raise JobCancel("owner")
        limit = (await self._access.tutor_limits(owner)).notifications
        used = await self._usage.get_count(owner.id, METRIC, period_key(now))
        if limit >= 0 and used >= limit:
            await self._skip(row, "quota")
            await self._warn(owner, now)
            raise JobCancel("quota")

    async def _warn(self, owner, now: datetime) -> None:
        """Tell the teacher once per Tashkent month. This note is free."""
        await deliver(
            self._notes,
            self._jobs,
            kind="manual",
            ref=month_ref(now),
            target="owner",
            target_id=owner.id,
            telegram_id=owner.telegram_id,
            lang=language(owner.language_code),
            template="notify_quota",
            params={},
            quota=False,
            owner_id=owner.id,
            run_at=now,
        )

    async def _skip(self, row, code: str) -> None:
        row.status = "skipped"
        await self._notes.save(row)
        logger.info("notice skipped id=%s code=%s", row.id, code)


def _too_late(job: Job, wake: datetime) -> bool:
    raw = (job.payload.get("params") or {}).get("starts_at")
    if not isinstance(raw, str):
        return False
    return wake >= datetime.fromisoformat(raw)


def _render(template: str, lang: object, params: object) -> str:
    data = dict(params) if isinstance(params, dict) else {}
    gap_min = data.pop("gap_min", None)
    data.pop("starts_at", None)
    data.pop("meeting_url", None)
    safe = {key: escape(value) if isinstance(value, str) else value for key, value in data.items()}
    if gap_min is not None:
        safe["gap"] = t(f"notify_gap_{gap_min}", str(lang or "uz"))
    return t(template, str(lang or "uz"), **safe)


async def prepare(
    session, bot: Bot, access: AccessService, handlers: dict, widgets_enabled: bool = True
) -> None:
    """Queue due notices, then register the sender for this tick."""
    from app.services.notify import notify_for

    await notify_for(session).enqueue_due()
    handlers[NOTIFY] = TutorNotifyHandler(
        bot,
        TutorNoticeRepository(session),
        UserRepository(session),
        UsageRepository(session),
        access,
        JobRepository(session),
        session=session,
        widgets_enabled=widgets_enabled,
    )


__all__ = ["NOTIFY", "TutorNotifyHandler", "prepare"]
