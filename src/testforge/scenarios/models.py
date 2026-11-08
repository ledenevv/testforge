"""Scenario data models."""

import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Priority = Literal["P0", "P1", "P2"]


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


class ValidationSpec(BaseModel):
    """
    Checks applied to a scenario's results after the run.

    Unknown keys are rejected, so a misspelled check is never silently skipped.
    """

    model_config = ConfigDict(extra="forbid")

    expectations: str | None = Field(
        default=None,
        description="Path to the expectations YAML for this scenario's documents",
    )
    llm_judge: bool = Field(
        default=False,
        description="Score the bot's interpretation with the LLM judge",
    )
    compliance: bool = Field(
        default=False,
        description="Check the disclaimer and forbidden phrases",
    )
    cost_budget_usd: float | None = Field(
        default=None,
        gt=0,
        description="Budget for TestForge's own LLM spend in this scenario (judge calls)",
    )
    performance_budget_sec: float | None = Field(
        default=None,
        gt=0,
        description="Target for the total duration of the scenario",
    )


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

    # Keep the bot's replies from this step as the interpretation text
    capture: Literal["interpretation"] | None = Field(
        default=None,
        description="Store the bot replies this step received under this name",
    )

    @model_validator(mode="after")
    def capture_needs_bot_replies(self) -> "Step":
        if self.capture is None:
            return self
        reads_replies = self.action == ActionType.EXPECT_RESPONSE or (
            self.action in (ActionType.SEND_MESSAGE, ActionType.SEND_DOCUMENT)
            and self.expect is not None
        )
        if not reads_replies:
            raise ValueError(
                "capture needs a step that reads bot replies: expect_response, "
                "or send_message/send_document with 'expect'"
            )
        return self


class Scenario(BaseModel):
    """Test scenario definition."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9_]+$",
        description="Unique scenario identifier (lowercase, underscores)",
    )
    title: str | None = Field(
        default=None,
        min_length=1,
        description="Short human-readable title, shown in reports",
    )
    description: str = Field(
        min_length=1,
        description="Human-readable scenario description",
    )
    priority: Priority = Field(
        default="P1",
        description="Importance: P0 is the most important, P2 the least",
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

    # Checks run on the results after the scenario
    validation: ValidationSpec = Field(
        default_factory=ValidationSpec,
        description="Checks applied to the results after the run",
    )


class StepTrace(BaseModel):
    """What happened in one step of a run."""

    index: int = Field(ge=0, description="Position of the step in the scenario (0-based)")
    action: ActionType = Field(description="Action performed")
    started_sec: float = Field(ge=0, description="Seconds since the run started")
    duration_sec: float = Field(default=0.0, ge=0, description="How long the step took")
    sent: str | None = Field(
        default=None,
        description="Message text sent, or file name for a document",
    )
    replies: list[str] = Field(
        default_factory=list,
        description="Text of every bot reply the step received",
    )
    passed: bool = Field(default=False, description="Whether the step passed")
    error: str | None = Field(default=None, description="Why the step failed")


class ExecutionTrace(BaseModel):
    """
    Step-by-step record of one scenario run, saved as trace.json.

    One entry per step that started. If the scenario timed out, the last entry
    is the step that was still running when time ran out.
    """

    scenario_id: str = Field(description="Scenario that was executed")
    started_at: datetime = Field(description="Wall-clock start of the run (UTC)")
    duration_sec: float = Field(ge=0, description="Total run duration")
    passed: bool = Field(description="Whether the scenario passed")
    error: str | None = Field(default=None, description="Scenario-level error, if any")
    steps: list[StepTrace] = Field(default_factory=list, description="Steps in order")
    captures: dict[str, str] = Field(
        default_factory=dict,
        description="Replies kept under a capture name, e.g. 'interpretation'",
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

    # Step-by-step record of the run
    trace: ExecutionTrace | None = Field(
        default=None,
        description="Step-by-step record of the run",
    )
