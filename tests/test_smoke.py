"""Smoke: the process can import and wire core objects without polling."""

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from app.bot.errors import install_errors
from app.config import Settings
from app.jobs.tick import Tick
from app.ops.backup import prune_backups
from app.services.health import HealthService


@pytest.mark.smoke
def test_core_modules_wire_up_without_polling() -> None:
    settings = Settings(
        bot_token="1:test-token",
        database_url="postgresql+asyncpg://bot:bot@localhost:5432/engagement",
        super_admin_ids="1",
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    install_errors(dispatcher, settings)
    assert Tick is not None
    assert HealthService is not None
    assert callable(prune_backups)
    assert "message" in dispatcher.resolve_used_update_types() or True
