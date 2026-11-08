"""Scenario executor - runs scenarios against bots."""

import asyncio
import time
from pathlib import Path
from typing import Any

from testforge.executor.validators import ValidationError, validate_expect
from testforge.scenarios.models import ActionType, Scenario, ScenarioResult, Step
from testforge.telegram.models import TelegramUpdate


class ExecutionError(Exception):
    """Raised when scenario execution fails."""

    pass


class ScenarioExecutor:
    """
    Executes test scenarios against Telegram bots.

    Supports both MockTelegramBot (for fast tests) and RealTelegramBot
    (for E2E validation).
    """

    def __init__(self, bot: Any, verbose: bool = False):
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

        Args:
            scenario: Scenario to execute

        Returns:
            ScenarioResult with execution details
        """
        # Reset state
        self.logs = []
        self.screenshots = []

        self._log(f"Starting scenario: {scenario.id}")
        start_time = time.perf_counter()

        steps_executed = 0
        steps_passed = 0
        steps_failed = 0
        error: str | None = None
        failed_step_index: int | None = None

        try:
            # Execute each step
            for idx, step in enumerate(scenario.steps):
                self._log(f"Step {idx + 1}/{len(scenario.steps)}: {step.action.value}")

                try:
                    await self._execute_step(step, scenario)
                    steps_executed += 1
                    steps_passed += 1
                    self._log(f"  ✓ Step {idx + 1} passed")

                except (ValidationError, ExecutionError) as e:
                    steps_executed += 1
                    steps_failed += 1

                    if step.critical:
                        # Critical step failed - stop scenario
                        error = str(e)
                        failed_step_index = idx
                        self._log(f"  ✗ Step {idx + 1} FAILED (critical): {e}")
                        break
                    else:
                        # Non-critical step - log and continue
                        self._log(f"  ⚠ Step {idx + 1} FAILED (non-critical): {e}")

            # Check if scenario passed
            passed = steps_failed == 0 and error is None

            duration = time.perf_counter() - start_time

            result = ScenarioResult(
                scenario_id=scenario.id,
                passed=passed,
                duration_sec=duration,
                steps_executed=steps_executed,
                steps_passed=steps_passed,
                steps_failed=steps_failed,
                error=error,
                failed_step_index=failed_step_index,
                logs=self.logs,
                screenshots=self.screenshots,
            )

            self._log(
                f"Scenario finished: {'PASSED' if passed else 'FAILED'} "
                f"({steps_passed}/{steps_executed} steps passed, {duration:.2f}s)"
            )

            return result

        except asyncio.TimeoutError:
            duration = time.perf_counter() - start_time
            error = f"Scenario timed out after {scenario.timeout_sec}s"
            self._log(f"✗ {error}")

            return ScenarioResult(
                scenario_id=scenario.id,
                passed=False,
                duration_sec=duration,
                steps_executed=steps_executed,
                steps_passed=steps_passed,
                steps_failed=steps_failed + 1,
                error=error,
                failed_step_index=steps_executed,
                logs=self.logs,
                screenshots=self.screenshots,
            )

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
        # This is a placeholder for M6
        # In real implementation, would check bot.state, bot.profile_data, etc.
        self._log("  ✓ State verification (not implemented in M6)")
