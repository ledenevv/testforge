"""Telegram bot implementations: Mock and Real."""

from testforge.telegram.mock_bot import MockTelegramBot
from testforge.telegram.models import (
    ProfileData,
    TelegramMessage,
    TelegramUpdate,
    TelegramUser,
)

__all__ = [
    "MockTelegramBot",
    "TelegramMessage",
    "TelegramUpdate",
    "TelegramUser",
    "ProfileData",
]
