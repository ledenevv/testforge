"""Real Telegram bot client using Telegram Bot API."""

import asyncio
from pathlib import Path
from typing import Any

import httpx

from testforge.telegram.models import TelegramMessage, TelegramUpdate, TelegramUser

# Telegram rejects sendMessage text longer than this
MAX_MESSAGE_LENGTH = 4096


class TelegramAPIError(Exception):
    """Raised when Telegram API returns an error."""

    pass


class RealTelegramBot:
    """
    Real Telegram bot client using Bot API.

    Sends messages and documents to actual Telegram bot,
    polls for updates from real users.
    """

    def __init__(
        self,
        token: str,
        chat_id: int | None = None,
        api_base: str = "https://api.telegram.org",
        timeout_sec: int = 30,
    ):
        """
        Initialize real bot client.

        Args:
            token: Telegram bot token (from @BotFather)
            chat_id: Default chat ID for messages (optional, can be set per-message)
            api_base: Telegram API base URL
            timeout_sec: HTTP request timeout
        """
        self.token = token
        self.chat_id = chat_id
        self.api_base = api_base.rstrip("/")
        self.timeout_sec = timeout_sec

        # HTTP client
        self.client = httpx.AsyncClient(timeout=timeout_sec)

        # Track updates
        self.last_update_id = 0
        self.sent_messages: list[TelegramMessage] = []

        # Bot info (cached)
        self._bot_user: TelegramUser | None = None

    async def _api_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make Telegram API request.

        Args:
            method: API method name (e.g., 'sendMessage')
            params: Query parameters
            files: Files to upload

        Returns:
            API response result

        Raises:
            TelegramAPIError: If API returns error
        """
        url = f"{self.api_base}/bot{self.token}/{method}"

        try:
            if files:
                # Multipart upload
                response = await self.client.post(url, data=params, files=files)
            else:
                # JSON request
                response = await self.client.post(url, json=params)

            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as e:
                raise TelegramAPIError(f"Invalid JSON in response to {method}: {e}") from e

            if not isinstance(data, dict):
                raise TelegramAPIError(f"Unexpected response shape for {method}")

            if not data.get("ok"):
                error_description = data.get("description", "Unknown error")
                raise TelegramAPIError(f"Telegram API error: {error_description}")

            return data.get("result", {})

        except httpx.HTTPStatusError as e:
            raise TelegramAPIError(f"HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise TelegramAPIError(f"Request failed: {e}") from e

    async def get_me(self) -> TelegramUser:
        """
        Get bot info.

        Returns:
            Bot user object

        Raises:
            TelegramAPIError: If API call fails
        """
        if self._bot_user:
            return self._bot_user

        result = await self._api_request("getMe")

        if "id" not in result:
            raise TelegramAPIError("getMe response missing 'id' field")

        self._bot_user = TelegramUser(
            id=result["id"],
            is_bot=result.get("is_bot", True),
            first_name=result.get("first_name", "Bot"),
            username=result.get("username"),
        )

        return self._bot_user

    async def send_message(
        self,
        text: str,
        chat_id: int | None = None,
        parse_mode: str | None = None,
    ) -> TelegramMessage:
        """
        Send text message.

        Args:
            text: Message text
            chat_id: Chat ID (uses default if not provided)
            parse_mode: Parse mode (Markdown, HTML, etc.)

        Returns:
            Sent message object

        Raises:
            TelegramAPIError: If send fails
            ValueError: If chat_id not provided and no default, or text too long
        """
        target_chat_id = chat_id or self.chat_id
        if not target_chat_id:
            raise ValueError("chat_id must be provided or set as default")

        if len(text) > MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"Message too long: {len(text)} chars (max {MAX_MESSAGE_LENGTH})"
            )

        params = {
            "chat_id": target_chat_id,
            "text": text,
        }

        if parse_mode:
            params["parse_mode"] = parse_mode

        result = await self._api_request("sendMessage", params=params)

        # Parse response into TelegramMessage
        message = self._parse_message(result)
        self.sent_messages.append(message)

        return message

    async def send_document(
        self,
        file_path: str | Path,
        caption: str | None = None,
        chat_id: int | None = None,
    ) -> TelegramMessage:
        """
        Send document file.

        Args:
            file_path: Path to document file
            caption: Optional caption
            chat_id: Chat ID (uses default if not provided)

        Returns:
            Sent message object

        Raises:
            TelegramAPIError: If send fails
            ValueError: If chat_id not provided and no default
            FileNotFoundError: If file doesn't exist
        """
        target_chat_id = chat_id or self.chat_id
        if not target_chat_id:
            raise ValueError("chat_id must be provided or set as default")

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Document file not found: {file_path}")

        params = {
            "chat_id": target_chat_id,
        }

        if caption:
            params["caption"] = caption

        # Open file and upload
        with open(file_path, "rb") as f:
            files = {
                "document": (file_path.name, f, "application/octet-stream"),
            }

            result = await self._api_request("sendDocument", params=params, files=files)

        message = self._parse_message(result)
        self.sent_messages.append(message)

        return message

    async def get_updates(
        self,
        timeout: int = 10,
        limit: int = 100,
    ) -> list[TelegramUpdate]:
        """
        Get updates (long polling).

        Args:
            timeout: Long polling timeout in seconds
            limit: Maximum number of updates to retrieve

        Returns:
            List of updates

        Raises:
            TelegramAPIError: If API call fails
        """
        params = {
            "offset": self.last_update_id + 1,
            "timeout": timeout,
            "limit": limit,
        }

        result = await self._api_request("getUpdates", params=params)

        updates = []
        for update_data in result:
            update = self._parse_update(update_data)
            updates.append(update)

            # Track highest update ID
            if update.update_id > self.last_update_id:
                self.last_update_id = update.update_id

        return updates

    def _parse_message(self, data: dict[str, Any]) -> TelegramMessage:
        """
        Parse Telegram message from API response.

        Args:
            data: Message data from API

        Returns:
            TelegramMessage object
        """
        try:
            from_user_data = data.get("from", {})
            from_user = TelegramUser(
                id=from_user_data["id"],
                is_bot=from_user_data.get("is_bot", False),
                first_name=from_user_data.get("first_name", "User"),
                last_name=from_user_data.get("last_name"),
                username=from_user_data.get("username"),
            )

            return TelegramMessage(
                message_id=data["message_id"],
                **{"from": from_user},
                chat_id=data["chat"]["id"],
                text=data.get("text"),
                document=data.get("document"),
                photo=data.get("photo"),
            )
        except KeyError as e:
            raise TelegramAPIError(f"Malformed message from Telegram: missing {e}") from e

    def _parse_update(self, data: dict[str, Any]) -> TelegramUpdate:
        """
        Parse Telegram update from API response.

        Args:
            data: Update data from API

        Returns:
            TelegramUpdate object
        """
        if "update_id" not in data:
            raise TelegramAPIError("Malformed update from Telegram: missing 'update_id'")

        message = None
        if "message" in data:
            message = self._parse_message(data["message"])

        return TelegramUpdate(
            update_id=data["update_id"],
            message=message,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    def reset(self) -> None:
        """Reset bot state (clear sent messages, update offset)."""
        self.sent_messages = []
        # Note: We don't reset last_update_id to avoid reprocessing old updates

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args):
        """Async context manager exit."""
        await self.close()
