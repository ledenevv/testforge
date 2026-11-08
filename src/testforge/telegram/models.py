"""Telegram data models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TelegramUser(BaseModel):
    """Telegram user."""

    id: int = Field(description="Telegram user ID")
    is_bot: bool = Field(default=False, description="Is bot user")
    first_name: str = Field(default="Test", description="First name")
    last_name: str | None = Field(default=None, description="Last name")
    username: str | None = Field(default=None, description="Username")


class TelegramMessage(BaseModel):
    """Telegram message."""

    message_id: int = Field(description="Message ID")
    from_user: TelegramUser = Field(alias="from", description="Message sender")
    chat_id: int = Field(description="Chat ID")
    date: datetime = Field(default_factory=datetime.now, description="Message date")
    text: str | None = Field(default=None, description="Message text")
    document: dict[str, Any] | None = Field(default=None, description="Document attachment")
    photo: list[dict[str, Any]] | None = Field(default=None, description="Photo attachments")

    model_config = ConfigDict(populate_by_name=True)


class TelegramUpdate(BaseModel):
    """Telegram update (from getUpdates)."""

    update_id: int = Field(description="Update ID")
    message: TelegramMessage | None = Field(default=None, description="New message")


class ProfileData(BaseModel):
    """User profile data (ask-toby specific)."""

    sex: Literal["m", "f", "other"] = Field(description="Sex")
    birth_year: int = Field(ge=1900, le=2100, description="Birth year")
    height_cm: int = Field(gt=0, le=300, description="Height in cm")
    weight_kg: float = Field(gt=0, le=500, description="Weight in kg")
    chronic_conditions: str = Field(default="", description="Chronic conditions")
    medications: str = Field(default="", description="Current medications")
