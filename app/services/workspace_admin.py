"""Platform-owner actions on vertical workspaces and their subscriptions."""

from datetime import timedelta

from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.clock import Clock, utcnow

MAX_GRANT_DAYS = 3650


class WorkspaceAdminError(ValueError):
    """Rejected platform-admin workspace operation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class WorkspaceAdminService:
    """Administer a vertical subscription independently of the owner's legacy plan."""

    def __init__(
        self,
        workspaces: WorkspaceRepository,
        plans: PlanRepository,
        subscriptions: SubscriptionRepository,
        audit: AuditRepository,
        now: Clock | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._plans = plans
        self._subscriptions = subscriptions
        self._audit = audit
        self._now = now or utcnow

    async def grant(
        self,
        actor: User,
        workspace_id: int,
        plan_code: str,
        days: int,
        reason: str,
    ) -> Subscription:
        """Replace one workspace's active plan and audit the decision."""
        if days < 1 or days > MAX_GRANT_DAYS:
            raise WorkspaceAdminError("bad_days")
        note = reason.strip()[:500]
        if not note:
            raise WorkspaceAdminError("reason")
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceAdminError("missing_workspace")
        plan = await self._plans.get_by_code(plan_code)
        if (
            plan is None
            or not plan.is_active
            or plan.vertical not in (None, workspace.vertical)
        ):
            raise WorkspaceAdminError("bad_plan")

        current = await self._subscriptions.get_open(workspace.owner_id, workspace.id)
        if current is not None:
            current.status = SubscriptionStatus.CANCELED
        now = self._now()
        subscription = await self._subscriptions.add(
            Subscription(
                owner_id=workspace.owner_id,
                workspace_id=workspace.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=now,
                expires_at=now + timedelta(days=days),
            )
        )
        await self._audit.add(
            actor_user_id=actor.id,
            action="workspace_plan_granted",
            entity="workspace_subscription",
            entity_id=str(subscription.id),
            data={
                "workspace_id": workspace.id,
                "owner_id": workspace.owner_id,
                "vertical": workspace.vertical,
                "plan": plan.code,
                "days": days,
                "reason": note,
            },
        )
        return subscription
