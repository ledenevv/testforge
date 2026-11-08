"""Mock Telegram bot for testing without real Bot API."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from jinja2 import Template, TemplateError

from testforge.telegram.models import (
    ProfileData,
    TelegramMessage,
    TelegramUpdate,
    TelegramUser,
)


class MockTelegramBot:
    """
    Mock Telegram bot that simulates ask-toby bot behavior.

    Uses canned responses from JSON files to simulate bot interactions
    without making real Telegram API calls.
    """

    def __init__(
        self,
        responses_dir: str | Path = "fixtures/mock_responses",
        bot_user_id: int = 999999999,
        test_user_id: int = 12345678,
    ):
        """
        Initialize mock bot.

        Args:
            responses_dir: Directory containing response JSON files
            bot_user_id: Fake bot user ID
            test_user_id: Fake test user ID
        """
        self.responses_dir = Path(responses_dir)
        self.bot_user_id = bot_user_id
        self.test_user_id = test_user_id

        # Mock state
        self.message_counter = 0
        self.update_counter = 0
        self.sent_messages: list[TelegramMessage] = []
        self.pending_responses: list[TelegramMessage] = []

        # FSM state (for profile setup flow)
        self.state: str = "idle"
        self.profile_data: dict[str, Any] = {}

        # Load responses
        self.responses = self._load_responses()

    def _load_responses(self) -> dict[str, Any]:
        """Load canned responses from JSON files."""
        responses = {}

        if not self.responses_dir.exists():
            # Return default responses if directory doesn't exist
            return self._default_responses()

        for json_file in self.responses_dir.glob("*.json"):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                    key = json_file.stem  # filename without extension
                    responses[key] = data
            except Exception:
                # Skip invalid files
                continue

        # Fallback to defaults if nothing loaded
        return responses if responses else self._default_responses()

    def _default_responses(self) -> dict[str, Any]:
        """Default canned responses."""
        return {
            "start": {
                "trigger": {"command": "/start"},
                "response": {
                    "text": "👋 Привет! Этот бот анализирует медицинские документы.\n\nПеред началом работы прочитайте, пожалуйста, информацию о том, что я делаю и как храню данные.\n\n/consent — Согласиться и продолжить",
                    "delay_sec": 0.5,
                },
            },
            "consent": {
                "trigger": {"command": "/consent"},
                "response": {
                    "text": "Спасибо! Теперь заполним профиль.\n\nУкажите ваш пол (m/f/other):",
                    "delay_sec": 0.3,
                },
            },
            "profile_saved": {
                "trigger": {"state": "profile_complete"},
                "response": {
                    "text": "✅ Профиль сохранён!\n\nТеперь вы можете загружать документы или задавать вопросы.\n\n/menu — Главное меню",
                    "delay_sec": 0.5,
                },
            },
            "document_received": {
                "trigger": {"type": "document"},
                "response": {
                    "text": "📄 Документ получен. Анализирую...\n\n⏳ Это займёт около 30-60 секунд.",
                    "delay_sec": 1.0,
                },
            },
            "interpretation": {
                "trigger": {"after": "document_received"},
                "response": {
                    "text": "📊 **Резюме**\n\nВаши анализы в целом в пределах нормы.\n\n**Ключевые моменты:**\n- АЛТ: 25 Ед/л (норма)\n- АСТ: 22 Ед/л (норма)\n- Холестерин: 5.2 ммоль/л (норма)\n- Глюкоза: 5.0 ммоль/л (норма)\n\n**В норме:**\nВсе показатели биохимии находятся в референсных диапазонах.\n\n**Что обсудить с врачом:**\nРезультаты в норме, но регулярный мониторинг полезен.\n\n⚠️ Это информационный разбор. Не заменяет консультацию врача.",
                    "delay_sec": 2.0,
                },
            },
            "default": {
                "trigger": {"fallback": True},
                "response": {
                    "text": "Извините, я не понял команду. Используйте /help для справки.",
                    "delay_sec": 0.3,
                },
            },
        }

    def _next_message_id(self) -> int:
        """Generate next message ID."""
        self.message_counter += 1
        return self.message_counter

    def _next_update_id(self) -> int:
        """Generate next update ID."""
        self.update_counter += 1
        return self.update_counter

    def _create_bot_user(self) -> TelegramUser:
        """Create bot user object."""
        return TelegramUser(
            id=self.bot_user_id,
            is_bot=True,
            first_name="ask-toby (mock)",
            username="asktoby_mock_bot",
        )

    def _create_test_user(self) -> TelegramUser:
        """Create test user object."""
        return TelegramUser(
            id=self.test_user_id,
            is_bot=False,
            first_name="Test",
            last_name="User",
            username="test_user",
        )

    def _match_response(self, message_text: str) -> dict[str, Any]:
        """Find matching response for message text."""
        # Try exact command match
        if message_text.startswith("/"):
            command = message_text.split()[0].lower()
            for key, resp_data in self.responses.items():
                trigger = resp_data.get("trigger", {})
                if trigger.get("command") == command:
                    return resp_data

        # Try partial text match
        message_lower = message_text.lower()
        for key, resp_data in self.responses.items():
            trigger = resp_data.get("trigger", {})
            if "text" in trigger and trigger["text"].lower() in message_lower:
                return resp_data

        # Fallback to default (always return something)
        default = self.responses.get("default")
        if default:
            return default
        
        # Ultimate fallback if no default defined
        return {
            "response": {
                "text": "Извините, я не понял команду. Используйте /help для справки.",
                "delay_sec": 0.3,
            }
        }

    async def send_message(self, text: str) -> TelegramMessage:
        """
        Send a message to the bot (from test user).

        Args:
            text: Message text

        Returns:
            Sent message object
        """
        # Create sent message
        message = TelegramMessage(
            message_id=self._next_message_id(),
            **{"from": self._create_test_user()},
            chat_id=self.test_user_id,
            text=text,
        )
        self.sent_messages.append(message)

        # Process message and queue response
        await self._process_message(message)

        return message

    async def send_document(
        self,
        file_path: str | Path,
        caption: str | None = None,
    ) -> TelegramMessage:
        """
        Send a document to the bot.

        Args:
            file_path: Path to document file
            caption: Optional caption

        Returns:
            Sent message object
        """
        file_path = Path(file_path)

        try:
            file_size = file_path.stat().st_size
        except OSError:
            # Missing or unreadable file: the mock doesn't need real content
            file_size = 1024

        # Create document message
        message = TelegramMessage(
            message_id=self._next_message_id(),
            **{"from": self._create_test_user()},
            chat_id=self.test_user_id,
            text=caption,
            document={
                "file_name": file_path.name,
                "mime_type": "application/pdf",
                "file_size": file_size,
            },
        )
        self.sent_messages.append(message)

        # Queue document received response
        await self._process_document(message)

        return message

    async def _process_message(self, message: TelegramMessage) -> None:
        """Process incoming message and queue bot response."""
        if not message.text:
            return

        # Special handling for profile flow
        if self.state.startswith("profile_"):
            await self._handle_profile_flow(message.text)
            return

        # Handle /consent command (triggers profile flow)
        if message.text.lower() == "/consent":
            self.state = "profile_sex"

        # Find matching response (always returns something)
        response_data = self._match_response(message.text)
        await self._queue_response(response_data)

    async def _process_document(self, message: TelegramMessage) -> None:
        """Process document upload and queue responses."""
        # Queue "document received" response
        doc_response = self.responses.get("document_received")
        if doc_response:
            await self._queue_response(doc_response)

        # Queue interpretation (simulated delay)
        interpretation = self.responses.get("interpretation")
        if interpretation:
            # Simulate processing delay
            await asyncio.sleep(0.5)
            await self._queue_response(interpretation)

    async def _handle_profile_flow(self, text: str) -> None:
        """Handle profile setup flow (FSM)."""
        if self.state == "profile_sex":
            self.profile_data["sex"] = text
            self.state = "profile_birth_year"
            await self._queue_text_response("Укажите год рождения:")

        elif self.state == "profile_birth_year":
            value = self._parse_number(text, int)
            if value is None:
                await self._queue_text_response("Пожалуйста, введите число. Укажите год рождения:")
                return
            self.profile_data["birth_year"] = value
            self.state = "profile_height"
            await self._queue_text_response("Укажите рост (см):")

        elif self.state == "profile_height":
            value = self._parse_number(text, int)
            if value is None:
                await self._queue_text_response("Пожалуйста, введите число. Укажите рост (см):")
                return
            self.profile_data["height_cm"] = value
            self.state = "profile_weight"
            await self._queue_text_response("Укажите вес (кг):")

        elif self.state == "profile_weight":
            value = self._parse_number(text, float)
            if value is None:
                await self._queue_text_response("Пожалуйста, введите число. Укажите вес (кг):")
                return
            self.profile_data["weight_kg"] = value
            self.state = "profile_conditions"
            await self._queue_text_response(
                "Есть ли хронические заболевания? (или 'нет')"
            )

        elif self.state == "profile_conditions":
            self.profile_data["chronic_conditions"] = text
            # Queue profile saved response
            saved_response = self.responses.get("profile_saved")
            if saved_response:
                await self._queue_response(saved_response)
            else:
                # Fallback if no saved response template
                await self._queue_text_response("✅ Профиль сохранён!")
            self.state = "idle"

    @staticmethod
    def _parse_number(text: str, kind: type[int] | type[float]) -> int | float | None:
        """Parse numeric profile input; None if it isn't a valid number."""
        try:
            return kind(text.strip())
        except ValueError:
            return None

    async def _queue_response(self, response_data: dict[str, Any]) -> None:
        """Queue a bot response."""
        response = response_data.get("response", {})
        text = response.get("text", "")
        delay = response.get("delay_sec", 0.3)

        # Simulate network delay
        await asyncio.sleep(delay)

        # Render template if needed
        if "{{" in text:
            try:
                text = Template(text).render(profile=self.profile_data)
            except TemplateError:
                # Malformed template in a fixture: send the raw text rather than crash
                pass

        # Create bot message
        bot_message = TelegramMessage(
            message_id=self._next_message_id(),
            **{"from": self._create_bot_user()},
            chat_id=self.test_user_id,
            text=text,
        )
        self.pending_responses.append(bot_message)

    async def _queue_text_response(self, text: str) -> None:
        """Queue a simple text response."""
        await asyncio.sleep(0.3)
        bot_message = TelegramMessage(
            message_id=self._next_message_id(),
            **{"from": self._create_bot_user()},
            chat_id=self.test_user_id,
            text=text,
        )
        self.pending_responses.append(bot_message)

    async def get_updates(self, timeout: int = 10) -> list[TelegramUpdate]:
        """
        Get pending updates (bot responses).

        Args:
            timeout: Max time to wait for updates (not used in mock)

        Returns:
            List of updates
        """
        updates = []
        while self.pending_responses:
            message = self.pending_responses.pop(0)
            update = TelegramUpdate(
                update_id=self._next_update_id(),
                message=message,
            )
            updates.append(update)

        return updates

    def reset(self) -> None:
        """Reset bot state (for tests)."""
        self.message_counter = 0
        self.update_counter = 0
        self.sent_messages = []
        self.pending_responses = []
        self.state = "idle"
        self.profile_data = {}

    async def close(self) -> None:
        """No-op; present so the mock is interchangeable with RealTelegramBot."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
