"""First /start asks for the UI language; the choice is saved and editable later."""

import os
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest
from aiogram.methods import EditMessageText, SendMessage
from app.bot.callbacks import LangCB
from app.bot.keyboards.menu import language_picker, main_menu
from app.bot.routers.start import language_screen, open_menu, pick_language
from app.db.models.users import User
from app.services.user_prefs import PrefsError, needs_language, set_language, update_prefs
from tests.test_view import _Bot, _callback, _message, _of, _state

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")


def _user(**kw) -> User:
    base = {"telegram_id": 50, "language_code": "uz", "ui_language_set": False}
    base.update(kw)
    return User(**base)


def _codes(markup) -> list[str]:
    return [row[0].callback_data for row in markup.inline_keyboard]


class _Links:
    """Plain /start never claims a student. The argument is still required."""

    async def enroll(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("menu start must not enroll")

    async def claim(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("menu start must not claim")


async def test_new_user_gets_the_language_picker_before_the_menu() -> None:
    bot = _Bot()
    await open_menu(_message(bot, text="/start"), _state(), "uz", False, _user(), _Links())
    sent = _of(bot, SendMessage)
    assert len(sent) == 1
    assert "Choose your language" in sent[0].text
    codes = _codes(sent[0].reply_markup)
    assert codes[:3] == [LangCB(v=c, f=1).pack() for c in ("uz", "ru", "en")]
    assert len(codes) == 3  # no back button on the first run


async def test_existing_user_with_a_language_goes_straight_to_the_menu() -> None:
    bot = _Bot()
    await open_menu(
        _message(bot, text="/start"),
        _state(),
        "ru",
        False,
        _user(ui_language_set=True),
        _Links(),
    )
    sent = _of(bot, SendMessage)
    assert "Choose your language" not in sent[0].text
    assert sent[0].reply_markup == main_menu("ru", False)


async def test_picking_saves_the_language_and_shows_the_menu_in_it() -> None:
    bot = _Bot()
    user = _user()
    await pick_language(_callback(bot, _message(bot)), LangCB(v="ru", f=1), user, False)
    assert user.language_code == "ru" and user.ui_language_set is True
    assert not needs_language(user)
    edit = _of(bot, EditMessageText)[-1]
    assert "Русский" in edit.text and "Здравствуйте" in edit.text


async def test_unknown_code_is_refused_and_nothing_changes() -> None:
    bot = _Bot()
    user = _user()
    await pick_language(_callback(bot, _message(bot)), LangCB(v="de"), user, False)
    assert user.language_code == "uz" and user.ui_language_set is False


async def test_menu_has_a_language_entry_with_back_button() -> None:
    labels = [row[0].text for row in main_menu("uz", False).inline_keyboard]
    assert any("Til" in label for label in labels)
    bot = _Bot()
    await language_screen(_callback(bot, _message(bot)), "en")
    markup = _of(bot, EditMessageText)[-1].reply_markup
    assert markup.inline_keyboard[0][0].text == "🇺🇿 O‘zbekcha"
    assert len(markup.inline_keyboard) == 4  # 3 languages + back
    assert language_picker("en").inline_keyboard[2][0].text.startswith("✅")


def test_bot_and_mini_app_share_one_rule() -> None:
    user = _user()
    with pytest.raises(PrefsError):
        set_language(user, "xx")
    with pytest.raises(PrefsError):
        update_prefs(user, {"language": "xx"})
    update_prefs(user, {"language": "en"})
    assert user.language_code == "en" and user.ui_language_set is True


@pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
async def test_migration_0012_marks_existing_users_as_having_chosen() -> None:
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": _URL}

    def alembic(*args: str) -> None:
        done = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert done.returncode == 0, done.stderr[-2000:]

    dsn = _URL.replace("postgresql+asyncpg://", "postgresql://")
    tg = 9890000001
    alembic("downgrade", "0011_usage_daily")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DELETE FROM users WHERE telegram_id = $1", tg)
        await conn.execute("INSERT INTO users (telegram_id, language_code) VALUES ($1, 'ru')", tg)
        alembic("upgrade", "head")
        row = await conn.fetchrow(
            "SELECT ui_language_set, notify_reports, notify_expiry, default_timezone "
            "FROM users WHERE telegram_id = $1",
            tg,
        )
        assert tuple(row) == (True, True, True, None)
        await conn.execute("DELETE FROM users WHERE telegram_id = $1", tg)
        await conn.execute("INSERT INTO users (telegram_id) VALUES ($1)", tg)
        fresh = await conn.fetchval("SELECT ui_language_set FROM users WHERE telegram_id = $1", tg)
        assert fresh is False  # new users are asked on /start
    finally:
        await conn.execute("DELETE FROM users WHERE telegram_id = $1", tg)
        await conn.close()
