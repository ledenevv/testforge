"""Scenario data models."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Action types for scenario steps."""

    SEND_MESSAGE = "send_message"
    SEND_DOCUMENT = "send_document"
    WAIT = "wait"
    VERIFY_STATE = "verify_state"
    EXPECT_RESPONSE = "expect_response"


class ExpectCondition(BaseModel):
    """Expected condition for verification."""

    contains: str | None = Field(
        default=None,
        description="Response must contain this text (case-insensitive)",
    )
    not_contains: str | None = Field(
        default=None,
        description="Response must NOT contain this text",
    )
    matches_regex: str | None = Field(
        default=None,
        description="Response must match this regex pattern",
    )
    response_count: int | None = Field(
        default=None,
        ge=0,
        description="Expected number of bot responses",
    )
    delay_sec: float | None = Field(
        default=None,
        ge=0,
        description="Wait this many seconds before checking",
    )


class Step(BaseModel):
    """Single step in a test scenario."""

    action: ActionType = Field(description="Action to perform")
    description: str | None = Field(
        default=None,
        description="Human-readable step description",
    )

    # Action-specific parameters
    text: str | None = Field(default=None, description="Message text (for send_message)")
    document_path: str | None = Field(
        default=None,
        description="Path to document file (for send_document)",
    )
    caption: str | None = Field(
        default=None,
        description="Document caption (for send_document)",
    )
    duration_sec: float | None = Field(
        default=None,
        ge=0,
        description="Wait duration (for wait action)",
    )

    # Verification
    expect: ExpectCondition | None = Field(
        default=None,
        description="Expected outcome for this step",
    )

    # Metadata
    critical: bool = Field(
        default=True,
        description="If True, failure stops scenario. If False, logs warning and continues.",
    )


class Scenario(BaseModel):
    """Test scenario definition."""

    id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9_]+$",
        description="Unique scenario identifier (lowercase, underscores)",
    )
    description: str = Field(
        min_length=1,
        description="Human-readable scenario description",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization (e.g., 'smoke', 'regression', 'profile')",
    )
    mode: Literal["mock", "real"] = Field(
        default="mock",
        description="Bot mode: 'mock' for MockTelegramBot, 'real' for RealTelegramBot",
    )

    # Scenario steps
    steps: list[Step] = Field(
        min_length=1,
        description="Ordered list of steps to execute",
    )

    # Test metadata
    timeout_sec: float = Field(
        default=60.0,
        ge=1,
        description="Maximum scenario execution time",
    )
    retry_on_failure: bool = Field(
        default=False,
        description="Retry scenario if it fails",
    )
    max_retries: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Maximum retry attempts (if retry_on_failure=True)",
    )

    # Variables for templating
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Variables for Jinja2 template rendering",
    )


class ScenarioResult(BaseModel):
    """Result of scenario execution."""

    scenario_id: str = Field(description="Scenario that was executed")
    passed: bool = Field(description="Whether scenario passed")
    duration_sec: float = Field(ge=0, description="Execution duration")

    # Step results
    steps_executed: int = Field(ge=0, description="Number of steps executed")
    steps_passed: int = Field(ge=0, description="Number of steps that passed")
    steps_failed: int = Field(ge=0, description="Number of steps that failed")

    # Errors
    error: str | None = Field(default=None, description="Error message if failed")
    failed_step_index: int | None = Field(
        default=None,
        description="Index of first failed step (0-based)",
    )

    # Artifacts
    screenshots: list[str] = Field(
        default_factory=list,
        description="Paths to screenshots taken during execution",
    )
    logs: list[str] = Field(
        default_factory=list,
        description="Log messages from execution",
    )
