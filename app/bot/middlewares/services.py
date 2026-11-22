"""Build services for the current session and put them on handler data."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.config import Settings
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatProfileRepository, ChatRepository
from app.db.repositories.content import ContentRepository
from app.db.repositories.engagement import EngagementRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.leaderboard import LeaderboardRepository
from app.db.repositories.payments import PaymentEventRepository, PaymentRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.quizzes import QuizAnswerRepository, QuizRepository
from app.db.repositories.schedules import ScheduleRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.topics import TopicRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.admin import AdminService
from app.services.admin_posts import AdminPostService
from app.services.answers import QuizAnswerService
from app.services.grades import GradeService
from app.services.leaderboard import LeaderboardService
from app.services.lifecycle import ChatLifecycleService
from app.services.payments import PaymentService
from app.services.profiles import ProfileService
from app.services.quiz_launch import QuizLaunch
from app.services.schedule import ScheduleService
from app.services.trial import TrialService
from app.services.trial_reports import TrialReportService


class ServicesMiddleware(BaseMiddleware):
    """Routers receive services, never construct them from globals."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data["session"]
        plans = PlanRepository(session)
        subs = SubscriptionRepository(session)
        chats = ChatRepository(session)
        users = UserRepository(session)
        usage = UsageRepository(session)
        audit = AuditRepository(session)
        access = AccessService(
            plans,
            subs,
            chats,
            usage,
            users,
            founder_slots=self._settings.founder_slots,
        )
        trial = TrialService(plans, subs, audit, trial_days=self._settings.trial_days)
        profiles = ProfileService(ChatProfileRepository(session), access)
        data["access"] = access
        data["lifecycle"] = ChatLifecycleService(chats, access, trial, audit)
        data["profiles"] = profiles
        data["admin_service"] = AdminService(users, plans, subs, chats, audit)
        data["chats"] = chats
        data["users"] = users
        data["plans"] = plans
        data["schedules"] = ScheduleService(
            ScheduleRepository(session),
            JobRepository(session),
            access,
            profiles,
            default_time=self._settings.leaderboard_clock,
        )
        data["quiz_launch"] = QuizLaunch(data["schedules"], ContentRepository(session))
        data["quiz_answers"] = QuizAnswerService(
            QuizRepository(session),
            QuizAnswerRepository(session),
        )
        data["grades"] = GradeService(
            GroupRepository(session),
            StudentRepository(session),
            TopicRepository(session),
            UserRepository(session),
        )
        data["audit"] = audit
        data["payments"] = PaymentService(
            PaymentRepository(session),
            plans,
            subs,
            users,
            access,
            audit,
            discounts=self._settings.period_discount_map,
            events=PaymentEventRepository(session),
            terms_version=self._settings.payment_terms_version,
            draft_ttl_hours=self._settings.payment_draft_ttl_hours,
            fake_block_after=self._settings.payment_fake_block_after,
        )
        data["reports"] = TrialReportService(
            EngagementRepository(session),
            chats,
            subs,
            self._settings.trial_days,
        )
        data["leaderboard"] = LeaderboardService(
            LeaderboardRepository(session),
            users,
            self._settings.points_per_correct_answer,
        )
        content = ContentRepository(session)
        data["admin_posts"] = AdminPostService(
            chats,
            users,
            access,
            profiles,
            content,
            JobRepository(session),
            audit,
            min_chars=self._settings.admin_post_min_chars,
            delay_seconds=self._settings.admin_post_quiz_delay_seconds,
        )
        return await handler(event, data)
