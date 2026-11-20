"""Super admin tenant view: an expired open subscription shows as expired / free."""

from datetime import UTC, datetime, timedelta

from app.db.models.plans import Plan
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.services.admin_panel import _shown_status, _tenant_plan

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
PRO = Plan(code="pro", name="Pro", max_chats=5, ai_generations_per_month=300)


def _sub(status: SubscriptionStatus, expires: datetime) -> Subscription:
    return Subscription(
        status=status,
        source=SubscriptionSource.TRIAL,
        started_at=expires - timedelta(days=5),
        expires_at=expires,
    )


def test_expired_trial_is_free_in_tenant_view() -> None:
    sub = _sub(SubscriptionStatus.TRIAL, NOW - timedelta(hours=1))
    block = _tenant_plan([(sub, PRO)], 3, NOW)
    assert block["code"] == "free" and block["name"] == "Free"
    assert block["status"] == "expired" and block["expires_at"] is not None
    assert block["ai_limit"] is None and block["max_chats"] is None and block["ai_used"] == 3
    assert _shown_status(sub, NOW) == "expired"


def test_live_subscription_is_shown_as_is() -> None:
    sub = _sub(SubscriptionStatus.ACTIVE, NOW + timedelta(days=3))
    block = _tenant_plan([(sub, PRO)], 0, NOW)
    assert block["code"] == "pro" and block["status"] == "active"
    assert block["ai_limit"] == 300 and block["max_chats"] == 5


def test_no_subscription_is_free() -> None:
    block = _tenant_plan([], 0, NOW)
    assert block["code"] == "free" and block["status"] is None
    canceled = _sub(SubscriptionStatus.CANCELED, NOW - timedelta(days=1))
    assert _shown_status(canceled, NOW) == "canceled"
