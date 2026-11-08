"""Scenario executor - runs scenarios against bots."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from testforge.executor.validators import ValidationError, validate_expect
from testforge.scenarios.models import ActionType, Scenario, ScenarioResult, Step
from testforge.telegram.protocol import TelegramBot


class ExecutionError(Exception):
    """Raised when scenario execution fails."""

    pass


@dataclass
class _Progress:
    """Mutable step counters, shared so a timeout can still report what ran."""

    executed: int = 0
    passed: int = 0
    failed: int = 0
    error: str | None = None
    first_failed_index: int | None = None

    def record_failure(self, index: int, message: str) -> None:
        """Remember the first failure only."""
        if self.first_failed_index is None:
            self.first_failed_index = index
            self.error = message


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

    def _log(self, message: str) -> None:
        """Log a message."""
        self.logs.append(message)
        if self.verbose:
            print(f"[Executor] {message}")

    async def run(self, scenario: Scenario) -> ScenarioResult:
        """
        Run a scenario.

        The bot is reset first so state from a previous scenario cannot leak in.
        Each expectation consumes every update received since the previous check.

        A scenario passes only if every step passed; a failed non-critical step
        lets the remaining steps run but still fails the scenario.

        Args:
            scenario: Scenario to execute

        Returns:
            ScenarioResult with execution details
        """
        self.bot.reset()
        self.logs = []
        self.screenshots = []

        self._log(f"Starting scenario: {scenario.id}")
        start_time = time.perf_counter()
        progress = _Progress()

        try:
            await asyncio.wait_for(
                self._run_steps(scenario, progress),
                timeout=scenario.timeout_sec,
            )
        except asyncio.TimeoutError:
            # The step that was in flight never finished: count it as failed
            progress.failed += 1
            message = f"Scenario timed out after {scenario.timeout_sec}s"
            if progress.first_failed_index is None:
                progress.first_failed_index = progress.executed
            progress.error = message
            self._log(f"✗ {message}")

        passed = progress.failed == 0
        duration = time.perf_counter() - start_time
        self._log(
            f"Scenario finished: {'PASSED' if passed else 'FAILED'} "
            f"({progress.passed}/{progress.executed} steps passed, {duration:.2f}s)"
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
        )

    async def _run_steps(self, scenario: Scenario, progress: _Progress) -> None:
        """Execute steps in order, stopping at the first critical failure."""
        for idx, step in enumerate(scenario.steps):
            self._log(f"Step {idx + 1}/{len(scenario.steps)}: {step.action.value}")

            try:
                await self._execute_step(step, scenario)
            except Exception as e:
                # Any step error (including bot/network errors) is a step failure,
                # not a crash that loses the rest of the result.
                detail = (
                    str(e)
                    if isinstance(e, (ValidationError, ExecutionError))
                    else f"{type(e).__name__}: {e}"
                )
                progress.executed += 1
                progress.failed += 1
                progress.record_failure(idx, detail)

                if step.critical:
                    self._log(f"  ✗ Step {idx + 1} FAILED (critical): {detail}")
                    return
                self._log(f"  ⚠ Step {idx + 1} FAILED (non-critical): {detail}")
            else:
                progress.executed += 1
                progress.passed += 1
                self._log(f"  ✓ Step {idx + 1} passed")

    async def _execute_step(self, step: Step, scenario: Scenario) -> None:
        """
        Execute a single step.

        Args:
            step: Step to execute
            scenario: Parent scenario (for context)

        Raises:
            ExecutionError: If step execution fails
            ValidationError: If expect condition not met
        """
        # Execute action based on type
        if step.action == ActionType.SEND_MESSAGE:
            await self._handle_send_message(step)

        elif step.action == ActionType.SEND_DOCUMENT:
            await self._handle_send_document(step)

        elif step.action == ActionType.WAIT:
            await self._handle_wait(step)

        elif step.action == ActionType.EXPECT_RESPONSE:
            await self._handle_expect_response(step)

        elif step.action == ActionType.VERIFY_STATE:
            await self._handle_verify_state(step)

        else:
            raise ExecutionError(f"Unknown action type: {step.action}")

    async def _handle_send_message(self, step: Step) -> None:
        """
        Handle send_message action.

        Sends a text message to the bot and optionally validates response.
        """
        if not step.text:
            raise ExecutionError("send_message requires 'text' field")

        self._log(f"  → Sending message: {step.text}")

        # Send message to bot
        await self.bot.send_message(step.text)

        # Check expectations if specified
        if step.expect:
            # Wait for delay if specified
            if step.expect.delay_sec:
                await asyncio.sleep(step.expect.delay_sec)

            # Get bot responses
            updates = await self.bot.get_updates()

            self._log(f"  ← Received {len(updates)} response(s)")

            # Validate responses
            validate_expect(step.expect, updates)

    async def _handle_send_document(self, step: Step) -> None:
        """
        Handle send_document action.

        Uploads a document to the bot and optionally validates response.
        """
        if not step.document_path:
            raise ExecutionError("send_document requires 'document_path' field")

        doc_path = Path(step.document_path)
        self._log(f"  → Sending document: {doc_path.name}")

        # Send document to bot
        await self.bot.send_document(doc_path, caption=step.caption)

        # Check expectations if specified
        if step.expect:
            # Wait for delay if specified
            if step.expect.delay_sec:
                await asyncio.sleep(step.expect.delay_sec)

            # Get bot responses
            updates = await self.bot.get_updates()

            self._log(f"  ← Received {len(updates)} response(s)")

            # Validate responses
            validate_expect(step.expect, updates)

    async def _handle_wait(self, step: Step) -> None:
        """
        Handle wait action.

        Waits for a specified duration.
        """
        if not step.duration_sec or step.duration_sec <= 0:
            raise ExecutionError("wait requires 'duration_sec' > 0")

        self._log(f"  ⏳ Waiting {step.duration_sec}s...")
        await asyncio.sleep(step.duration_sec)

    async def _handle_expect_response(self, step: Step) -> None:
        """
        Handle expect_response action.

        Waits for bot responses and validates them.
        """
        if not step.expect:
            raise ExecutionError("expect_response requires 'expect' field")

        # Wait for delay if specified
        if step.expect.delay_sec:
            await asyncio.sleep(step.expect.delay_sec)

        # Get bot responses
        updates = await self.bot.get_updates()

        self._log(f"  ← Checking {len(updates)} response(s)")

        # Validate responses
        validate_expect(step.expect, updates)

    async def _handle_verify_state(self, step: Step) -> None:
        """
        Handle verify_state action.

        Verifies bot internal state (for testing purposes).
        """
        # Failing loudly: a stub that reported success would turn any scenario
        # using verify_state into a false pass.
        raise ExecutionError("verify_state is not implemented yet")
