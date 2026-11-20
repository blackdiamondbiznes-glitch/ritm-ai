"""FSM states for the flows that ask for text."""

from aiogram.fsm.state import State, StatesGroup


class ProfileSG(StatesGroup):
    """Niche wizard. Each step can go back."""

    niche = State()
    niche_custom = State()
    description = State()
    tone = State()
    audience = State()
    language = State()
    timezone = State()
    summary = State()


class GrantSG(StatesGroup):
    """Super admin grants a plan."""

    telegram_id = State()
    plan = State()
    days = State()


class BlockSG(StatesGroup):
    """Super admin blocks or unblocks by Telegram id."""

    action = State()
    telegram_id = State()


class PaySG(StatesGroup):
    """Evidence after a transfer: card last 4, transfer time, receipt. Then disputes."""

    last4 = State()
    when = State()
    receipt = State()
    dispute = State()


class RejectSG(StatesGroup):
    """Super admin types a rejection reason."""

    reason = State()
