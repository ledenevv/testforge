"""Scenario executor - runs scenarios against bots."""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from testforge.executor.validators import ValidationError, validate_expect
from testforge.scenarios.models import (
    ActionType,
    ExecutionTrace,
    ExpectCondition,
    Scenario,
    ScenarioResult,
    Step,
    StepTrace,
)
from testforge.telegram.models import TelegramUpdate
from testforge.telegram.protocol import TelegramBot


class ExecutionError(Exception):
    """Raised when scenario execution fails."""

    pass


@dataclass
class _Progress:
    """Mutable run state, shared so a timeout can still report what ran."""

    executed: int = 0
    passed: int = 0
    failed: int = 0
    error: str | None = None
    first_failed_index: int | None = None
    steps: list[StepTrace] = field(default_factory=list)
    captures: dict[str, str] = field(default_factory=dict)
    current: StepTrace | None = None

    def record_failure(self, index: int, message: str) -> None:
        """Remember the first failure only."""
        if self.first_failed_index is None:
            self.first_failed_index = index
            self.error = message


def _reply_texts(updates: list[TelegramUpdate]) -> list[str]:
    return [update.message.text for update in updates if update.message and update.message.text]


class ScenarioExecutor:
    """
    Executes test scenarios against Telegram bots.

    Supports both MockTelegramBot (for fast tests) and RealTelegramBot
    (for E2E validation).
    """

    def __init__(self, bot: TelegramBot, verbose: bool = False):
        """
        Initialize executor.

        Args:
            bot: Bot instance (MockTelegramBot or RealTelegramBot)
            verbose: Enable verbose logging
        """
        self.bot = bot
        self.verbose = verbose
        self.logs: list[str] = []
        self.screenshots: list[str] = []
        self._run_started = 0.0

    def _log(self, message: str) -> None:
        """Log a message."""
        self.logs.append(message)
        if self.verbose:
            print(f"[Executor] {message}")

    def _elapsed(self) -> float:
        """Seconds since the current run started."""
        return time.perf_counter() - self._run_started

    async def run(self, scenario: Scenario) -> ScenarioResult:
        """
        Run a scenario.

        The bot is reset first so state from a previous scenario cannot leak in.
        Each expectation consumes every update received since the previous check.

        A scenario passes only if every step passed; a failed non-critical step
        lets the remaining steps run but still fails the scenario.

        The result carries an ExecutionTrace with one entry per step that started.

        Args:
            scenario: Scenario to execute

        Returns:
            ScenarioResult with execution details
        """
        self.bot.reset()
        self.logs = []
        self.screenshots = []

        self._log(f"Starting scenario: {scenario.id}")
        started_at = datetime.now(timezone.utc)
        self._run_started = time.perf_counter()
        progress = _Progress()

        try:
            await asyncio.wait_for(
                self._run_steps(scenario, progress),
                timeout=scenario.timeout_sec,
            )
        except asyncio.TimeoutError:
            # The step that was in flight never finished: count it as failed
            message = f"Scenario timed out after {scenario.timeout_sec}s"
            progress.failed += 1
            if progress.first_failed_index is None:
                progress.first_failed_index = progress.executed
            progress.error = message
            if progress.current is not None:
                self._finish_step(progress, scenario.steps[progress.current.index], message)
            self._log(f"✗ {message}")

        passed = progress.failed == 0
        duration = self._elapsed()
        self._log(
            f"Scenario finished: {'PASSED' if passed else 'FAILED'} "
            f"({progress.passed}/{progress.executed} steps passed, {duration:.2f}s)"
        )

        trace = ExecutionTrace(
            scenario_id=scenario.id,
            started_at=started_at,
            duration_sec=duration,
            passed=passed,
            error=progress.error,
            steps=progress.steps,
            captures=progress.captures,
        )

        return ScenarioResult(
            scenario_id=scenario.id,
            passed=passed,
            duration_sec=duration,
            steps_executed=progress.executed,
            steps_passed=progress.passed,
            steps_failed=progress.failed,
            error=progress.error,
            failed_step_index=progress.first_failed_index,
            logs=list(self.logs),
            screenshots=list(self.screenshots),
            trace=trace,
        )

    async def _run_steps(self, scenario: Scenario, progress: _Progress) -> None:
        """Execute steps in order, stopping at the first critical failure."""
        for idx, step in enumerate(scenario.steps):
            self._log(f"Step {idx + 1}/{len(scenario.steps)}: {step.action.value}")

            record = StepTrace(index=idx, action=step.action, started_sec=self._elapsed(), passed=False)
            progress.steps.append(record)
            progress.current = record

            error: str | None = None
            try:
                await self._execute_step(step, record)
            except Exception as e:
                # Any step error (including bot/network errors) is a step failure,
                # not a crash that loses the rest of the result.
                error = (
                    str(e)
                    if isinstance(e, (ValidationError, ExecutionError))
                    else f"{type(e).__name__}: {e}"
                )

            self._finish_step(progress, step, error)
            progress.executed += 1

            if error is None:
                progress.passed += 1
                self._log(f"  ✓ Step {idx + 1} passed")
                continue

            progress.failed += 1
            progress.record_failure(idx, error)
            if step.critical:
                self._log(f"  ✗ Step {idx + 1} FAILED (critical): {error}")
                return
            self._log(f"  ⚠ Step {idx + 1} FAILED (non-critical): {error}")

    def _finish_step(self, progress: _Progress, step: Step, error: str | None) -> None:
        """Close the step in flight: record its outcome, duration and captured replies."""
        record = progress.current
        record.duration_sec = self._elapsed() - record.started_sec
        record.passed = error is None
        record.error = error
        if step.capture:
            progress.captures[step.capture] = "\n".join(record.replies)
        progress.current = None

    async def _execute_step(self, step: Step, record: StepTrace) -> None:
        """
        Execute a single step.

        Args:
            step: Step to execute
            record: Trace entry for this step, filled in while it runs

        Raises:
            ExecutionError: If step execution fails
            ValidationError: If expect condition not met
        """
        if step.action == ActionType.SEND_MESSAGE:
            await self._handle_send_message(step, record)

        elif step.action == ActionType.SEND_DOCUMENT:
            await self._handle_send_document(step, record)

        elif step.action == ActionType.WAIT:
            await self._handle_wait(step)

        elif step.action == ActionType.EXPECT_RESPONSE:
            await self._handle_expect_response(step, record)

        elif step.action == ActionType.VERIFY_STATE:
            await self._handle_verify_state(step)

        else:
            raise ExecutionError(f"Unknown action type: {step.action}")

    async def _handle_send_message(self, step: Step, record: StepTrace) -> None:
        """
        Handle send_message action.

        Sends a text message to the bot and optionally validates response.
        """
        if not step.text:
            raise ExecutionError("send_message requires 'text' field")

        self._log(f"  → Sending message: {step.text}")
        record.sent = step.text

        await self.bot.send_message(step.text)

        if step.expect:
            await self._check_replies(step.expect, record)

    async def _handle_send_document(self, step: Step, record: StepTrace) -> None:
        """
        Handle send_document action.

        Uploads a document to the bot and optionally validates response.
        """
        if not step.document_path:
            raise ExecutionError("send_document requires 'document_path' field")

        doc_path = Path(step.document_path)
        self._log(f"  → Sending document: {doc_path.name}")
        record.sent = doc_path.name

        await self.bot.send_document(doc_path, caption=step.caption)

        if step.expect:
            await self._check_replies(step.expect, record)

    async def _handle_wait(self, step: Step) -> None:
        """
        Handle wait action.

        Waits for a specified duration.
        """
        if not step.duration_sec or step.duration_sec <= 0:
            raise ExecutionError("wait requires 'duration_sec' > 0")

        self._log(f"  ⏳ Waiting {step.duration_sec}s...")
        await asyncio.sleep(step.duration_sec)

    async def _handle_expect_response(self, step: Step, record: StepTrace) -> None:
        """
        Handle expect_response action.

        Waits for bot responses and validates them.
        """
        if not step.expect:
            raise ExecutionError("expect_response requires 'expect' field")

        await self._check_replies(step.expect, record)

    async def _check_replies(self, expect: ExpectCondition, record: StepTrace) -> None:
        """Wait for the bot, keep every reply on the trace, then validate them."""
        if expect.delay_sec:
            await asyncio.sleep(expect.delay_sec)

        updates = await self.bot.get_updates()
        record.replies.extend(_reply_texts(updates))

        self._log(f"  ← Received {len(updates)} response(s)")
        validate_expect(expect, updates)

    async def _handle_verify_state(self, step: Step) -> None:
        """
        Handle verify_state action.

        Verifies bot internal state (for testing purposes).
        """
        # Failing loudly: a stub that reported success would turn any scenario
        # using verify_state into a false pass.
        raise ExecutionError("verify_state is not implemented yet")
