"""Effective plan, chat limit and AI quota."""

from datetime import timedelta

from app.db.models.subscriptions import SubscriptionSource, SubscriptionStatus
from app.services.access import AI_METRIC
from tests.fakes import NOW, World, make_chat, make_user


async def test_no_subscription_is_free() -> None:
    world = World()
    owner = world.add_user(make_user())
    plan = await world.access.get_effective_plan(owner)
    assert plan.code == "free"


async def test_active_trial_uses_pro() -> None:
    world = World()
    owner = world.add_user(make_user())
    await world.add_sub(
        owner, "pro", SubscriptionStatus.TRIAL, days=4, source=SubscriptionSource.TRIAL
    )
    plan = await world.access.get_effective_plan(owner)
    assert plan.code == "pro"
    snap = await world.access.snapshot(owner)
    assert snap.kind == "trial"
    assert snap.days_left == 4


async def test_expired_trial_falls_back_to_free() -> None:
    world = World()
    owner = world.add_user(make_user())
    sub = await world.add_sub(
        owner, "pro", SubscriptionStatus.TRIAL, days=1, source=SubscriptionSource.TRIAL
    )
    sub.expires_at = NOW - timedelta(hours=1)
    plan = await world.access.get_effective_plan(owner)
    assert plan.code == "free"
    assert sub.status == SubscriptionStatus.TRIAL


async def test_expired_paid_plan_falls_back_to_free() -> None:
    world = World()
    owner = world.add_user(make_user())
    sub = await world.add_sub(owner, "start", SubscriptionStatus.ACTIVE, days=1)
    sub.expires_at = NOW - timedelta(seconds=1)
    plan = await world.access.get_effective_plan(owner)
    assert plan.code == "free"


async def test_can_connect_respects_free_limit() -> None:
    world = World()
    owner = world.add_user(make_user())
    first = await world.access.can_connect_chat(owner)
    assert first.allowed is True
    assert first.limit == 1
    chat = make_chat(owner)
    await world.chats.add(chat)
    second = await world.access.can_connect_chat(owner)
    assert second.allowed is False
    assert second.used == 1


async def test_pro_limit_allows_five_chats() -> None:
    world = World()
    owner = world.add_user(make_user())
    await world.add_sub(owner, "pro", SubscriptionStatus.ACTIVE, days=10)
    for index in range(4):
        await world.chats.add(make_chat(owner, telegram_chat_id=-2000 - index))
    assert (await world.access.can_connect_chat(owner)).allowed is True
    await world.chats.add(make_chat(owner, telegram_chat_id=-3000))
    decision = await world.access.can_connect_chat(owner)
    assert decision.allowed is False
    assert decision.limit == 5


async def test_quota_subtracts_usage_and_floors_at_zero() -> None:
    world = World()
    owner = world.add_user(make_user())
    await world.add_sub(owner, "pro", SubscriptionStatus.ACTIVE, days=10)
    period = NOW.strftime("%Y-%m")
    assert await world.access.remaining_ai_quota(owner) == 300
    world.usage.counts[(owner.id, AI_METRIC, period)] = 40
    assert await world.access.remaining_ai_quota(owner) == 260
    world.usage.counts[(owner.id, AI_METRIC, period)] = 999
    assert await world.access.remaining_ai_quota(owner) == 0


async def test_free_quota_when_trial_expired() -> None:
    world = World()
    owner = world.add_user(make_user())
    sub = await world.add_sub(
        owner, "pro", SubscriptionStatus.TRIAL, days=1, source=SubscriptionSource.TRIAL
    )
    sub.expires_at = NOW - timedelta(days=1)
    assert await world.access.remaining_ai_quota(owner) == 8
