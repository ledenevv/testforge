"""Unit tests for TelegramUserBot: the test account talks to the bot over MTProto (ADR-006).

Telethon is replaced by a fake client, so nothing touches the network.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from telethon.crypto import AuthKey
from telethon.sessions import StringSession

from testforge.telegram import TelegramBot
from testforge.telegram.user_bot import TelegramUserBot, TelegramUserBotError

BOT_ID = 777000111
ME_ID = 555000222
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def _session_string() -> str:
    """A well-formed session string: Telethon decodes it when the client is created."""
    session = StringSession()
    session.set_dc(2, "149.154.167.51", 443)
    session.auth_key = AuthKey(bytes(range(256)))
    return session.save()


ENV = {
    "TESTFORGE_TG_API_ID": "123456",
    "TESTFORGE_TG_API_HASH": "0123456789abcdef0123456789abcdef",
    "TESTFORGE_TG_SESSION": _session_string(),
    "TESTFORGE_TG_BOT": "@ask_toby_staging_bot",
}


class FakeTelethonClient:
    """Stands in for telethon.TelegramClient. Records calls and delivers replies on demand."""

    def __init__(self, *, authorized: bool = True, bot_is_bot: bool = True) -> None:
        self.authorized = authorized
        self.bot_is_bot = bot_is_bot
        self.sent: list[tuple[int, str]] = []
        self.files: list[dict[str, object]] = []
        self.handlers: list[tuple[object, object]] = []
        self.disconnected = False
        self._ids = iter(range(1, 1000))

    async def connect(self) -> None:
        return None

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def get_me(self) -> SimpleNamespace:
        return SimpleNamespace(id=ME_ID, first_name="Tester", username="tester")

    async def get_entity(self, username: str) -> SimpleNamespace:
        return SimpleNamespace(id=BOT_ID, bot=self.bot_is_bot, username=username)

    def add_event_handler(self, callback: object, event: object) -> None:
        self.handlers.append((callback, event))

    async def send_message(self, entity: int, text: str) -> SimpleNamespace:
        self.sent.append((entity, text))
        return SimpleNamespace(id=next(self._ids), date=NOW, chat_id=BOT_ID)

    async def send_file(
        self,
        entity: int,
        file: object,
        caption: str | None = None,
        force_document: bool = False,
    ) -> SimpleNamespace:
        self.files.append(
            {"entity": entity, "file": file, "caption": caption, "force_document": force_document}
        )
        return SimpleNamespace(id=next(self._ids), date=NOW, chat_id=BOT_ID)

    async def disconnect(self) -> None:
        self.disconnected = True

    async def deliver(self, text: str, message_id: int = 900) -> None:
        """Simulate the bot's reply the way Telethon does: call the registered handler."""
        event = SimpleNamespace(
            chat_id=BOT_ID,
            message=SimpleNamespace(id=message_id, date=NOW, message=text, sender_id=BOT_ID),
        )
        for callback, _ in self.handlers:
            await callback(event)


async def started(
    fake: FakeTelethonClient | None = None,
) -> tuple[TelegramUserBot, FakeTelethonClient]:
    fake = fake or FakeTelethonClient()
    bot = TelegramUserBot(fake, "@ask_toby_staging_bot")
    await bot.start()
    return bot, fake


class TestSettings:
    def test_missing_variables_are_named(self):
        env = {name: value for name, value in ENV.items() if name != "TESTFORGE_TG_SESSION"}

        with pytest.raises(TelegramUserBotError, match="TESTFORGE_TG_SESSION"):
            TelegramUserBot.from_env(env)

    def test_api_id_must_be_a_number(self):
        with pytest.raises(TelegramUserBotError, match="TESTFORGE_TG_API_ID must be a number"):
            TelegramUserBot.from_env({**ENV, "TESTFORGE_TG_API_ID": "abc"})

    def test_from_env_strips_the_at_sign_from_the_bot_name(self):
        bot = TelegramUserBot.from_env(ENV)

        assert bot.bot_username == "ask_toby_staging_bot"
        assert bot.sent_messages == []


class TestStart:
    @pytest.mark.asyncio
    async def test_refuses_a_session_that_is_not_authorized(self):
        bot = TelegramUserBot(FakeTelethonClient(authorized=False), "ask_toby_staging_bot")

        with pytest.raises(TelegramUserBotError, match=r"telegram_login\.py"):
            await bot.start()

    @pytest.mark.asyncio
    async def test_refuses_a_target_that_is_not_a_bot(self):
        bot = TelegramUserBot(FakeTelethonClient(bot_is_bot=False), "ask_toby_staging_bot")

        with pytest.raises(TelegramUserBotError, match="is not a bot"):
            await bot.start()

    @pytest.mark.asyncio
    async def test_listens_only_to_messages_from_the_bot(self):
        _, fake = await started()

        assert len(fake.handlers) == 1
        _, event = fake.handlers[0]
        assert event.from_users == BOT_ID

    @pytest.mark.asyncio
    async def test_second_start_does_not_add_a_second_listener(self):
        bot, fake = await started()

        await bot.start()

        assert len(fake.handlers) == 1


class TestSending:
    @pytest.mark.asyncio
    async def test_send_message_goes_to_the_bot_and_is_recorded(self):
        bot, fake = await started()

        message = await bot.send_message("/start")

        assert fake.sent == [(BOT_ID, "/start")]
        assert message.text == "/start"
        assert message.from_user.id == ME_ID
        assert message.from_user.is_bot is False
        assert bot.sent_messages == [message]

    @pytest.mark.asyncio
    async def test_document_is_sent_as_a_file_not_a_photo(self, tmp_path):
        bot, fake = await started()
        pdf = tmp_path / "lab_report.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")

        message = await bot.send_document(pdf, caption="Мои анализы")

        assert fake.files == [
            {"entity": BOT_ID, "file": pdf, "caption": "Мои анализы", "force_document": True}
        ]
        assert message.document == {"file_name": "lab_report.pdf"}

    @pytest.mark.asyncio
    async def test_sending_before_start_is_refused(self):
        bot = TelegramUserBot(FakeTelethonClient(), "ask_toby_staging_bot")

        with pytest.raises(TelegramUserBotError, match="start"):
            await bot.send_message("/start")


class TestReplies:
    @pytest.mark.asyncio
    async def test_replies_are_returned_once(self):
        bot, fake = await started()
        await fake.deliver("Записал.", message_id=10)
        await fake.deliver("Резюме", message_id=11)

        updates = await bot.get_updates(timeout=0)

        assert [update.message.text for update in updates] == ["Записал.", "Резюме"]
        assert [update.message.message_id for update in updates] == [10, 11]
        assert await bot.get_updates(timeout=0) == []

    @pytest.mark.asyncio
    async def test_get_updates_waits_for_a_late_reply(self):
        bot, fake = await started()
        waiting = asyncio.create_task(bot.get_updates(timeout=2))
        await asyncio.sleep(0.05)

        await fake.deliver("Резюме")
        updates = await waiting

        assert [update.message.text for update in updates] == ["Резюме"]

    @pytest.mark.asyncio
    async def test_get_updates_gives_up_after_the_timeout(self):
        bot, _ = await started()

        assert await bot.get_updates(timeout=0.05) == []

    @pytest.mark.asyncio
    async def test_reset_drops_unread_replies_and_sent_messages(self):
        bot, fake = await started()
        await bot.send_message("/start")
        await fake.deliver("Привет")

        bot.reset()

        assert bot.sent_messages == []
        assert await bot.get_updates(timeout=0) == []


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_close_disconnects(self):
        bot, fake = await started()

        await bot.close()

        assert fake.disconnected is True

    def test_satisfies_the_bot_protocol(self):
        bot = TelegramUserBot(FakeTelethonClient(), "ask_toby_staging_bot")

        assert isinstance(bot, TelegramBot)
