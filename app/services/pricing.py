"""Payment amounts, period discounts and display helpers."""

from decimal import ROUND_HALF_UP, Decimal

from app.db.models.plans import Plan

PERIODS = (1, 3, 12)
DEFAULT_PERIOD_DISCOUNTS = {3: 7, 12: 15}


def parse_period_discounts(raw: str) -> dict[int, int]:
    """Parse ``3:7,12:15`` into month-to-percent. Empty keys are ignored."""
    found: dict[int, int] = {}
    for part in (raw or "").split(","):
        token = part.strip()
        if not token or ":" not in token:
            continue
        months_raw, percent_raw = token.split(":", 1)
        if not months_raw.strip().isdigit() or not percent_raw.strip().lstrip("-").isdigit():
            continue
        months = int(months_raw)
        percent = int(percent_raw)
        if months in PERIODS and 0 <= percent < 100:
            found[months] = percent
    return found


def period_percent(months: int, discounts: dict[int, int] | None = None) -> int:
    """Period discount percent for this length. One month is always 0."""
    if months == 1:
        return 0
    return int((discounts or {}).get(months, 0))


def round_soum(amount: int | float | Decimal) -> int:
    """Nearest 100 so'm, halves rounded away from zero."""
    quanta = (Decimal(str(amount)) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(quanta * 100)


def total_amount(monthly: int, months: int, percent: int = 0) -> int:
    """Charge months times the monthly price, then apply a period percent."""
    if months not in PERIODS:
        raise ValueError("months")
    if percent < 0 or percent >= 100:
        raise ValueError("percent")
    listed = monthly * months
    if percent == 0:
        return listed
    return round_soum(Decimal(listed) * Decimal(100 - percent) / Decimal(100))


def paid_days(months: int) -> int:
    """Paid length in days. A month is 30 days, as in the plans table."""
    if months not in PERIODS:
        raise ValueError("months")
    return months * 30


def is_paid_plan(plan: Plan) -> bool:
    """Free is not sold through the payment flow."""
    return plan.code != "free" and bool(plan.is_active)


def format_soum(amount: int) -> str:
    """Group thousands with spaces."""
    return f"{amount:,}".replace(",", " ")


def founder_percent(plans: list[Plan]) -> int:
    """Typical founder discount across paid plans that have a sale price."""
    for plan in plans:
        regular = int(plan.price_uzs)
        sale = int(plan.founder_price_uzs)
        if regular > 0 and 0 < sale < regular:
            return int(
                ((Decimal(regular - sale) / Decimal(regular)) * 100).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
    return 0
