"""One APScheduler wake-up. The clock itself has no business rules."""

import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.provider import build_provider
from app.bot.poster import RateLimitedSender
from app.config import Settings
from app.db.repositories.audit import AuditRepository
from app.db.repositories.cache import CacheRepository
from app.db.repositories.chats import ChatProfileRepository, ChatRepository
from app.db.repositories.content import ContentRepository
from app.db.repositories.engagement import EngagementRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.leaderboard import LeaderboardRepository
from app.db.repositories.notifications import NotificationRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.quizzes import QuizRepository
from app.db.repositories.reminders import ReminderRepository
from app.db.repositories.schedules import ScheduleRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.system_state import SystemStateRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.jobs.admin_quiz import AdminPostQuizHandler
from app.jobs.daily import DailyHandler
from app.jobs.leaderboard import LeaderboardHandler
from app.jobs.quiz import QUIZ, QuizHandler
from app.jobs.reminder import ReminderHandler
from app.jobs.runner import JobRunner
from app.jobs.trial_nudge import EXPIRY, REPORT, TrialNudgeHandler, TrialNudgePlanner
from app.jobs.tutor_fees import refill_fees
from app.jobs.tutor_notify import prepare as prepare_notices
from app.jobs.tutor_sessions import refill_sessions
from app.services.access import AccessService
from app.services.clock import utcnow
from app.services.generate import ContentGenerator
from app.services.health import LAST_TICK
from app.services.leaderboard import MODULE as LEADERBOARD
from app.services.leaderboard import LeaderboardService
from app.services.lifecycle import ChatLifecycleService
from app.services.profiles import ProfileService
from app.services.quiz_mode import ADMIN_POST_QUIZ
from app.services.quizgen import QuizGenerator
from app.services.reminders import REMINDER, ReminderService
from app.services.trial import TrialService
from app.services.trial_reports import TrialReportService

logger = logging.getLogger(__name__)


class Tick:
    """Open a session, run the dispatcher, commit."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        bot: Bot,
        settings: Settings,
        sender: RateLimitedSender,
    ) -> None:
        self._sessions = sessions
        self._bot = bot
        self._settings = settings
        self._sender = sender

    async def run(self) -> None:
        """Called every JOB_TICK_SECONDS. Failures stay inside this task.

        Register `tick.run` with APScheduler, not the Tick instance.
        AsyncIOExecutor only awaits inspect.iscoroutinefunction callables, and
        a class instance with async ``__call__`` is not detected.
        """
        async with self._sessions() as session:
            try:
                await _once(session, self._bot, self._settings, self._sender)
                await session.commit()
                _touch_heartbeat(self._settings.health_file)
            except Exception:
                await session.rollback()
                logger.exception("job tick failed")

    async def __call__(self) -> None:
        """Same work as `run`. Prefer `run` when adding the scheduler job."""
        await self.run()


async def _once(
    session: AsyncSession, bot: Bot, settings: Settings, sender: RateLimitedSender
) -> None:
    access = _access(session, settings)
    profiles = ProfileService(ChatProfileRepository(session), access)
    audit = AuditRepository(session)
    trial = TrialService(
        PlanRepository(session),
        SubscriptionRepository(session),
        audit,
        settings.trial_days,
    )
    handlers = _handlers(session, bot, settings, sender, access, profiles, trial, audit)
    jobs = JobRepository(session)
    reports, planner, nudge = _trial(session, bot, settings, sender, jobs)
    await planner.enqueue_due()
    await ReminderService(
        ReminderRepository(session),
        StudentRepository(session),
        jobs,
    ).enqueue_due()
    await prepare_notices(session, bot, access, handlers)
    handlers[REPORT] = nudge
    handlers[EXPIRY] = nudge
    handlers[REMINDER] = ReminderHandler(bot, ReminderRepository(session), UserRepository(session))
    await JobRunner(ScheduleRepository(session), jobs, handlers).run_once()
    await refill_sessions(session)
    await refill_fees(session)
    await SystemStateRepository(session).put(LAST_TICK, utcnow().isoformat())


def _access(session: AsyncSession, settings: Settings) -> AccessService:
    return AccessService(
        PlanRepository(session),
        SubscriptionRepository(session),
        ChatRepository(session),
        UsageRepository(session),
        UserRepository(session),
        founder_slots=settings.founder_slots,
    )


def _handlers(session, bot, settings, sender, access, profiles, trial, audit):
    """Build the job handlers for this tick."""
    provider = build_provider(settings)
    chats = ChatRepository(session)
    users = UserRepository(session)
    usage = UsageRepository(session)
    content = ContentRepository(session)
    cache = CacheRepository(session)
    life = ChatLifecycleService(chats, access, trial, audit)
    daily = _daily(
        chats, users, profiles, access, usage, content, provider, cache, sender, bot, life
    )
    quiz = _quiz(
        chats, users, profiles, access, usage, content, provider, cache, sender, bot, life, session
    )
    admin = AdminPostQuizHandler(
        chats,
        users,
        profiles,
        access,
        usage,
        content,
        QuizRepository(session),
        QuizGenerator(provider, cache),
        sender,
        bot,
        life,
    )
    boards = LeaderboardService(
        LeaderboardRepository(session),
        users,
        settings.points_per_correct_answer,
    )
    rating = LeaderboardHandler(chats, users, profiles, access, boards, sender, bot, life)
    return {"daily_content": daily, QUIZ: quiz, ADMIN_POST_QUIZ: admin, LEADERBOARD: rating}


def _daily(chats, users, profiles, access, usage, content, provider, cache, sender, bot, life):
    return DailyHandler(
        chats,
        users,
        profiles,
        access,
        usage,
        content,
        ContentGenerator(provider, cache),
        sender,
        bot,
        life,
    )


def _quiz(
    chats, users, profiles, access, usage, content, provider, cache, sender, bot, life, session
):
    return QuizHandler(
        chats,
        users,
        profiles,
        access,
        usage,
        content,
        QuizRepository(session),
        QuizGenerator(provider, cache),
        sender,
        bot,
        life,
    )


def _trial(session, bot, settings, sender, jobs):
    chats = ChatRepository(session)
    users = UserRepository(session)
    subs = SubscriptionRepository(session)
    reports = TrialReportService(
        EngagementRepository(session),
        chats,
        subs,
        settings.trial_days,
    )
    notices = NotificationRepository(session)
    planner = TrialNudgePlanner(subs, chats, jobs, notices, reports)
    nudge = TrialNudgeHandler(
        users,
        chats,
        subs,
        notices,
        reports,
        sender,
        bot,
    )
    return reports, planner, nudge


def schedule_tick(scheduler: object, tick: Tick, seconds: int) -> None:
    """Add the tick as an awaitable coroutine function, not as a callable object."""
    scheduler.add_job(
        tick.run,
        "interval",
        seconds=seconds,
        max_instances=1,
        coalesce=True,
    )


def _touch_heartbeat(path: str) -> None:
    """Update the container heartbeat file after a successful tick."""
    if not path:
        return
    from pathlib import Path

    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n")
    except OSError:
        logger.info("heartbeat not written")
