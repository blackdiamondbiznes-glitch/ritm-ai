"""Students get a small keyboard; owners and teachers keep the full menu."""

from types import SimpleNamespace

from app.bot.join_reply import reply_text
from app.bot.keyboards.menu import student_menu
from app.bot.menus import home_view, menu_for
from app.db.repositories.users import teacher_name_of
from app.i18n import t


class _Modes:
    def __init__(self, teaching=(), learning=(), pending=(), card=False) -> None:
        self.found = {
            "teaching": list(teaching),
            "learning": list(learning),
            "pending": list(pending),
        }
        self.card = card

    async def for_user(self, user):
        return self.found

    async def has_card(self, user) -> bool:
        return self.card


class _Chats:
    def __init__(self, active: int = 0) -> None:
        self.active = active

    async def count_active(self, owner_id: int) -> int:
        return self.active


def _user(niche=None):
    return SimpleNamespace(id=1, telegram_id=10, cabinet_niche=niche)


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _data(markup) -> list[str]:
    return [b.callback_data or "" for row in markup.inline_keyboard for b in row]


async def test_only_student_gets_three_buttons() -> None:
    markup = await menu_for("uz", False, _user(), _Modes(learning=[{}]), _Chats())
    labels = _labels(markup)
    assert len(labels) == 3
    assert labels[1:] == [t("menu_help", "uz"), t("menu_language", "uz")]
    assert not any("plan" in d or "connect" in d for d in _data(markup))


async def test_card_without_group_counts_as_student() -> None:
    title, markup = await home_view("uz", False, _user(), _Modes(card=True), _Chats())
    assert title == t("menu_title_student", "uz")
    assert len(_labels(markup)) == 3


async def test_owner_teacher_and_newcomer_keep_full_menu() -> None:
    cases = [
        _Modes(learning=[{}]),  # studies but owns a chat
        _Modes(teaching=[{}], learning=[{}]),
        _Modes(),
    ]
    chats = [_Chats(1), _Chats(), _Chats()]
    for modes, owned in zip(cases, chats, strict=True):
        title, markup = await home_view("uz", False, _user(), modes, owned)
        assert title == t("menu_title", "uz")
        assert len(_labels(markup)) > 3
    _, markup = await home_view("uz", False, _user("tutor"), _Modes(learning=[{}]), _Chats())
    assert len(_labels(markup)) > 3


def test_admin_row_stays_for_super_admin() -> None:
    assert len(_labels(student_menu("ru", True, webapp_url=""))) == 4


def test_named_texts_fall_back_to_short_ones() -> None:
    named = reply_text("join", "ok", "uz", "TEST Ingliz A1", "Malika")
    assert "«TEST Ingliz A1»" in named and "Malika" in named
    assert reply_text("join", "ok", "uz", None, "Malika") == t(
        "join_ok_teacher", "uz", teacher="Malika"
    )
    assert reply_text("join", "ok", "ru", None, None) == t("join_ok", "ru")
    assert reply_text("join", "taken", "en", "A", "B") == t("join_taken", "en")
    assert "B1" in reply_text("enroll", "pending", "en", "B1", "Ann")


def test_teacher_name_falls_back_to_telegram_name() -> None:
    assert teacher_name_of(SimpleNamespace(teacher_name="  ", full_name="Ali")) == "Ali"
    assert teacher_name_of(SimpleNamespace(teacher_name="Malika opa", full_name="Ali")) == (
        "Malika opa"
    )
    assert teacher_name_of(None) == ""
