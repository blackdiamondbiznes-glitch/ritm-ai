"""Mini App buttons placed under a widget, as a fallback open path."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.bot.keyboards.menu import _cabinet_url, _menu_webapp_url, _role_url
from app.i18n import t


def study_markup(lang: str) -> InlineKeyboardMarkup | None:
    """Open the student cabinet."""
    url = _menu_webapp_url()
    if not url:
        return None
    return _one(t("learn_open", lang), _role_url(url, "student"))


def cabinet_markup(lang: str) -> InlineKeyboardMarkup | None:
    """Open the teacher cabinet."""
    url = _menu_webapp_url()
    if not url:
        return None
    return _one(t("menu_teach", lang), _cabinet_url(url))


def _one(text: str, url: str) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def with_join(
    markup: InlineKeyboardMarkup | None, url: object, lang: str
) -> InlineKeyboardMarkup | None:
    """Put a plain URL button for the online lesson above any other buttons."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return markup
    join = [InlineKeyboardButton(text=t("lesson_join", lang), url=url)]
    rows = list(markup.inline_keyboard) if markup is not None else []
    return InlineKeyboardMarkup(inline_keyboard=[join, *rows])
