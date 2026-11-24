"""Resolve the plan and features available to one vertical workspace."""

from __future__ import annotations

from dataclasses import dataclass

from app.db.models.plans import Plan
from app.db.models.subscriptions import Subscription
from app.db.models.workspaces import Workspace
from app.db.repositories.plan_entitlements import PlanEntitlementRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.clock import Clock, utcnow


class WorkspaceAccessError(ValueError):
    """A workspace cannot resolve a valid vertical plan."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class WorkspacePlan:
    """Effective workspace plan, subscription, and normalized entitlements."""

    workspace: Workspace
    plan: Plan
    subscription: Subscription | None
    entitlements: dict[str, object]


class WorkspaceAccessService:
    """Resolve plan access without changing legacy owner-wide subscriptions."""

    def __init__(
        self,
        workspaces: WorkspaceRepository,
        subscriptions: SubscriptionRepository,
        plans: PlanRepository,
        entitlements: PlanEntitlementRepository,
        now: Clock | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._subscriptions = subscriptions
        self._plans = plans
        self._entitlements = entitlements
        self._now = now or utcnow

    async def resolve(self, workspace_id: int) -> WorkspacePlan:
        """Resolve active workspace subscription or the vertical-compatible free plan."""
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceAccessError("workspace_missing")

        subscription = await self._subscriptions.get_open(workspace.owner_id, workspace.id)
        if subscription is not None and subscription.expires_at > self._now():
            plan = await self._plans.get_by_id(subscription.plan_id)
            if plan is None:
                raise WorkspaceAccessError("plan_missing")
            if plan.vertical not in (None, workspace.vertical):
                raise WorkspaceAccessError("plan_vertical_mismatch")
            return WorkspacePlan(
                workspace=workspace,
                plan=plan,
                subscription=subscription,
                entitlements=await self._entitlements.for_plan(plan.id),
            )

        plan = await self._plans.get_free_for_vertical(workspace.vertical)
        if plan is None:
            raise WorkspaceAccessError("free_plan_missing")
        return WorkspacePlan(
            workspace=workspace,
            plan=plan,
            subscription=None,
            entitlements=await self._entitlements.for_plan(plan.id),
        )
