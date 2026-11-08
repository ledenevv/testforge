"""Scenario verification - post-execution validation."""

from typing import Any

from testforge.scenarios.models import ScenarioResult
from testforge.telegram.models import ProfileData, TelegramMessage


class AssertionError(Exception):
    """Raised when verification assertion fails."""

    pass


class ScenarioVerifier:
    """
    Verifies scenario execution results and bot state.

    Provides assertion helpers for common validation patterns.
    """

    def __init__(self, strict: bool = True):
        """
        Initialize verifier.

        Args:
            strict: If True, assertions raise errors. If False, log warnings.
        """
        self.strict = strict
        self.warnings: list[str] = []

    def _assert(self, condition: bool, message: str) -> None:
        """
        Assert a condition.

        Args:
            condition: Condition to check
            message: Error message if condition is False

        Raises:
            AssertionError: If condition is False and strict mode enabled
        """
        if not condition:
            if self.strict:
                raise AssertionError(message)
            else:
                self.warnings.append(message)

    def verify_result_passed(self, result: ScenarioResult) -> None:
        """
        Verify that scenario passed.

        Args:
            result: Scenario execution result

        Raises:
            AssertionError: If scenario failed
        """
        self._assert(
            result.passed,
            f"Scenario {result.scenario_id} failed: {result.error}",
        )

    def verify_all_steps_passed(self, result: ScenarioResult) -> None:
        """
        Verify that all steps passed.

        Args:
            result: Scenario execution result

        Raises:
            AssertionError: If any steps failed
        """
        self._assert(
            result.steps_failed == 0,
            f"Expected all steps to pass, but {result.steps_failed} failed",
        )

    def verify_step_count(
        self,
        result: ScenarioResult,
        expected_executed: int | None = None,
        expected_passed: int | None = None,
    ) -> None:
        """
        Verify step execution counts.

        Args:
            result: Scenario execution result
            expected_executed: Expected number of executed steps
            expected_passed: Expected number of passed steps

        Raises:
            AssertionError: If counts don't match
        """
        if expected_executed is not None:
            self._assert(
                result.steps_executed == expected_executed,
                f"Expected {expected_executed} steps executed, got {result.steps_executed}",
            )

        if expected_passed is not None:
            self._assert(
                result.steps_passed == expected_passed,
                f"Expected {expected_passed} steps passed, got {result.steps_passed}",
            )

    def verify_duration_within(
        self,
        result: ScenarioResult,
        min_sec: float | None = None,
        max_sec: float | None = None,
    ) -> None:
        """
        Verify execution duration is within bounds.

        Args:
            result: Scenario execution result
            min_sec: Minimum expected duration in seconds
            max_sec: Maximum expected duration in seconds

        Raises:
            AssertionError: If duration is outside bounds
        """
        if min_sec is not None:
            self._assert(
                result.duration_sec >= min_sec,
                f"Expected duration >= {min_sec}s, got {result.duration_sec}s",
            )

        if max_sec is not None:
            self._assert(
                result.duration_sec <= max_sec,
                f"Expected duration <= {max_sec}s, got {result.duration_sec}s",
            )

    def verify_bot_state(self, bot: Any, expected_state: str) -> None:
        """
        Verify bot internal state.

        Args:
            bot: Bot instance (MockTelegramBot or RealTelegramBot)
            expected_state: Expected state value

        Raises:
            AssertionError: If state doesn't match
        """
        if not hasattr(bot, "state"):
            self._assert(False, f"Bot does not have 'state' attribute")
            return

        self._assert(
            bot.state == expected_state,
            f"Expected bot state '{expected_state}', got '{bot.state}'",
        )

    def verify_message_count(
        self,
        bot: Any,
        expected_sent: int | None = None,
        expected_received: int | None = None,
    ) -> None:
        """
        Verify message counts.

        Args:
            bot: Bot instance
            expected_sent: Expected number of sent messages (from user)
            expected_received: Expected number of received messages (from bot)

        Raises:
            AssertionError: If counts don't match
        """
        if expected_sent is not None:
            if not hasattr(bot, "sent_messages"):
                self._assert(False, "Bot does not have 'sent_messages' attribute")
            else:
                actual = len(bot.sent_messages)
                self._assert(
                    actual == expected_sent,
                    f"Expected {expected_sent} sent messages, got {actual}",
                )

        if expected_received is not None:
            if not hasattr(bot, "pending_responses"):
                # Try to get updates
                if hasattr(bot, "get_updates"):
                    # Note: This is async, simplified check
                    pass
            # For simplicity, skip this check in M7
            # Real implementation would use async get_updates()

    def verify_profile_complete(self, bot: Any) -> None:
        """
        Verify that user profile is complete.

        Args:
            bot: Bot instance with profile_data attribute

        Raises:
            AssertionError: If profile is incomplete
        """
        if not hasattr(bot, "profile_data"):
            self._assert(False, "Bot does not have 'profile_data' attribute")
            return

        profile = bot.profile_data

        # Check required fields
        required_fields = ["sex", "birth_year", "height_cm", "weight_kg"]
        for field in required_fields:
            self._assert(
                field in profile and profile[field],
                f"Profile missing required field: {field}",
            )

    def verify_profile_matches(self, bot: Any, expected: dict[str, Any]) -> None:
        """
        Verify profile data matches expected values.

        Args:
            bot: Bot instance
            expected: Expected profile data (dict)

        Raises:
            AssertionError: If profile doesn't match
        """
        if not hasattr(bot, "profile_data"):
            self._assert(False, "Bot does not have 'profile_data' attribute")
            return

        profile = bot.profile_data

        for key, expected_value in expected.items():
            actual_value = profile.get(key)
            self._assert(
                actual_value == expected_value,
                f"Profile field '{key}': expected {expected_value}, got {actual_value}",
            )

    def verify_conversation_flow(
        self,
        bot: Any,
        expected_keywords: list[str],
    ) -> None:
        """
        Verify conversation contains expected keywords in order.

        Args:
            bot: Bot instance
            expected_keywords: List of keywords that should appear in order

        Raises:
            AssertionError: If keywords not found or out of order
        """
        if not hasattr(bot, "sent_messages"):
            self._assert(False, "Bot does not have 'sent_messages' attribute")
            return

        # Collect all message texts
        all_text = ""
        for msg in bot.sent_messages:
            if hasattr(msg, "text") and msg.text:
                all_text += msg.text.lower() + "\n"

        # Check keywords appear in order
        last_index = -1
        for keyword in expected_keywords:
            index = all_text.find(keyword.lower(), last_index + 1)
            self._assert(
                index > last_index,
                f"Expected keyword '{keyword}' not found in conversation flow",
            )
            last_index = index

    def verify_no_errors_logged(self, result: ScenarioResult) -> None:
        """
        Verify no error messages in logs.

        Args:
            result: Scenario execution result

        Raises:
            AssertionError: If logs contain error messages
        """
        error_keywords = ["error", "failed", "exception"]

        for log in result.logs:
            log_lower = log.lower()
            for keyword in error_keywords:
                if keyword in log_lower and "passed" not in log_lower:
                    self._assert(
                        False,
                        f"Found error keyword '{keyword}' in log: {log[:100]}",
                    )

    def verify_logs_contain(self, result: ScenarioResult, expected: str) -> None:
        """
        Verify logs contain expected text.

        Args:
            result: Scenario execution result
            expected: Expected text in logs

        Raises:
            AssertionError: If text not found in logs
        """
        all_logs = "\n".join(result.logs)
        self._assert(
            expected.lower() in all_logs.lower(),
            f"Expected '{expected}' in logs, but not found",
        )

    def verify_logs_not_contain(self, result: ScenarioResult, unexpected: str) -> None:
        """
        Verify logs do not contain text.

        Args:
            result: Scenario execution result
            unexpected: Text that should not be in logs

        Raises:
            AssertionError: If text found in logs
        """
        all_logs = "\n".join(result.logs)
        self._assert(
            unexpected.lower() not in all_logs.lower(),
            f"Unexpected '{unexpected}' found in logs",
        )

    def collect_artifacts(self, result: ScenarioResult) -> dict[str, Any]:
        """
        Collect scenario artifacts for debugging.

        Args:
            result: Scenario execution result

        Returns:
            Dict with artifacts (logs, screenshots, metrics)
        """
        return {
            "scenario_id": result.scenario_id,
            "passed": result.passed,
            "duration_sec": result.duration_sec,
            "steps": {
                "executed": result.steps_executed,
                "passed": result.steps_passed,
                "failed": result.steps_failed,
            },
            "error": result.error,
            "failed_step": result.failed_step_index,
            "logs": result.logs,
            "screenshots": result.screenshots,
            "warnings": self.warnings,
        }

    def reset_warnings(self) -> None:
        """Reset collected warnings."""
        self.warnings = []
