"""One trial per owner, one trial per chat, reconnect does not refresh it."""

from app.db.models.chats import ChatType
from app.db.models.subscriptions import SubscriptionStatus
from tests.fakes import World, make_chat, make_user


async def test_trial_starts_once_per_owner() -> None:
    world = World()
    owner = world.add_user(make_user())
    first = make_chat(owner, -100)
    second = make_chat(owner, -200)
    assert await world.trial.start_if_eligible(owner, first) is True
    assert owner.trial_used_at is not None
    assert first.trial_consumed is True
    assert await world.trial.start_if_eligible(owner, second) is False
    assert second.trial_consumed is False
    trials = [row for row in world.subs.rows if row.status == SubscriptionStatus.TRIAL]
    assert len(trials) == 1
    actions = [row["action"] for row in world.audit.rows]
    assert actions == ["trial_started"]


async def test_trial_does_not_start_when_chat_already_consumed() -> None:
    world = World()
    owner = world.add_user(make_user())
    chat = make_chat(owner, consumed=True)
    assert await world.trial.start_if_eligible(owner, chat) is False
    assert owner.trial_used_at is None
    assert world.subs.rows == []


async def test_reconnect_does_not_restart_trial() -> None:
    world = World()
    owner = world.add_user(make_user())
    first = await world.lifecycle.connect(
        owner,
        telegram_chat_id=-100,
        chat_type=ChatType.CHANNEL.value,
        title="Arab tili",
        username=None,
        user_is_admin=True,
        bot_can_post=True,
    )
    assert first.trial_started is True
    chat = await world.chats.get_by_id(first.chat_id or 0)
    assert chat is not None
    await world.lifecycle.disconnect(owner, chat)
    assert chat.trial_consumed is True
    assert chat.is_active is False
    again = await world.lifecycle.connect(
        owner,
        telegram_chat_id=-100,
        chat_type=ChatType.CHANNEL.value,
        title="Arab tili",
        username=None,
        user_is_admin=True,
        bot_can_post=True,
    )
    assert again.ok is True
    assert again.trial_started is False
    assert chat.trial_consumed is True
    assert chat.is_active is True
    trials = [row for row in world.subs.rows if row.status == SubscriptionStatus.TRIAL]
    assert len(trials) == 1


async def test_non_admin_cannot_connect() -> None:
    world = World()
    owner = world.add_user(make_user())
    outcome = await world.lifecycle.connect(
        owner,
        telegram_chat_id=-100,
        chat_type="channel",
        title="Yopiq",
        username=None,
        user_is_admin=False,
        bot_can_post=True,
    )
    assert outcome.ok is False
    assert outcome.code == "not_admin"
    assert world.chats.rows == []


async def test_other_owner_cannot_take_an_active_chat() -> None:
    world = World()
    owner = world.add_user(make_user(1, 100))
    other = world.add_user(make_user(2, 200))
    await world.lifecycle.connect(
        owner,
        telegram_chat_id=-100,
        chat_type="group",
        title="Guruh",
        username=None,
        user_is_admin=True,
        bot_can_post=True,
    )
    stolen = await world.lifecycle.connect(
        other,
        telegram_chat_id=-100,
        chat_type="group",
        title="Guruh",
        username=None,
        user_is_admin=True,
        bot_can_post=True,
    )
    assert stolen.ok is False
    assert stolen.code == "owned"
    visible = await world.chats.list_active_for_owner(other.id)
    assert visible == []
