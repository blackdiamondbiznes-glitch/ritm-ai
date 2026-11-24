from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.services.workspace_access import WorkspaceAccessError, WorkspaceAccessService


def _service(*, subscription=None, plan=None, free_plan=None, vertical="tutor"):
    workspace = SimpleNamespace(id=12, owner_id=4, vertical=vertical)
    workspaces = SimpleNamespace(get_by_id=AsyncMock(return_value=workspace))
    subscriptions = SimpleNamespace(get_open=AsyncMock(return_value=subscription))
    plans = SimpleNamespace(
        get_by_id=AsyncMock(return_value=plan),
        get_free_for_vertical=AsyncMock(return_value=free_plan),
    )
    entitlements = SimpleNamespace(for_plan=AsyncMock(return_value={"max_students": 40}))
    service = WorkspaceAccessService(
        workspaces,
        subscriptions,
        plans,
        entitlements,
        now=lambda: datetime(2026, 11, 24, tzinfo=UTC),
    )
    return service, workspaces, subscriptions, plans, entitlements


@pytest.mark.asyncio
async def test_resolves_active_subscription_and_workspace_entitlements():
    plan = SimpleNamespace(id=3, vertical="tutor")
    subscription = SimpleNamespace(
        plan_id=3,
        expires_at=datetime(2026, 12, 24, tzinfo=UTC),
    )
    service, _workspaces, subscriptions, _plans, _entitlements = _service(
        subscription=subscription,
        plan=plan,
    )

    result = await service.resolve(12)

    assert result.plan is plan
    assert result.subscription is subscription
    assert result.entitlements == {"max_students": 40}
    subscriptions.get_open.assert_awaited_once_with(4, 12)


@pytest.mark.asyncio
async def test_expired_workspace_subscription_uses_free_plan():
    free_plan = SimpleNamespace(id=1, vertical=None)
    subscription = SimpleNamespace(
        plan_id=3,
        expires_at=datetime(2026, 11, 23, tzinfo=UTC),
    )
    service, _workspaces, _subscriptions, plans, _entitlements = _service(
        subscription=subscription,
        free_plan=free_plan,
    )

    result = await service.resolve(12)

    assert result.plan is free_plan
    assert result.subscription is None
    plans.get_free_for_vertical.assert_awaited_once_with("tutor")


@pytest.mark.asyncio
async def test_workspace_rejects_subscription_for_a_different_vertical():
    subscription = SimpleNamespace(
        plan_id=3,
        expires_at=datetime(2026, 12, 24, tzinfo=UTC),
    )
    service, _workspaces, _subscriptions, _plans, _entitlements = _service(
        subscription=subscription,
        plan=SimpleNamespace(id=3, vertical="community"),
    )

    with pytest.raises(WorkspaceAccessError, match="plan_vertical_mismatch"):
        await service.resolve(12)
