from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.db.models.subscriptions import SubscriptionStatus
from app.services.workspace_admin import WorkspaceAdminError, WorkspaceAdminService


def _service(*, workspace=None, plan=None, current=None):
    workspace_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=workspace))
    plan_repo = SimpleNamespace(get_by_code=AsyncMock(return_value=plan))
    subscriptions = SimpleNamespace(
        get_open=AsyncMock(return_value=current),
        add=AsyncMock(side_effect=lambda row: row),
    )
    audit = SimpleNamespace(add=AsyncMock())
    service = WorkspaceAdminService(
        workspace_repo,
        plan_repo,
        subscriptions,
        audit,
        now=lambda: datetime(2026, 11, 24, tzinfo=UTC),
    )
    return service, subscriptions, audit


@pytest.mark.asyncio
async def test_grant_replaces_only_the_requested_workspace_subscription():
    workspace = SimpleNamespace(id=12, owner_id=4, vertical="tutor")
    plan = SimpleNamespace(id=3, code="tutor_pro", vertical="tutor", is_active=True)
    current = SimpleNamespace(status=SubscriptionStatus.ACTIVE)
    service, subscriptions, audit = _service(
        workspace=workspace,
        plan=plan,
        current=current,
    )
    actor = SimpleNamespace(id=1)

    granted = await service.grant(actor, 12, "tutor_pro", 30, "first month")

    assert current.status is SubscriptionStatus.CANCELED
    subscriptions.get_open.assert_awaited_once_with(4, 12)
    assert granted.workspace_id == 12
    assert granted.owner_id == 4
    assert granted.plan_id == 3
    assert (granted.expires_at - granted.started_at).days == 30
    audit.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_grant_rejects_plan_from_another_vertical():
    workspace = SimpleNamespace(id=12, owner_id=4, vertical="tutor")
    plan = SimpleNamespace(id=3, code="community_pro", vertical="community", is_active=True)
    service, subscriptions, audit = _service(workspace=workspace, plan=plan)

    with pytest.raises(WorkspaceAdminError, match="bad_plan"):
        await service.grant(SimpleNamespace(id=1), 12, "community_pro", 30, "test")

    subscriptions.add.assert_not_awaited()
    audit.add.assert_not_awaited()
