"""One apostrophe style for Uzbek text: o‘/g‘ use U+2018, the tutuq sign U+02BC."""

from app.i18n import normalize_uz, t


def test_letters_get_the_right_mark() -> None:
    assert normalize_uz("so'm") == "so\u2018m"
    assert normalize_uz("bog'laning") == "bog\u2018laning"
    assert normalize_uz("E'lon") == "E\u02bclon"
    assert normalize_uz("ta\u2019lim") == "ta\u02bclim"


def test_no_mark_is_added_at_the_end() -> None:
    assert normalize_uz("bosing") == "bosing"
    assert normalize_uz("1 oy") == "1 oy"
    assert normalize_uz("") == ""


def test_markup_and_params_stay_intact() -> None:
    assert normalize_uz('<a href="https://t.me/x">Ali</a>') == '<a href="https://t.me/x">Ali</a>'
    assert normalize_uz("<code>39 047</code>") == "<code>39 047</code>"


def test_t_normalises_uzbek_only() -> None:
    assert t("button_stale", "uz") == "Bu tugma eskirgan, /menu ni bosing"
    assert "'" not in t("menu_title", "uz")
    assert t("menu_teach", "ru") == "👩‍🏫 Кабинет преподавателя"
