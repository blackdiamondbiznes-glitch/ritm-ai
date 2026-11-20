"""Plan catalog and founder-sale texts. Dynamic values are HTML-escaped."""

from html import escape

from app.db.models.plans import Plan
from app.i18n import t
from app.services.access import FounderOffer, PlanSnapshot
from app.services.pricing import format_soum, founder_percent, is_paid_plan


def plan_text(snap: PlanSnapshot, plans: list[Plan], lang: str, offer: FounderOffer) -> str:
    """Current limits, a founder banner and the price list."""
    expiry = t("plan_expiry_none", lang)
    if snap.days_left is not None:
        expiry = t("plan_expiry_days", lang, days=snap.days_left)
    return t(
        "plan_screen",
        lang,
        plan=_plan_name(snap, lang),
        expiry=expiry,
        used=snap.chats_used,
        max=snap.plan.max_chats,
        ai_used=snap.ai_used,
        ai_max=snap.plan.ai_generations_per_month,
        promo=_promo_block(offer, plans, lang),
        catalog=_catalog(plans, lang, offer),
    )


def pay_plan_text(plans: list[Plan], lang: str, offer: FounderOffer) -> str:
    """Intro for the paid-plan picker, with sale prices when they apply."""
    catalog = _catalog([plan for plan in plans if is_paid_plan(plan)], lang, offer)
    return t("pay_pick_plan", lang) + _promo_block(offer, plans, lang) + catalog


def promo_line(offer: FounderOffer, plans: list[Plan], lang: str) -> str:
    """Single banner used on the quote screen, or empty."""
    return _promo_block(offer, plans, lang).strip()


def _promo_block(offer: FounderOffer, plans: list[Plan], lang: str) -> str:
    parts: list[str] = []
    if offer.keep:
        parts.append(t("plan_founder_keep", lang))
    elif offer.remaining > 0:
        parts.append(
            t(
                "plan_promo",
                lang,
                slots=offer.slots,
                percent=founder_percent(plans),
                left=offer.remaining,
            )
        )
    if not parts:
        return "\n"
    return "\n" + "\n".join(parts) + "\n\n"


def _catalog(plans: list[Plan], lang: str, offer: FounderOffer) -> str:
    return "\n".join(_plan_line(plan, lang, offer) for plan in plans)


def _plan_line(plan: Plan, lang: str, offer: FounderOffer) -> str:
    regular = format_soum(int(plan.price_uzs))
    sale = format_soum(int(plan.founder_price_uzs))
    if offer.show_sale and is_paid_plan(plan) and int(plan.founder_price_uzs) < int(plan.price_uzs):
        return t(
            "plan_line_sale",
            lang,
            name=escape(plan.name),
            price=regular,
            founder=sale,
            chats=plan.max_chats,
            ai=plan.ai_generations_per_month,
        )
    return t(
        "plan_line",
        lang,
        name=escape(plan.name),
        price=regular,
        chats=plan.max_chats,
        ai=plan.ai_generations_per_month,
    )


def _plan_name(snap: PlanSnapshot, lang: str) -> str:
    name = escape(snap.plan.name)
    if snap.kind == "trial":
        return t("plan_trial", lang, name=name)
    if snap.kind == "active":
        return t("plan_active", lang, name=name)
    return t("plan_free", lang, name=name)
