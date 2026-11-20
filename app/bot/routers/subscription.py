"""Plan screen and the entry point into the payment flow."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.callbacks import MenuCB
from app.bot.keyboards.payments import plan_actions
from app.bot.plan_copy import plan_text
from app.bot.view import show_screen
from app.db.models.users import User
from app.db.repositories.plans import PlanRepository
from app.services.access import AccessService

router = Router(name="subscription")


@router.callback_query(MenuCB.filter(F.a == "plan"))
async def show_plan(
    callback: CallbackQuery,
    current_user: User,
    access: AccessService,
    plans: PlanRepository,
    lang: str,
) -> None:
    """Effective plan, limits and the price list from the database."""
    snap = await access.snapshot(current_user)
    catalog = await plans.list_active()
    offer = await access.founder_offer(current_user)
    trial = snap.kind == "trial"
    await show_screen(
        callback, plan_text(snap, catalog, lang, offer), plan_actions(lang, trial=trial)
    )
