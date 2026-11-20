"""Callback payloads. Every handler re-checks rights; these ids are untrusted."""

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    """Main menu actions."""

    a: str


class ConnectCB(CallbackData, prefix="c"):
    """Connect-flow actions. `id` is a Telegram chat id."""

    a: str
    id: int = 0


class WizardCB(CallbackData, prefix="w"):
    """Profile wizard. `v` is a short code, never free text."""

    a: str
    v: str = "-"


class ChatCB(CallbackData, prefix="h"):
    """Chat list actions. `id` is the internal chat id."""

    a: str
    id: int = 0


class PlanCB(CallbackData, prefix="b"):
    """Plan screen actions."""

    a: str


class AdminCB(CallbackData, prefix="a"):
    """Admin panel actions. `v` is a plan code or a day count."""

    a: str
    v: str = "-"


class DailyCB(CallbackData, prefix="d"):
    """Daily schedule actions. `v` is a clock code such as 0900."""

    a: str
    id: int = 0
    v: str = "-"


class QuizCB(CallbackData, prefix="u"):
    """Quiz schedule actions. `v` is a clock code such as 0900."""

    a: str
    id: int = 0
    v: str = "-"


class PickCB(CallbackData, prefix="q"):
    """An answer button posted into the chat. `v` is 0..3."""

    id: int
    v: str


class BoardCB(CallbackData, prefix="r"):
    """Leaderboard schedule actions. `v` is a weekday or a clock code."""

    a: str
    id: int = 0
    v: str = "-"


class PayCB(CallbackData, prefix="p"):
    """Owner payment actions. `v` is a plan code or plan:months."""

    a: str
    v: str = "-"


class AdminPayCB(CallbackData, prefix="ap"):
    """Super-admin review of one payment. `v` is a short reason code."""

    a: str
    id: int = 0
    v: str = "-"


class LangCB(CallbackData, prefix="l"):
    """UI language picker. `v` is uz, ru or en; `f` is 1 on the first /start."""

    v: str
    f: int = 0
