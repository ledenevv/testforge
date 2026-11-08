"""Unit tests for ScenarioVerifier."""

import pytest

from testforge.scenarios.models import ScenarioResult
from testforge.verifier import AssertionError, ScenarioVerifier


class MockBot:
    """Mock bot for testing."""

    def __init__(self):
        self.state = "idle"
        self.profile_data = {}
        self.sent_messages = []
        self.pending_responses = []


class TestScenarioVerifier:
    """Test ScenarioVerifier."""

    @pytest.fixture
    def verifier(self):
        """Create verifier instance."""
        return ScenarioVerifier(strict=True)

    @pytest.fixture
    def passed_result(self):
        """Create a passed scenario result."""
        return ScenarioResult(
            scenario_id="test",
            passed=True,
            duration_sec=1.5,
            steps_executed=3,
            steps_passed=3,
            steps_failed=0,
            logs=["Starting scenario: test", "Step 1 passed", "Scenario finished"],
        )

    @pytest.fixture
    def failed_result(self):
        """Create a failed scenario result."""
        return ScenarioResult(
            scenario_id="test",
            passed=False,
            duration_sec=0.5,
            steps_executed=2,
            steps_passed=1,
            steps_failed=1,
            error="Step validation failed",
            failed_step_index=1,
            logs=["Starting scenario: test", "Step 1 passed", "Step 2 FAILED"],
        )

    def test_verify_result_passed_success(self, verifier, passed_result):
        """Verify passed result should not raise."""
        verifier.verify_result_passed(passed_result)  # Should not raise

    def test_verify_result_passed_failure(self, verifier, failed_result):
        """Verify failed result should raise."""
        with pytest.raises(AssertionError, match="failed"):
            verifier.verify_result_passed(failed_result)

    def test_verify_all_steps_passed_success(self, verifier, passed_result):
        """Verify all steps passed should not raise."""
        verifier.verify_all_steps_passed(passed_result)  # Should not raise

    def test_verify_all_steps_passed_failure(self, verifier, failed_result):
        """Verify with failed steps should raise."""
        with pytest.raises(AssertionError, match="failed"):
            verifier.verify_all_steps_passed(failed_result)

    def test_verify_step_count_success(self, verifier, passed_result):
        """Verify correct step counts should not raise."""
        verifier.verify_step_count(
            passed_result,
            expected_executed=3,
            expected_passed=3,
        )

    def test_verify_step_count_executed_mismatch(self, verifier, passed_result):
        """Verify wrong executed count should raise."""
        with pytest.raises(AssertionError, match="executed"):
            verifier.verify_step_count(passed_result, expected_executed=5)

    def test_verify_step_count_passed_mismatch(self, verifier, passed_result):
        """Verify wrong passed count should raise."""
        with pytest.raises(AssertionError, match="passed"):
            verifier.verify_step_count(passed_result, expected_passed=2)

    def test_verify_duration_within_success(self, verifier, passed_result):
        """Verify duration within bounds should not raise."""
        verifier.verify_duration_within(
            passed_result,
            min_sec=1.0,
            max_sec=2.0,
        )

    def test_verify_duration_too_short(self, verifier, passed_result):
        """Verify duration below minimum should raise."""
        with pytest.raises(AssertionError, match="duration"):
            verifier.verify_duration_within(passed_result, min_sec=5.0)

    def test_verify_duration_too_long(self, verifier, passed_result):
        """Verify duration above maximum should raise."""
        with pytest.raises(AssertionError, match="duration"):
            verifier.verify_duration_within(passed_result, max_sec=1.0)

    def test_verify_bot_state_success(self, verifier):
        """Verify correct bot state should not raise."""
        bot = MockBot()
        bot.state = "idle"

        verifier.verify_bot_state(bot, expected_state="idle")

    def test_verify_bot_state_mismatch(self, verifier):
        """Verify wrong bot state should raise."""
        bot = MockBot()
        bot.state = "active"

        with pytest.raises(AssertionError, match="state"):
            verifier.verify_bot_state(bot, expected_state="idle")

    def test_verify_message_count_success(self, verifier):
        """Verify correct message count should not raise."""
        bot = MockBot()
        bot.sent_messages = ["msg1", "msg2", "msg3"]

        verifier.verify_message_count(bot, expected_sent=3)

    def test_verify_message_count_mismatch(self, verifier):
        """Verify wrong message count should raise."""
        bot = MockBot()
        bot.sent_messages = ["msg1", "msg2"]

        with pytest.raises(AssertionError, match="sent messages"):
            verifier.verify_message_count(bot, expected_sent=5)

    def test_verify_profile_complete_success(self, verifier):
        """Verify complete profile should not raise."""
        bot = MockBot()
        bot.profile_data = {
            "sex": "m",
            "birth_year": 1990,
            "height_cm": 180,
            "weight_kg": 75,
        }

        verifier.verify_profile_complete(bot)

    def test_verify_profile_complete_missing_field(self, verifier):
        """Verify incomplete profile should raise."""
        bot = MockBot()
        bot.profile_data = {
            "sex": "m",
            "birth_year": 1990,
            # Missing height_cm and weight_kg
        }

        with pytest.raises(AssertionError, match="missing required field"):
            verifier.verify_profile_complete(bot)

    def test_verify_profile_matches_success(self, verifier):
        """Verify matching profile should not raise."""
        bot = MockBot()
        bot.profile_data = {
            "sex": "f",
            "birth_year": 1985,
            "height_cm": 165,
        }

        verifier.verify_profile_matches(
            bot,
            expected={"sex": "f", "birth_year": 1985},
        )

    def test_verify_profile_matches_mismatch(self, verifier):
        """Verify mismatched profile should raise."""
        bot = MockBot()
        bot.profile_data = {"sex": "m", "birth_year": 1990}

        with pytest.raises(AssertionError, match="expected f"):
            verifier.verify_profile_matches(bot, expected={"sex": "f"})

    def test_verify_logs_contain_success(self, verifier, passed_result):
        """Verify logs contain text should not raise."""
        verifier.verify_logs_contain(passed_result, "Starting scenario")

    def test_verify_logs_contain_failure(self, verifier, passed_result):
        """Verify logs missing text should raise."""
        with pytest.raises(AssertionError, match="not found"):
            verifier.verify_logs_contain(passed_result, "MISSING_TEXT")

    def test_verify_logs_not_contain_success(self, verifier, passed_result):
        """Verify logs don't contain text should not raise."""
        verifier.verify_logs_not_contain(passed_result, "ERROR")

    def test_verify_logs_not_contain_failure(self, verifier, passed_result):
        """Verify logs contain unwanted text should raise."""
        with pytest.raises(AssertionError, match="found in logs"):
            verifier.verify_logs_not_contain(passed_result, "Starting")

    def test_collect_artifacts(self, verifier, passed_result):
        """Collect artifacts should return dict with all data."""
        artifacts = verifier.collect_artifacts(passed_result)

        assert artifacts["scenario_id"] == "test"
        assert artifacts["passed"] is True
        assert artifacts["duration_sec"] == 1.5
        assert artifacts["steps"]["executed"] == 3
        assert artifacts["steps"]["passed"] == 3
        assert artifacts["steps"]["failed"] == 0
        assert len(artifacts["logs"]) == 3

    def test_strict_mode_raises_on_failure(self):
        """Strict mode should raise on assertion failure."""
        verifier = ScenarioVerifier(strict=True)
        result = ScenarioResult(
            scenario_id="test",
            passed=False,
            duration_sec=1.0,
            steps_executed=1,
            steps_passed=0,
            steps_failed=1,
            error="Test error",
        )

        with pytest.raises(AssertionError):
            verifier.verify_result_passed(result)

    def test_non_strict_mode_logs_warning(self):
        """Non-strict mode should log warning instead of raising."""
        verifier = ScenarioVerifier(strict=False)
        result = ScenarioResult(
            scenario_id="test",
            passed=False,
            duration_sec=1.0,
            steps_executed=1,
            steps_passed=0,
            steps_failed=1,
            error="Test error",
        )

        # Should not raise
        verifier.verify_result_passed(result)

        # Should have warning
        assert len(verifier.warnings) > 0
        assert "failed" in verifier.warnings[0]

    def test_reset_warnings(self):
        """Reset warnings should clear warning list."""
        verifier = ScenarioVerifier(strict=False)
        result = ScenarioResult(
            scenario_id="test",
            passed=False,
            duration_sec=1.0,
            steps_executed=1,
            steps_passed=0,
            steps_failed=1,
            error="Test",
        )

        verifier.verify_result_passed(result)
        assert len(verifier.warnings) > 0

        verifier.reset_warnings()
        assert len(verifier.warnings) == 0

    def test_verify_no_errors_logged_success(self, verifier):
        """Verify no errors in clean logs should not raise."""
        result = ScenarioResult(
            scenario_id="test",
            passed=True,
            duration_sec=1.0,
            steps_executed=1,
            steps_passed=1,
            steps_failed=0,
            logs=["Starting scenario", "Step 1 passed", "Finished"],
        )

        verifier.verify_no_errors_logged(result)

    def test_verify_no_errors_logged_failure(self, verifier):
        """Verify errors in logs should raise."""
        result = ScenarioResult(
            scenario_id="test",
            passed=False,
            duration_sec=1.0,
            steps_executed=1,
            steps_passed=0,
            steps_failed=1,
            logs=["Starting scenario", "Step 1 error: validation failed"],
        )

        with pytest.raises(AssertionError, match="error keyword"):
            verifier.verify_no_errors_logged(result)

    def test_verify_conversation_flow_success(self, verifier):
        """Verify conversation flow with keywords in order should not raise."""
        from testforge.telegram.models import TelegramMessage, TelegramUser

        bot = MockBot()
        user = TelegramUser(id=123, first_name="Test")

        bot.sent_messages = [
            TelegramMessage(
                message_id=1,
                **{"from": user},
                chat_id=123,
                text="/start",
            ),
            TelegramMessage(
                message_id=2,
                **{"from": user},
                chat_id=123,
                text="/consent",
            ),
            TelegramMessage(
                message_id=3,
                **{"from": user},
                chat_id=123,
                text="m",
            ),
        ]

        verifier.verify_conversation_flow(bot, ["/start", "/consent", "m"])

    def test_verify_conversation_flow_out_of_order(self, verifier):
        """Verify conversation flow with keywords out of order should raise."""
        from testforge.telegram.models import TelegramMessage, TelegramUser

        bot = MockBot()
        user = TelegramUser(id=123, first_name="Test")

        bot.sent_messages = [
            TelegramMessage(
                message_id=1,
                **{"from": user},
                chat_id=123,
                text="/start",
            ),
            TelegramMessage(
                message_id=2,
                **{"from": user},
                chat_id=123,
                text="m",
            ),
        ]

        with pytest.raises(AssertionError, match="not found"):
            # Expecting "/consent" which doesn't appear
            verifier.verify_conversation_flow(bot, ["/start", "/consent"])
