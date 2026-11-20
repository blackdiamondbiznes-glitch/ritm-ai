"""Queue and send trial reports plus a one-time expiry notice."""

import logging

from aiogram import Bot

from app.bot.keyboards.payments import report_actions
from app.bot.pay_copy import expiry_notice, trial_report_text
from app.bot.poster import ChatGone, RateLimitedSender
from app.db.models.jobs import Job, JobStatus
from app.db.models.subscriptions import Subscription, SubscriptionStatus
from app.db.repositories.chats import ChatRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.notifications import NotificationRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.users import UserRepository
from app.jobs.runner import JobCancel
from app.services.clock import Clock, utcnow
from app.services.trial_reports import TrialReportService

logger = logging.getLogger(__name__)
REPORT = "trial_engagement_report"
EXPIRY = "trial_expiry_watch"


class TrialNudgePlanner:
    """Enqueue due trial reports and expiry notices once each."""

    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        chats: ChatRepository,
        jobs: JobRepository,
        notices: NotificationRepository,
        reports: TrialReportService,
        now: Clock | None = None,
    ) -> None:
        self._subs = subscriptions
        self._chats = chats
        self._jobs = jobs
        self._notices = notices
        self._reports = reports
        self._now = now or utcnow

    async def enqueue_due(self) -> None:
        """Add pending jobs for milestones that have been reached."""
        now = self._now()
        for sub in await self._subs.list_trials():
            if sub.expires_at <= now:
                await self._expiry(sub, now)
                continue
            await self._reports_for(sub, now)

    async def _reports_for(self, sub: Subscription, now) -> None:
        chats = await self._chats.list_active_for_owner(sub.owner_id)
        for chat in chats:
            for offset in self._reports.offsets():
                kind = f"trial_report:{offset}"
                if not self._reports.is_due(sub.started_at, offset, now):
                    continue
                if await self._notices.was_sent(sub.owner_id, kind, chat_id=chat.id):
                    continue
                await self._queue(REPORT, sub.owner_id, now, chat.id, kind, offset)

    async def _expiry(self, sub: Subscription, now) -> None:
        if await self._notices.was_sent(sub.owner_id, EXPIRY):
            if sub.status == SubscriptionStatus.TRIAL:
                sub.status = SubscriptionStatus.EXPIRED
            return
        await self._queue(EXPIRY, sub.owner_id, now, None, EXPIRY, 0)

    async def _queue(
        self, typ: str, owner_id: int, now, chat_id: int | None, kind: str, offset: int
    ) -> None:
        slot = f"{kind}:{chat_id or 0}"
        if await self._jobs.has_slot(typ, slot):
            return
        await self._jobs.add(
            Job(
                chat_id=chat_id,
                type=typ,
                payload={
                    "slot": slot,
                    "owner_id": owner_id,
                    "kind": kind,
                    "offset": offset,
                    "chat_id": chat_id,
                },
                run_at=now,
                status=JobStatus.PENDING,
                attempts=0,
                max_attempts=5,
            )
        )


class TrialNudgeHandler:
    """Send one private report or expiry notice and record the dedup row."""

    def __init__(
        self,
        users: UserRepository,
        chats: ChatRepository,
        subscriptions: SubscriptionRepository,
        notices: NotificationRepository,
        reports: TrialReportService,
        sender: RateLimitedSender,
        bot: Bot,
        now: Clock | None = None,
    ) -> None:
        self._users = users
        self._chats = chats
        self._subs = subscriptions
        self._notices = notices
        self._reports = reports
        self._sender = sender
        self._bot = bot
        self._now = now or utcnow

    async def handle(self, job: Job) -> None:
        """Deliver the message or skip when it was already sent."""
        payload = job.payload or {}
        owner_id = int(payload.get("owner_id") or 0)
        kind = str(payload.get("kind") or job.type)
        chat_id = payload.get("chat_id")
        chat_key = int(chat_id) if chat_id else None
        if await self._notices.was_sent(owner_id, kind, chat_id=chat_key):
            return
        owner = await self._users.get_by_id(owner_id)
        if owner is None:
            raise JobCancel("owner")
        if job.type == EXPIRY:
            await self._send_expiry(owner, kind)
            return
        await self._send_report(owner, kind, chat_key, int(payload.get("offset") or 0))

    async def send_live_report(self, owner, chat) -> bool:
        """Owner-triggered report. Does not consume a scheduled milestone."""
        sub = await self._subs.get_open(owner.id)
        if sub is None or sub.status != SubscriptionStatus.TRIAL:
            return False
        stats = await self._reports.stats_for(chat, sub.started_at, sub.expires_at)
        lang = owner.language_code or "uz"
        await self._deliver(owner.telegram_id, trial_report_text(stats, lang), report_actions(lang))
        return True

    async def _send_report(self, owner, kind: str, chat_id: int | None, offset: int) -> None:
        chat = None
        if chat_id:
            chat = await self._chats.get_by_id(chat_id)
        if chat is None:
            chat = await self._reports.first_chat(owner.id)
        sub = await self._subs.get_open(owner.id)
        if chat is None or sub is None:
            raise JobCancel("chat")
        if not getattr(owner, "notify_reports", True):
            # Opted out in the Mini App: record the milestone so it is not queued again.
            await self._notices.add(owner.id, kind, self._now(), chat_id=chat.id)
            return
        stats = await self._reports.stats_for(chat, sub.started_at, sub.expires_at)
        stats = TrialStatsView(stats, late=self._reports.is_late(offset))
        lang = owner.language_code or "uz"
        sent = await self._deliver(
            owner.telegram_id, trial_report_text(stats, lang), report_actions(lang)
        )
        if sent:
            await self._notices.add(owner.id, kind, self._now(), chat_id=chat.id)

    async def _send_expiry(self, owner, kind: str) -> None:
        lang = owner.language_code or "uz"
        if getattr(owner, "notify_expiry", True):
            sent = await self._deliver(owner.telegram_id, expiry_notice(lang), report_actions(lang))
        else:
            sent = True  # opted out: skip the message, keep the same bookkeeping
        if sent:
            await self._notices.add(owner.id, kind, self._now())
            sub = await self._subs.get_open(owner.id)
            if sub is not None and sub.status == SubscriptionStatus.TRIAL:
                sub.status = SubscriptionStatus.EXPIRED

    async def _deliver(self, telegram_id: int, text: str, markup) -> bool:
        try:
            await self._sender.post(self._bot, telegram_id, text, markup)
            return True
        except ChatGone:
            logger.info("trial nudge failed telegram_id=%s", telegram_id)
            return False


class TrialStatsView:
    """Override the late flag for a scheduled report day."""

    def __init__(self, stats, late: bool) -> None:
        self.chat = stats.chat
        self.posts = stats.posts
        self.answers = stats.answers
        self.participants = stats.participants
        self.best_day = stats.best_day
        self.days_left = stats.days_left
        self.late = late
