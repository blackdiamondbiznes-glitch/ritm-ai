"""Register the public commands in each locale."""

from aiogram import Bot
from aiogram.types import BotCommand

from app.i18n import t

_LANGS = ("uz", "ru", "en")


async def setup_commands(bot: Bot) -> None:
    """Uzbek is the default command list. ru and en get their own lists."""
    for lang in _LANGS:
        commands = [
            BotCommand(command="start", description=t("cmd_start", lang)),
            BotCommand(command="menu", description=t("cmd_menu", lang)),
            BotCommand(command="help", description=t("cmd_help", lang)),
            BotCommand(command="cancel", description=t("cmd_cancel", lang)),
            BotCommand(command="language", description=t("cmd_language", lang)),
            BotCommand(command="panel", description=t("cmd_panel", lang)),
        ]
        code = None if lang == "uz" else lang
        await bot.set_my_commands(commands, language_code=code)
