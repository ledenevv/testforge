"""Telegram bot implementations: Mock and Real."""

from testforge.telegram.mock_bot import MockTelegramBot
from testforge.telegram.models import (
    ProfileData,
    TelegramMessage,
    TelegramUpdate,
    TelegramUser,
)
from testforge.telegram.real_bot import RealTelegramBot, TelegramAPIError

__all__ = [
    "MockTelegramBot",
    "RealTelegramBot",
    "TelegramAPIError",
    "TelegramMessage",
    "TelegramUpdate",
    "TelegramUser",
    "ProfileData",
]
