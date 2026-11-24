"""Build the same services the bot middleware uses, for one HTTP request."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatProfileRepository, ChatRepository
from app.db.repositories.content import ContentRepository
from app.db.repositories.engagement import EngagementRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.leaderboard import LeaderboardRepository
from app.db.repositories.payments import PaymentEventRepository, PaymentRepository
from app.db.repositories.plan_entitlements import PlanEntitlementRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.schedules import ScheduleRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.access import AccessService
from app.services.activity import ActivityService
from app.services.leaderboard import LeaderboardService
from app.services.lifecycle import ChatLifecycleService
from app.services.payments import PaymentService
from app.services.profiles import ProfileService
from app.services.quiz_launch import QuizLaunch
from app.services.schedule import ScheduleService
from app.services.trial import TrialService
from app.services.workspace_access import WorkspaceAccessService
from app.webapp.panel import OwnerPanel


@dataclass
class WebContext:
    """Services for the current authenticated owner."""

    settings: Settings
    session: AsyncSession
    user: User
    is_super: bool
    users: UserRepository
    plans: PlanRepository
    access: AccessService
    workspace_access: WorkspaceAccessService
    payments: PaymentService
    panel: OwnerPanel
    activity: ActivityService
    engagement: EngagementRepository
    lifecycle: ChatLifecycleService | None = None
    memo: dict = field(default_factory=dict)


def build_context(
    session: AsyncSession, settings: Settings, user: User, admins: object | None = None
) -> WebContext:
    """Wire repositories and services on an already-open session."""
    is_super = user.telegram_id is not None and user.telegram_id in settings.admin_ids
    plans = PlanRepository(session)
    subs = SubscriptionRepository(session)
    workspaces = WorkspaceRepository(session)
    plan_entitlements = PlanEntitlementRepository(session)
    chats = ChatRepository(session)
    users = UserRepository(session)
    access = AccessService(
        plans,
        subs,
        chats,
        UsageRepository(session),
        users,
        founder_slots=settings.founder_slots,
        workspaces=workspaces,
    )
    workspace_access = WorkspaceAccessService(
        workspaces,
        subs,
        plans,
        plan_entitlements,
    )
    profiles = ProfileService(ChatProfileRepository(session), access)
    schedules = ScheduleService(
        ScheduleRepository(session),
        JobRepository(session),
        access,
        profiles,
        default_time=settings.leaderboard_clock,
    )
    payments = PaymentService(
        PaymentRepository(session),
        plans,
        subs,
        users,
        access,
        AuditRepository(session),
        discounts=settings.period_discount_map,
        events=PaymentEventRepository(session),
        terms_version=settings.payment_terms_version,
        draft_ttl_hours=settings.payment_draft_ttl_hours,
        fake_block_after=settings.payment_fake_block_after,
    )
    engagement = EngagementRepository(session)
    audit = AuditRepository(session)
    lifecycle = ChatLifecycleService(
        chats, access, TrialService(plans, subs, audit, trial_days=settings.trial_days), audit
    )
    panel = OwnerPanel(
        chats=chats,
        access=access,
        profiles=profiles,
        schedules=schedules,
        quiz_launch=QuizLaunch(schedules, ContentRepository(session)),
        leaderboard=LeaderboardService(
            LeaderboardRepository(session),
            users,
            settings.points_per_correct_answer,
        ),
        is_super=is_super,
        admins=admins,
        participation=engagement,
        users=users,
    )
    return WebContext(
        settings=settings,
        session=session,
        user=user,
        is_super=is_super,
        users=users,
        plans=plans,
        access=access,
        workspace_access=workspace_access,
        payments=payments,
        panel=panel,
        activity=ActivityService(engagement),
        engagement=engagement,
        lifecycle=lifecycle,
    )
