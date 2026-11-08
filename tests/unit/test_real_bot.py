"""Unit tests for RealTelegramBot."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from testforge.telegram import RealTelegramBot, TelegramAPIError


class TestRealTelegramBot:
    """Test RealTelegramBot."""

    @pytest.fixture
    def bot(self):
        """Create RealTelegramBot instance."""
        return RealTelegramBot(
            token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            chat_id=12345678,
        )

    def test_initialization(self, bot):
        """Bot should initialize with token and chat_id."""
        assert bot.token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        assert bot.chat_id == 12345678
        assert bot.last_update_id == 0
        assert len(bot.sent_messages) == 0

    def test_initialization_without_chat_id(self):
        """Bot can be initialized without default chat_id."""
        bot = RealTelegramBot(token="test-token")
        assert bot.chat_id is None

    def test_api_base_customization(self):
        """Bot should support custom API base URL."""
        bot = RealTelegramBot(
            token="test",
            api_base="https://custom-api.example.com/",
        )
        # Should strip trailing slash
        assert bot.api_base == "https://custom-api.example.com"

    @pytest.mark.asyncio
    async def test_get_me_success(self, bot):
        """get_me should return bot info."""
        mock_response = {
            "ok": True,
            "result": {
                "id": 999999999,
                "is_bot": True,
                "first_name": "TestBot",
                "username": "testbot",
            },
        }

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response["result"])):
            bot_user = await bot.get_me()

            assert bot_user.id == 999999999
            assert bot_user.is_bot is True
            assert bot_user.first_name == "TestBot"
            assert bot_user.username == "testbot"

    @pytest.mark.asyncio
    async def test_get_me_caches_result(self, bot):
        """get_me should cache bot info."""
        mock_response = {
            "id": 999999999,
            "is_bot": True,
            "first_name": "TestBot",
        }

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response)) as mock_api:
            # First call
            await bot.get_me()
            assert mock_api.call_count == 1

            # Second call (should use cache)
            await bot.get_me()
            assert mock_api.call_count == 1  # Not called again

    @pytest.mark.asyncio
    async def test_send_message_success(self, bot):
        """send_message should send text message."""
        mock_response = {
            "message_id": 123,
            "from": {
                "id": 999999999,
                "is_bot": True,
                "first_name": "TestBot",
            },
            "chat": {"id": 12345678},
            "text": "Hello, world!",
        }

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response)):
            message = await bot.send_message("Hello, world!")

            assert message.message_id == 123
            assert message.text == "Hello, world!"
            assert message.chat_id == 12345678
            assert len(bot.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_send_message_with_custom_chat_id(self, bot):
        """send_message should support custom chat_id."""
        mock_response = {
            "message_id": 123,
            "from": {"id": 999, "is_bot": True, "first_name": "Bot"},
            "chat": {"id": 987654321},
            "text": "Test",
        }

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response)) as mock_api:
            await bot.send_message("Test", chat_id=987654321)

            # Should use custom chat_id
            call_args = mock_api.call_args
            assert call_args[1]["params"]["chat_id"] == 987654321

    @pytest.mark.asyncio
    async def test_send_message_without_default_chat_id(self):
        """send_message should fail if no chat_id provided."""
        bot = RealTelegramBot(token="test")  # No default chat_id

        with pytest.raises(ValueError, match="chat_id must be provided"):
            await bot.send_message("Test")

    @pytest.mark.asyncio
    async def test_send_message_with_parse_mode(self, bot):
        """send_message should support parse_mode."""
        mock_response = {
            "message_id": 123,
            "from": {"id": 999, "is_bot": True, "first_name": "Bot"},
            "chat": {"id": 12345678},
            "text": "**Bold**",
        }

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response)) as mock_api:
            await bot.send_message("**Bold**", parse_mode="Markdown")

            call_args = mock_api.call_args
            assert call_args[1]["params"]["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_send_document_success(self, bot, tmp_path):
        """send_document should upload file."""
        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("Fake PDF content")

        mock_response = {
            "message_id": 124,
            "from": {"id": 999, "is_bot": True, "first_name": "Bot"},
            "chat": {"id": 12345678},
            "document": {"file_name": "test.pdf"},
        }

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response)):
            message = await bot.send_document(test_file)

            assert message.message_id == 124
            assert message.document is not None
            assert len(bot.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_send_document_file_not_found(self, bot):
        """send_document should raise if file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            await bot.send_document("nonexistent.pdf")

    @pytest.mark.asyncio
    async def test_send_document_with_caption(self, bot, tmp_path):
        """send_document should support caption."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("Content")

        mock_response = {
            "message_id": 125,
            "from": {"id": 999, "is_bot": True, "first_name": "Bot"},
            "chat": {"id": 12345678},
            "document": {"file_name": "test.pdf"},
            "caption": "Test caption",
        }

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response)) as mock_api:
            await bot.send_document(test_file, caption="Test caption")

            call_args = mock_api.call_args
            assert call_args[1]["params"]["caption"] == "Test caption"

    @pytest.mark.asyncio
    async def test_get_updates_success(self, bot):
        """get_updates should return list of updates."""
        mock_response = [
            {
                "update_id": 1001,
                "message": {
                    "message_id": 200,
                    "from": {"id": 12345, "is_bot": False, "first_name": "User"},
                    "chat": {"id": 12345678},
                    "text": "/start",
                },
            },
            {
                "update_id": 1002,
                "message": {
                    "message_id": 201,
                    "from": {"id": 12345, "is_bot": False, "first_name": "User"},
                    "chat": {"id": 12345678},
                    "text": "Hello",
                },
            },
        ]

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response)):
            updates = await bot.get_updates()

            assert len(updates) == 2
            assert updates[0].update_id == 1001
            assert updates[0].message.text == "/start"
            assert updates[1].update_id == 1002
            assert updates[1].message.text == "Hello"

    @pytest.mark.asyncio
    async def test_get_updates_tracks_last_update_id(self, bot):
        """get_updates should track highest update_id."""
        mock_response = [
            {
                "update_id": 1005,
                "message": {
                    "message_id": 200,
                    "from": {"id": 123, "is_bot": False, "first_name": "User"},
                    "chat": {"id": 12345678},
                    "text": "Test",
                },
            },
        ]

        with patch.object(bot, "_api_request", new=AsyncMock(return_value=mock_response)) as mock_api:
            await bot.get_updates()

            # last_update_id should be updated
            assert bot.last_update_id == 1005

            # Next call should use offset = last_update_id + 1
            await bot.get_updates()
            call_args = mock_api.call_args
            assert call_args[1]["params"]["offset"] == 1006

    @pytest.mark.asyncio
    async def test_get_updates_empty(self, bot):
        """get_updates should handle empty response."""
        with patch.object(bot, "_api_request", new=AsyncMock(return_value=[])):
            updates = await bot.get_updates()
            assert len(updates) == 0

    @pytest.mark.asyncio
    async def test_api_request_error_handling(self, bot):
        """_api_request should raise TelegramAPIError on API error."""
        with patch.object(bot.client, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "ok": False,
                "description": "Bad Request: chat not found",
            }
            mock_post.return_value = mock_response

            with pytest.raises(TelegramAPIError, match="Bad Request"):
                await bot._api_request("sendMessage", params={"chat_id": 123})

    @pytest.mark.asyncio
    async def test_close(self, bot):
        """close() should close HTTP client."""
        with patch.object(bot.client, "aclose", new=AsyncMock()) as mock_close:
            await bot.close()
            mock_close.assert_called_once()

    def test_reset(self, bot):
        """reset() should clear sent messages."""
        bot.sent_messages = ["msg1", "msg2"]
        bot.reset()
        assert len(bot.sent_messages) == 0

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Bot should work as async context manager."""
        async with RealTelegramBot(token="test") as bot:
            assert bot is not None

        # Client should be closed after context
        # (We can't easily test this without accessing internals)
