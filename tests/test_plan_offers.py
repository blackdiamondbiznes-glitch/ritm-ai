"""Founder sale lines on the plan screen and the payment picker."""

from app.bot.plan_copy import pay_plan_text, plan_text, promo_line
from app.services.access import FounderOffer, PlanSnapshot
from tests.fakes import make_plans

SLOTS = FounderOffer(slots=20, used=3, remaining=17, keep=False)
FULL = FounderOffer(slots=20, used=20, remaining=0, keep=False)
KEEP = FounderOffer(slots=20, used=20, remaining=0, keep=True)


def _priced():
    plans = make_plans()
    mapping = {
        "free": (0, 0),
        "start": (29000, 20300),
        "pro": (39000, 27300),
        "agency": (69000, 48300),
    }
    for plan in plans:
        plan.price_uzs, plan.founder_price_uzs = mapping[plan.code]
    return plans


def _snap():
    plans = _priced()
    free = next(plan for plan in plans if plan.code == "free")
    return PlanSnapshot(plan=free, kind="free", days_left=None, chats_used=0, ai_used=0), plans


def test_plan_screen_shows_sale_and_slots_remaining() -> None:
    snap, plans = _snap()
    text = plan_text(snap, plans, "uz", SLOTS)
    assert "Birinchi 20 obunachiga −30%" in text
    assert "17 ta joy qoldi" in text
    assert "<s>29 000</s> 20 300" in text
    assert "<s>39 000</s> 27 300" in text
    assert "<s>69 000</s> 48 300" in text
    assert "Free" in text and "0 so" in text


def test_plan_screen_hides_promo_when_slots_are_gone() -> None:
    snap, plans = _snap()
    text = plan_text(snap, plans, "uz", FULL)
    assert "joy qoldi" not in text
    assert "asoschi" not in text
    assert "<s>" not in text
    assert "29 000 so" in text
    assert "20 300" not in text


def test_founder_keeps_sale_price_when_slots_are_full() -> None:
    snap, plans = _snap()
    text = plan_text(snap, plans, "uz", KEEP)
    assert "Siz asoschi narxini saqlab qolasiz." in text
    assert "joy qoldi" not in text
    assert "<s>29 000</s> 20 300" in text
    picker = pay_plan_text(plans, "uz", KEEP)
    assert "Siz asoschi narxini saqlab qolasiz." in picker
    assert promo_line(KEEP, plans, "uz") == "Siz asoschi narxini saqlab qolasiz."
