"""Real-mode bot client that talks to the bot as a test user (ADR-006, option A).

Messages go out from a dedicated Telegram account over MTProto (Telethon), and the
bot's replies arrive on the same account. The Bot API cannot do this: a bot never
receives its own replies or messages from other bots.
"""

import asyncio
import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from testforge.telegram.models import TelegramMessage, TelegramUpdate, TelegramUser

ENV_API_ID = "TESTFORGE_TG_API_ID"
ENV_API_HASH = "TESTFORGE_TG_API_HASH"
ENV_SESSION = "TESTFORGE_TG_SESSION"
ENV_BOT = "TESTFORGE_TG_BOT"
REQUIRED_ENV = (ENV_API_ID, ENV_API_HASH, ENV_SESSION, ENV_BOT)


class TelegramUserBotError(RuntimeError):
    """The test account cannot talk to the bot: settings missing, no session, or wrong target."""


class TelegramUserBot:
    """Sends and receives as a test user. Satisfies the TelegramBot protocol."""

    def __init__(self, client: TelegramClient, bot_username: str) -> None:
        self.client = client
        self.bot_username = bot_username.lstrip("@")
        self.sent_messages: list[TelegramMessage] = []
        self._replies: asyncio.Queue[TelegramMessage] = asyncio.Queue()
        self._bot_id: int | None = None
        self._me: TelegramUser | None = None
        self._update_id = 0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        """Build the client from TESTFORGE_TG_* variables. Nothing connects until start()."""
        source = os.environ if env is None else env
        missing = [name for name in REQUIRED_ENV if not source.get(name)]
        if missing:
            raise TelegramUserBotError(f"Missing environment variables: {', '.join(missing)}")
        try:
            api_id = int(source[ENV_API_ID])
        except ValueError as e:
            raise TelegramUserBotError(f"{ENV_API_ID} must be a number") from e
        client = TelegramClient(StringSession(source[ENV_SESSION]), api_id, source[ENV_API_HASH])
        return cls(client, source[ENV_BOT])

    async def start(self) -> None:
        """Connect with the saved session, check the target is a bot, and listen for replies."""
        if self._bot_id is not None:
            return
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise TelegramUserBotError(
                "The session is not authorized. Create one with scripts/telegram_login.py"
            )
        me = await self.client.get_me()
        self._me = TelegramUser(
            id=me.id,
            is_bot=False,
            first_name=me.first_name or "Test",
            username=me.username,
        )
        entity = await self.client.get_entity(self.bot_username)
        if not getattr(entity, "bot", False):
            raise TelegramUserBotError(f"@{self.bot_username} is not a bot")
        self._bot_id = entity.id
        self.client.add_event_handler(self._on_reply, events.NewMessage(from_users=entity.id))

    async def send_message(self, text: str) -> TelegramMessage:
        """Send a text message to the bot, as the test user."""
        bot_id, me = self._session()
        sent = await self.client.send_message(bot_id, text)
        return self._record(sent, me, text=text)

    async def send_document(
        self,
        file_path: str | Path,
        caption: str | None = None,
    ) -> TelegramMessage:
        """Send a file to the bot as a document, not as a compressed photo."""
        bot_id, me = self._session()
        path = Path(file_path)
        sent = await self.client.send_file(bot_id, path, caption=caption, force_document=True)
        return self._record(sent, me, text=caption, document={"file_name": path.name})

    async def get_updates(self, timeout: float = 10) -> list[TelegramUpdate]:
        """Replies that arrived since the last call.

        If nothing has arrived yet, waits up to `timeout` seconds for the first reply.
        """
        replies: list[TelegramMessage] = []
        if self._replies.empty() and timeout > 0:
            try:
                replies.append(await asyncio.wait_for(self._replies.get(), timeout))
            except TimeoutError:
                return []
        while not self._replies.empty():
            replies.append(self._replies.get_nowait())
        return [self._as_update(reply) for reply in replies]

    def reset(self) -> None:
        """Forget sent messages and drop replies nobody has read. The connection stays open."""
        self.sent_messages = []
        while not self._replies.empty():
            self._replies.get_nowait()

    async def close(self) -> None:
        """Disconnect from Telegram."""
        await self.client.disconnect()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _on_reply(self, event: Any) -> None:
        """Telethon calls this for every new message from the bot."""
        message = event.message
        sender = TelegramUser(
            id=int(message.sender_id or 0),
            is_bot=True,
            first_name=self.bot_username,
            username=self.bot_username,
        )
        reply = _to_message(message.id, event.chat_id, message.date, message.message, sender)
        await self._replies.put(reply)

    def _record(
        self,
        sent: Any,
        me: TelegramUser,
        text: str | None,
        document: dict[str, Any] | None = None,
    ) -> TelegramMessage:
        message = _to_message(sent.id, sent.chat_id, sent.date, text, me, document)
        self.sent_messages.append(message)
        return message

    def _as_update(self, message: TelegramMessage) -> TelegramUpdate:
        self._update_id += 1
        return TelegramUpdate(update_id=self._update_id, message=message)

    def _session(self) -> tuple[int, TelegramUser]:
        if self._bot_id is None or self._me is None:
            raise TelegramUserBotError("Call start() before talking to the bot")
        return self._bot_id, self._me


def _to_message(
    message_id: int,
    chat_id: int,
    sent_at: datetime,
    text: str | None,
    sender: TelegramUser,
    document: dict[str, Any] | None = None,
) -> TelegramMessage:
    return TelegramMessage.model_validate(
        {
            "message_id": message_id,
            "from": sender,
            "chat_id": chat_id,
            "date": sent_at,
            "text": text,
            "document": document,
        }
    )
