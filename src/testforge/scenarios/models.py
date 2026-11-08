"""Scenario data models."""

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActionType(str, Enum):
    """Action types for scenario steps."""

    SEND_MESSAGE = "send_message"
    SEND_DOCUMENT = "send_document"
    WAIT = "wait"
    VERIFY_STATE = "verify_state"
    EXPECT_RESPONSE = "expect_response"


class ExpectCondition(BaseModel):
    """
    Expected condition for verification.

    Conditions are checked against every bot update received since the previous
    check (each check consumes them), concatenated into one text.
    """

    # Unknown keys are rejected: a typo such as `expects:` would otherwise
    # silently turn a step into one with no checks at all.
    model_config = ConfigDict(extra="forbid")

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

    @field_validator("matches_regex")
    @classmethod
    def regex_must_compile(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex {v!r}: {e}") from e
        return v


class Step(BaseModel):
    """Single step in a test scenario."""

    model_config = ConfigDict(extra="forbid")

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
        description=(
            "If True, failure stops the scenario. If False, the remaining steps "
            "still run, but the scenario is still reported as failed."
        ),
    )


class Scenario(BaseModel):
    """Test scenario definition."""

    model_config = ConfigDict(extra="forbid")

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
        description=(
            "Bot mode: 'mock' for MockTelegramBot, 'real' for RealTelegramBot. "
            "Informational: the executor runs against whichever bot it is given."
        ),
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
        description="Reserved: not yet applied by the executor",
    )
    max_retries: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Reserved: not yet applied by the executor",
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
