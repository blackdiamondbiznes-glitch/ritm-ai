"""Inline keyboards. Labels always come from locales."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.bot.callbacks import AdminCB, ConnectCB, LangCB, MenuCB, PlanCB
from app.i18n import t
from app.services.pending import PendingChat


def main_menu(
    lang: str,
    is_admin: bool,
    webapp_url: str | None = None,
    *,
    teaching: bool = False,
    learning: bool = False,
) -> InlineKeyboardMarkup:
    """Root menu. Admin row is added only for super admins."""
    rows = []
    url = webapp_url if webapp_url is not None else _menu_webapp_url()
    if url:
        rows.append(
            [InlineKeyboardButton(text=t("menu_webapp", lang), web_app=WebAppInfo(url=url))]
        )
        if teaching:
            rows.append([_web(t("menu_teach", lang), _cabinet_url(url))])
        if learning:
            rows.append([_btn(t("menu_learn", lang), MenuCB(a="learn").pack())])
    rows.extend(
        [
            [_btn(t("menu_connect", lang), MenuCB(a="connect").pack())],
            [_btn(t("menu_chats", lang), MenuCB(a="chats").pack())],
            [_btn(t("menu_plan", lang), MenuCB(a="plan").pack())],
            [_btn(t("menu_help", lang), MenuCB(a="help").pack())],
            [_btn(t("menu_language", lang), MenuCB(a="lang").pack())],
        ]
    )
    if is_admin:
        rows.append([_btn(t("menu_admin", lang), MenuCB(a="admin").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def student_menu(lang: str, is_admin: bool, webapp_url: str | None = None) -> InlineKeyboardMarkup:
    """Only-student accounts: their study page, help and language. No owner or plan rows."""
    rows = []
    url = webapp_url if webapp_url is not None else _menu_webapp_url()
    if url:
        rows.append([_web(f"🎒 {t('learn_open', lang)}", _role_url(url, "student"))])
    else:
        rows.append([_btn(t("menu_learn", lang), MenuCB(a="learn").pack())])
    rows.append([_btn(t("menu_help", lang), MenuCB(a="help").pack())])
    rows.append([_btn(t("menu_language", lang), MenuCB(a="lang").pack())])
    if is_admin:
        rows.append([_btn(t("menu_admin", lang), MenuCB(a="admin").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def study_keyboard(lang: str, url: str | None) -> InlineKeyboardMarkup:
    """Open the Mini App in student mode, or go back when no URL is configured."""
    rows = []
    if url:
        rows.append([_web(t("learn_open", lang), _role_url(url, "student"))])
    rows.append([_btn(t("back", lang), MenuCB(a="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_menu(lang: str) -> InlineKeyboardMarkup:
    """Single back button to the main menu."""
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(t("back", lang), MenuCB(a="home").pack())]])


def connect_intro(lang: str) -> InlineKeyboardMarkup:
    """How-to screen: check recent adds, or go back."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("connect_check", lang), ConnectCB(a="check").pack())],
            [_btn(t("back", lang), MenuCB(a="home").pack())],
        ]
    )


def connect_confirm(lang: str, telegram_chat_id: int) -> InlineKeyboardMarkup:
    """Confirm or dismiss one pending chat."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("connect_confirm", lang), ConnectCB(a="ok", id=telegram_chat_id).pack())],
            [_btn(t("connect_decline", lang), ConnectCB(a="no", id=telegram_chat_id).pack())],
        ]
    )


def connect_pick(lang: str, rows: list[PendingChat]) -> InlineKeyboardMarkup:
    """Several pending chats."""
    buttons = [
        [_btn(_clip(row.title), ConnectCB(a="pick", id=row.telegram_chat_id).pack())]
        for row in rows[:8]
    ]
    buttons.append([_btn(t("back", lang), MenuCB(a="connect").pack())])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def plan_actions(lang: str) -> InlineKeyboardMarkup:
    """Payment is intentionally not wired in phase 1."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("plan_pay", lang), PlanCB(a="pay").pack())],
            [_btn(t("back", lang), MenuCB(a="home").pack())],
        ]
    )


def admin_menu(lang: str) -> InlineKeyboardMarkup:
    """Admin home."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("admin_stats", lang), AdminCB(a="stats").pack())],
            [_btn(t("admin_payments", lang), AdminCB(a="pays").pack())],
            [_btn(t("admin_health", lang), AdminCB(a="health").pack())],
            [_btn(t("admin_grant", lang), AdminCB(a="grant").pack())],
            [_btn(t("admin_block", lang), AdminCB(a="block").pack())],
            [_btn(t("back", lang), MenuCB(a="home").pack())],
        ]
    )


def cancel_row(lang: str) -> InlineKeyboardMarkup:
    """Cancel a text step and return home."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(t("cancel", lang), MenuCB(a="home").pack())]]
    )


def _role_url(base: str, role: str) -> str:
    return f"{base.split('#', 1)[0].split('?', 1)[0]}#role={role}"


def _cabinet_url(base: str) -> str:
    """Mini App deep link. startapp=cabinet is read on open; the hash is the route."""
    root = base.split("#", 1)[0].split("?", 1)[0]
    return f"{root}?startapp=cabinet#/cabinet"


def _web(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))


def _menu_webapp_url() -> str | None:
    try:
        from app.config import get_settings

        return get_settings().public_webapp_url
    except Exception:
        return None


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _clip(title: str) -> str:
    clean = title.strip() or "Chat"
    if len(clean) <= 40:
        return clean
    return clean[:39] + "…"


LANGUAGE_NAMES = (("uz", "🇺🇿 O‘zbekcha"), ("ru", "🇷🇺 Русский"), ("en", "🇬🇧 English"))


def language_picker(current: str | None = None, *, first: bool = False) -> InlineKeyboardMarkup:
    """Three language buttons; the current one is marked. No back button on the first run."""
    rows = [
        [_btn(f"{'✅ ' if code == current else ''}{name}", LangCB(v=code, f=int(first)).pack())]
        for code, name in LANGUAGE_NAMES
    ]
    if not first:
        rows.append([_btn(t("back", current or "uz"), MenuCB(a="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
