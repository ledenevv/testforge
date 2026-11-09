"""Telegram bot implementations: Mock and Real."""

from testforge.telegram.mock_bot import MockTelegramBot
from testforge.telegram.models import (
    ProfileData,
    TelegramMessage,
    TelegramUpdate,
    TelegramUser,
)
from testforge.telegram.protocol import TelegramBot
from testforge.telegram.real_bot import RealTelegramBot, TelegramAPIError
from testforge.telegram.user_bot import TelegramUserBot, TelegramUserBotError

__all__ = [
    "TelegramBot",
    "MockTelegramBot",
    "RealTelegramBot",
    "TelegramAPIError",
    "TelegramUserBot",
    "TelegramUserBotError",
    "TelegramMessage",
    "TelegramUpdate",
    "TelegramUser",
    "ProfileData",
]
