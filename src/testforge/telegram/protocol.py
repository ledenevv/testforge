"""Common interface shared by MockTelegramBot and RealTelegramBot."""

from pathlib import Path
from typing import Protocol, Self, runtime_checkable

from testforge.telegram.models import TelegramMessage, TelegramUpdate


@runtime_checkable
class TelegramBot(Protocol):
    """Interface the executor relies on; satisfied by both bot implementations."""

    sent_messages: list[TelegramMessage]

    async def send_message(self, text: str) -> TelegramMessage: ...

    async def send_document(
        self,
        file_path: str | Path,
        caption: str | None = None,
    ) -> TelegramMessage: ...

    async def get_updates(self, timeout: int = 10) -> list[TelegramUpdate]: ...

    def reset(self) -> None: ...

    async def close(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *args: object) -> None: ...
