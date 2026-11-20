"""Super-admin system status screen."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AdminCB
from app.bot.keyboards.menu import admin_menu, main_menu
from app.bot.view import show_screen
from app.config import Settings
from app.i18n import t
from app.services.health import HealthReport, HealthService

router = Router(name="admin_health")


@router.callback_query(AdminCB.filter(F.a == "health"))
async def show_health(
    callback: CallbackQuery,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """DB latency, last tick, AI config and job counts."""
    if not is_super_admin:
        await state.clear()
        await show_screen(callback, t("admin_denied", lang), main_menu(lang, False))
        return
    report = await HealthService(session, settings).report()
    await show_screen(callback, render_health(report, lang), admin_menu(lang))


def render_health(report: HealthReport, lang: str) -> str:
    """Turn a snapshot into a locale string. No secrets."""
    db = t("health_db_fail", lang)
    if report.db_ok and report.db_ms is not None:
        db = t("health_db_ok", lang, ms=report.db_ms)
    tick = t("health_tick_never", lang)
    if report.tick_age_seconds is not None:
        tick = t("health_tick_age", lang, seconds=report.tick_age_seconds)
    ai = t("health_ai_yes", lang) if report.ai_configured else t("health_ai_no", lang)
    return t(
        "health_text",
        lang,
        db=db,
        tick=tick,
        provider=report.provider,
        model=report.model,
        ai=ai,
        pending=report.pending_jobs,
        failed=report.failed_24h,
    )
