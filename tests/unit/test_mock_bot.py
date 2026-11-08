"""Unit tests for MockTelegramBot."""

from pathlib import Path

import pytest

from testforge.telegram import MockTelegramBot, TelegramMessage


class TestMockTelegramBot:
    """Test MockTelegramBot."""

    @pytest.fixture
    def bot(self):
        """Create mock bot instance."""
        return MockTelegramBot(
            responses_dir="fixtures/mock_responses",
            bot_user_id=999999999,
            test_user_id=12345678,
        )

    @pytest.mark.asyncio
    async def test_send_start_command(self, bot):
        """Sending /start should return welcome message."""
        await bot.send_message("/start")
        updates = await bot.get_updates()

        assert len(updates) == 1
        assert updates[0].message is not None
        assert "Этот бот анализирует медицинские документы" in updates[0].message.text

    @pytest.mark.asyncio
    async def test_send_consent_command(self, bot):
        """Sending /consent should return profile prompt."""
        await bot.send_message("/consent")
        updates = await bot.get_updates()

        assert len(updates) == 1
        assert updates[0].message is not None
        assert "профиль" in updates[0].message.text.lower()
        assert "пол" in updates[0].message.text.lower()
        assert bot.state == "profile_sex"

    @pytest.mark.asyncio
    async def test_send_help_command(self, bot):
        """Sending /help should return help text."""
        await bot.send_message("/help")
        updates = await bot.get_updates()

        assert len(updates) == 1
        assert updates[0].message is not None
        assert "Справка" in updates[0].message.text or "помощ" in updates[0].message.text.lower()

    @pytest.mark.asyncio
    async def test_send_unknown_command(self, bot):
        """Unknown command should return default response."""
        await bot.send_message("/unknown_command")
        updates = await bot.get_updates()

        assert len(updates) == 1
        assert updates[0].message is not None
        # Should get some response (default fallback)
        assert len(updates[0].message.text) > 0

    @pytest.mark.asyncio
    async def test_send_document(self, bot, tmp_path):
        """Sending document should return confirmation and interpretation."""
        # Create a fake PDF file
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("fake pdf content")

        await bot.send_document(pdf_file)
        updates = await bot.get_updates()

        # Confirmation followed by interpretation
        assert len(updates) == 2
        assert "Документ получен" in updates[0].message.text or "Анализирую" in updates[0].message.text
        assert "Резюме" in updates[1].message.text

    @pytest.mark.asyncio
    async def test_profile_flow(self, bot):
        """Profile setup flow should work sequentially."""
        # Start profile flow: /consent itself must enter the flow
        await bot.send_message("/consent")
        updates = await bot.get_updates()
        assert "пол" in updates[0].message.text.lower()

        # Send sex
        await bot.send_message("m")
        updates = await bot.get_updates()
        assert "год" in updates[0].message.text.lower()

        # Send birth year
        await bot.send_message("1985")
        updates = await bot.get_updates()
        assert "рост" in updates[0].message.text.lower()

        # Send height
        await bot.send_message("180")
        updates = await bot.get_updates()
        assert "вес" in updates[0].message.text.lower()

        # Send weight
        await bot.send_message("75")
        updates = await bot.get_updates()
        assert "заболевания" in updates[0].message.text.lower() or "хронические" in updates[0].message.text.lower()

        # Send conditions
        await bot.send_message("нет")
        updates = await bot.get_updates()
        assert "сохранён" in updates[0].message.text.lower() or "Профиль" in updates[0].message.text

        # State should be back to idle
        assert bot.state == "idle"

    @pytest.mark.asyncio
    async def test_message_ids_increment(self, bot):
        """Message IDs should increment."""
        msg1 = await bot.send_message("test1")
        msg2 = await bot.send_message("test2")

        assert msg2.message_id > msg1.message_id

    @pytest.mark.asyncio
    async def test_bot_user_is_bot(self, bot):
        """Bot user should have is_bot=True."""
        await bot.send_message("/start")
        updates = await bot.get_updates()

        bot_message = updates[0].message
        assert bot_message.from_user.is_bot is True

    @pytest.mark.asyncio
    async def test_test_user_is_not_bot(self, bot):
        """Test user should have is_bot=False."""
        msg = await bot.send_message("/start")
        assert msg.from_user.is_bot is False

    @pytest.mark.asyncio
    async def test_get_updates_empties_queue(self, bot):
        """get_updates should empty pending responses."""
        await bot.send_message("/start")

        # First call should return updates
        updates1 = await bot.get_updates()
        assert len(updates1) > 0

        # Second call should return empty (queue consumed)
        updates2 = await bot.get_updates()
        assert len(updates2) == 0

    def test_reset_clears_state(self, bot):
        """reset() should clear all state."""
        # Send some messages
        bot.message_counter = 10
        bot.state = "some_state"
        bot.profile_data = {"test": "data"}

        bot.reset()

        assert bot.message_counter == 0
        assert bot.state == "idle"
        assert bot.profile_data == {}
        assert len(bot.sent_messages) == 0
        assert len(bot.pending_responses) == 0

    @pytest.mark.asyncio
    async def test_responses_have_delay(self, bot):
        """Responses should have simulated delay."""
        import time

        start = time.time()
        await bot.send_message("/start")
        await bot.get_updates()
        duration = time.time() - start

        # Should have at least some delay (default 0.5s for /start)
        assert duration >= 0.3  # Allow for some timing variance

    def test_load_nonexistent_responses_uses_defaults(self):
        """If responses dir doesn't exist, should use defaults."""
        bot = MockTelegramBot(responses_dir="nonexistent_dir")
        assert len(bot.responses) > 0
        assert "start" in bot.responses or "default" in bot.responses

    @pytest.mark.asyncio
    async def test_multiple_messages_before_get_updates(self, bot):
        """Should queue multiple responses."""
        await bot.send_message("/start")
        await bot.send_message("/help")

        updates = await bot.get_updates()

        # Should get responses to both messages
        assert len(updates) >= 2

    @pytest.mark.asyncio
    async def test_sent_messages_tracked(self, bot):
        """Sent messages should be tracked."""
        assert len(bot.sent_messages) == 0

        await bot.send_message("test1")
        assert len(bot.sent_messages) == 1

        await bot.send_message("test2")
        assert len(bot.sent_messages) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("state", "next_state"),
        [
            ("profile_birth_year", "profile_height"),
            ("profile_height", "profile_weight"),
            ("profile_weight", "profile_conditions"),
        ],
    )
    async def test_profile_non_numeric_input_reprompts(self, bot, state, next_state):
        """Non-numeric input in a numeric profile step re-asks instead of crashing."""
        bot.state = state

        await bot.send_message("не число")
        updates = await bot.get_updates()

        assert bot.state == state
        assert len(updates) == 1
        assert "число" in updates[0].message.text.lower()

        # A valid answer afterwards still advances the flow
        await bot.send_message("1985" if state == "profile_birth_year" else "75")
        await bot.get_updates()
        assert bot.state == next_state

    @pytest.mark.asyncio
    async def test_malformed_template_does_not_crash(self, tmp_path):
        """A broken Jinja2 template in a fixture falls back to the raw text."""
        import json

        (tmp_path / "broken.json").write_text(
            json.dumps(
                {
                    "trigger": {"command": "/broken"},
                    "response": {"text": "Hello {{ unclosed", "delay_sec": 0},
                }
            ),
            encoding="utf-8",
        )
        bot = MockTelegramBot(responses_dir=tmp_path)

        await bot.send_message("/broken")
        updates = await bot.get_updates()

        assert updates[0].message.text == "Hello {{ unclosed"

    @pytest.mark.asyncio
    async def test_send_document_missing_file(self, bot, tmp_path):
        """A nonexistent file still produces a document message with a default size."""
        message = await bot.send_document(tmp_path / "does_not_exist.pdf")

        assert message.document["file_name"] == "does_not_exist.pdf"
        assert message.document["file_size"] == 1024

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Mock supports the same async context manager as the real bot."""
        async with MockTelegramBot() as bot:
            await bot.send_message("/start")

    def test_satisfies_telegram_bot_protocol(self, bot):
        """MockTelegramBot conforms to the shared TelegramBot interface."""
        from testforge.telegram import TelegramBot

        assert isinstance(bot, TelegramBot)
