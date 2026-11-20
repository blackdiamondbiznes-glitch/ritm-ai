"""Profile wizard keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import WizardCB
from app.i18n import t
from app.services.profiles import TIMEZONES

_NICHES = ("lang", "biz", "fit", "it", "edu", "news")
_TONES = ("formal", "friendly", "motiv", "fun")
_LEVELS = ("beginner", "mid", "high", "mixed")
_LANGS = (("uz", "lang_uz"), ("ru", "lang_ru"), ("en", "lang_en"))


def niche_kb(lang: str) -> InlineKeyboardMarkup:
    """Preset niches plus Other, back and cancel."""
    rows = [[_btn(t(f"niche_{code}", lang), "niche", code)] for code in _NICHES]
    rows.append([_btn(t("niche_other", lang), "niche", "other")])
    rows.append(_nav(lang, back=False))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def choice_kb(lang: str, action: str, codes: tuple[str, ...], prefix: str) -> InlineKeyboardMarkup:
    """Generic single-choice step."""
    rows = [[_btn(t(f"{prefix}_{code}", lang), action, code)] for code in codes]
    rows.append(_nav(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tone_kb(lang: str) -> InlineKeyboardMarkup:
    """Tone step."""
    return choice_kb(lang, "tone", _TONES, "tone")


def audience_kb(lang: str) -> InlineKeyboardMarkup:
    """Audience step."""
    return choice_kb(lang, "aud", _LEVELS, "aud")


def language_kb(lang: str) -> InlineKeyboardMarkup:
    """Content language step."""
    rows = [[_btn(t(key, lang), "lang", code)] for code, key in _LANGS]
    rows.append(_nav(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timezone_kb(lang: str) -> InlineKeyboardMarkup:
    """Keep the default or open the short list."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("tz_keep", lang), "tzkeep", "-")],
            [_btn(t("tz_change", lang), "tzopen", "-")],
            _nav(lang),
        ]
    )


def timezone_list_kb(lang: str) -> InlineKeyboardMarkup:
    """A few common zones. The default is included."""
    rows = [[_btn(zone, "tz", zone)] for zone in sorted(TIMEZONES)]
    rows.append(_nav(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def summary_kb(lang: str) -> InlineKeyboardMarkup:
    """Save, back, cancel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("save", lang), "save", "-")],
            _nav(lang),
        ]
    )


def text_step_kb(lang: str) -> InlineKeyboardMarkup:
    """Back and cancel while the user is typing."""
    return InlineKeyboardMarkup(inline_keyboard=[_nav(lang)])


def _nav(lang: str, back: bool = True) -> list[InlineKeyboardButton]:
    row = []
    if back:
        row.append(_btn(t("back", lang), "back", "-"))
    row.append(_btn(t("cancel", lang), "cancel", "-"))
    return row


def _btn(text: str, action: str, value: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=WizardCB(a=action, v=value).pack())
