"""Poll-answer middleware wiring and PollAnswer user lookup."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from aiogram import Dispatcher
from aiogram.types import PollAnswer
from aiogram.types import User as TgUser
from app.bot.middlewares import install_middlewares
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.services import ServicesMiddleware
from app.bot.middlewares.throttle import ThrottleMiddleware
from app.bot.middlewares.user import UserMiddleware, event_user
from app.config import Settings
from app.db.models.users import User


def _settings() -> Settings:
    return Settings(bot_token="123:test", database_url="postgresql+asyncpg://bot:bot@x/x")


def _names(observer: object) -> list[str]:
    manager = observer.middleware  # type: ignore[attr-defined]
    return [type(item).__name__ for item in manager._middlewares]


def test_poll_answer_gets_session_user_and_services_without_throttle() -> None:
    dispatcher = Dispatcher()
    install_middlewares(dispatcher, _settings(), MagicMock())
    poll = _names(dispatcher.poll_answer)
    assert poll == [
        "CorrelationMiddleware",
        "DbSessionMiddleware",
        "UserMiddleware",
        "ServicesMiddleware",
    ]
    assert ThrottleMiddleware.__name__ not in poll
    message = _names(dispatcher.message)
    assert message[0] == "CorrelationMiddleware"
    assert message[1] == "ThrottleMiddleware"
    assert DbSessionMiddleware.__name__ in message
    assert UserMiddleware.__name__ in message
    assert ServicesMiddleware.__name__ in message


def _poll_answer() -> PollAnswer:
    voter = TgUser(id=1001, is_bot=False, first_name="Ada", username="ada", language_code="uz")
    return PollAnswer(poll_id="poll-1", user=voter, option_ids=[0], option_persistent_ids=[])


def test_event_user_reads_poll_answer_user() -> None:
    event = _poll_answer()
    assert getattr(event, "from_user", None) is None
    found = event_user(event)
    assert found is not None
    assert found.id == 1001
    assert found.username == "ada"


class _Repo:
    def __init__(self, session: object) -> None:
        self.session = session

    async def upsert_seen(
        self,
        telegram_id: int,
        username: str | None,
        full_name: str | None,
        language_code: str | None,
    ) -> User:
        return User(
            id=7,
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            language_code=language_code or "uz",
            is_blocked=False,
        )


async def test_user_middleware_loads_poll_answer_user(monkeypatch) -> None:
    monkeypatch.setattr("app.bot.middlewares.user.UserRepository", _Repo)
    captured: dict[str, object] = {}

    async def handler(_event: object, data: dict[str, object]) -> str:
        captured.update(data)
        return "ok"

    middleware = UserMiddleware(_settings())
    result = await middleware(handler, _poll_answer(), {"session": object()})
    assert result == "ok"
    user = captured["current_user"]
    assert isinstance(user, User)
    assert user.telegram_id == 1001
    assert captured["lang"] == "uz"
    assert captured["is_super_admin"] is False


def test_event_user_prefers_from_user() -> None:
    from_user = TgUser(id=2, is_bot=False, first_name="Bo")
    event = SimpleNamespace(from_user=from_user, user=TgUser(id=9, is_bot=False, first_name="X"))
    found = event_user(event)
    assert found is not None
    assert found.id == 2


def test_channel_post_gets_session_user_and_services_without_throttle() -> None:
    dispatcher = Dispatcher()
    install_middlewares(dispatcher, _settings(), MagicMock())
    names = _names(dispatcher.channel_post)
    assert names == [
        "CorrelationMiddleware",
        "DbSessionMiddleware",
        "UserMiddleware",
        "ServicesMiddleware",
    ]
    assert ThrottleMiddleware.__name__ not in names


def test_channel_post_is_requested_in_allowed_updates() -> None:
    from app.bot.routers import setup_routers

    dispatcher = Dispatcher()
    setup_routers(dispatcher)
    assert "channel_post" in dispatcher.resolve_used_update_types()


def test_event_user_is_none_without_from_user_or_user() -> None:
    event = SimpleNamespace(from_user=None, user=None)
    assert event_user(event) is None


async def test_user_middleware_skips_channel_post_without_user(monkeypatch) -> None:
    class _Boom:
        def __init__(self, session: object) -> None:
            raise AssertionError("must not create a user for a channel post")

    monkeypatch.setattr("app.bot.middlewares.user.UserRepository", _Boom)
    captured: dict[str, object] = {}

    async def handler(_event: object, data: dict[str, object]) -> str:
        captured.update(data)
        return "ok"

    middleware = UserMiddleware(_settings())
    event = SimpleNamespace(from_user=None, user=None)
    result = await middleware(handler, event, {"session": object()})
    assert result == "ok"
    assert "current_user" not in captured
