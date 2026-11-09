"""Integration tests for ScenarioVerifier with Executor."""

from pathlib import Path

import pytest

from testforge.executor import ScenarioExecutor
from testforge.scenarios import load_scenario
from testforge.telegram import MockTelegramBot
from testforge.verifier import ScenarioVerifier, VerificationError


class TestVerifierIntegration:
    """Test ScenarioVerifier with real scenario execution."""

    @pytest.fixture
    def bot(self):
        """Create MockTelegramBot instance."""
        bot = MockTelegramBot(responses_dir="fixtures/mock_responses")
        return bot

    @pytest.fixture
    def executor(self, bot):
        """Create ScenarioExecutor instance."""
        return ScenarioExecutor(bot=bot, verbose=False)

    @pytest.fixture
    def verifier(self):
        """Create ScenarioVerifier instance."""
        return ScenarioVerifier(strict=True)

    @pytest.fixture
    def scenarios_dir(self):
        """Path to fixture scenarios."""
        return Path("tests/fixtures/scenarios")

    @pytest.mark.asyncio
    async def test_verify_smoke_test_scenario(
        self, executor, verifier, scenarios_dir
    ):
        """Run and verify smoke_test scenario."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        # Verify with ScenarioVerifier
        verifier.verify_result_passed(result)
        verifier.verify_all_steps_passed(result)
        verifier.verify_step_count(result, expected_executed=3, expected_passed=3)
        verifier.verify_logs_contain(result, "Starting scenario")

    @pytest.mark.asyncio
    async def test_verify_profile_setup_scenario(
        self, executor, verifier, scenarios_dir, bot
    ):
        """Run and verify profile_setup scenario with bot state."""
        scenario = load_scenario(scenarios_dir / "profile_setup.yaml")
        result = await executor.run(scenario)

        # Verify result
        verifier.verify_result_passed(result)
        verifier.verify_step_count(result, expected_executed=6)

        # Verify bot state after scenario
        verifier.verify_bot_state(bot, expected_state="idle")

        # Verify profile was completed
        verifier.verify_profile_complete(bot)

        # Verify specific profile values
        verifier.verify_profile_matches(
            bot,
            expected={
                "sex": "m",
                "birth_year": 1985,
                "height_cm": 180,
                "weight_kg": 75,
            },
        )

    @pytest.mark.asyncio
    async def test_verify_message_counts(
        self, executor, verifier, scenarios_dir, bot
    ):
        """Verify message counts after scenario execution."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        # 3 messages sent by user (/start, /help, /unknown_command_xyz)
        verifier.verify_message_count(bot, expected_sent=3)

    @pytest.mark.asyncio
    async def test_verify_duration_bounds(
        self, executor, verifier, scenarios_dir
    ):
        """Verify scenario execution duration is reasonable."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        # Should take at least some time (network delays simulated)
        verifier.verify_duration_within(result, min_sec=0.5)

        # But not too long (timeout = 15s, should finish much faster)
        verifier.verify_duration_within(result, max_sec=10.0)

    @pytest.mark.asyncio
    async def test_verify_conversation_flow(
        self, executor, verifier, scenarios_dir, bot
    ):
        """Verify conversation follows expected flow."""
        scenario = load_scenario(scenarios_dir / "profile_setup.yaml")
        result = await executor.run(scenario)

        # Verify keywords appear in order
        verifier.verify_conversation_flow(
            bot,
            expected_keywords=["/consent", "m", "1985", "180", "75", "нет"],
        )

    @pytest.mark.asyncio
    async def test_collect_artifacts_for_debugging(
        self, executor, verifier, scenarios_dir
    ):
        """Collect artifacts for failed scenario debugging."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        # Collect artifacts
        artifacts = verifier.collect_artifacts(result)

        # Verify artifact structure
        assert artifacts["scenario_id"] == "smoke_test"
        assert artifacts["passed"] is True
        assert "steps" in artifacts
        assert "logs" in artifacts
        assert len(artifacts["logs"]) > 0

    @pytest.mark.asyncio
    async def test_verify_no_errors_in_successful_scenario(
        self, executor, verifier, scenarios_dir
    ):
        """Verify no error keywords in logs for successful scenario."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        assert result.passed is True
        verifier.verify_no_errors_logged(result)

    @pytest.mark.asyncio
    async def test_verify_no_errors_detects_failed_scenario(
        self, executor, verifier
    ):
        """A failed scenario's logs must be flagged, including its summary line."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="failing",
            description="Fails its only step",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(contains="WILL_FAIL"),
                )
            ],
        )
        result = await executor.run(scenario)

        assert result.passed is False
        with pytest.raises(VerificationError, match="FAILED|failed"):
            verifier.verify_no_errors_logged(result)

    @pytest.mark.asyncio
    async def test_verify_logs_structure(
        self, executor, verifier, scenarios_dir
    ):
        """Verify logs contain expected structure."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        # Check log structure - logs should exist
        assert len(result.logs) > 0
       
        # Check for starting log
        verifier.verify_logs_contain(result, "Starting scenario")
        
        # Check for step logs
        verifier.verify_logs_contain(result, "Step")

    @pytest.mark.asyncio
    async def test_non_strict_mode_continues_on_failure(
        self, executor, scenarios_dir
    ):
        """Non-strict verifier should continue after failures."""
        verifier = ScenarioVerifier(strict=False)

        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        # Make an assertion that would fail
        verifier.verify_step_count(result, expected_executed=999)  # Wrong!

        # Should not raise, but should have warning
        assert len(verifier.warnings) > 0

    @pytest.mark.asyncio
    async def test_strict_mode_raises_on_assertion_failure(
        self, executor, verifier, scenarios_dir
    ):
        """Strict verifier should raise on failed assertion."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        # Wrong assertion should raise
        with pytest.raises(VerificationError):
            verifier.verify_step_count(result, expected_executed=999)

    @pytest.mark.asyncio
    async def test_verify_multiple_scenarios_in_sequence(
        self, executor, verifier, scenarios_dir, bot
    ):
        """Verify multiple scenarios can be run and verified in sequence."""
        # Run scenario 1
        scenario1 = load_scenario(scenarios_dir / "smoke_test.yaml")
        result1 = await executor.run(scenario1)
        verifier.verify_result_passed(result1)

        # Reset bot
        bot.reset()
        verifier.reset_warnings()

        # Run scenario 2
        scenario2 = load_scenario(scenarios_dir / "profile_setup.yaml")
        result2 = await executor.run(scenario2)
        verifier.verify_result_passed(result2)

        # Both should have passed
        assert result1.passed and result2.passed

    @pytest.mark.asyncio
    async def test_verify_profile_partial_match(
        self, executor, verifier, scenarios_dir, bot
    ):
        """Verify profile can be checked partially."""
        scenario = load_scenario(scenarios_dir / "profile_setup.yaml")
        result = await executor.run(scenario)

        # Check only sex and birth_year (not all fields)
        verifier.verify_profile_matches(
            bot,
            expected={"sex": "m", "birth_year": 1985},
        )

    @pytest.mark.asyncio
    async def test_verify_bot_state_transitions(
        self, executor, verifier, scenarios_dir, bot
    ):
        """Verify bot state transitions during scenario."""
        # Initial state
        assert bot.state == "idle"

        scenario = load_scenario(scenarios_dir / "profile_setup.yaml")
        result = await executor.run(scenario)

        # Final state should be idle again
        verifier.verify_bot_state(bot, expected_state="idle")

    @pytest.mark.asyncio
    async def test_artifacts_include_all_data(
        self, executor, verifier, scenarios_dir
    ):
        """Verify artifacts include all relevant data."""
        scenario = load_scenario(scenarios_dir / "profile_setup.yaml")
        result = await executor.run(scenario)

        artifacts = verifier.collect_artifacts(result)

        # Check all expected keys
        assert "scenario_id" in artifacts
        assert "passed" in artifacts
        assert "duration_sec" in artifacts
        assert "steps" in artifacts
        assert "error" in artifacts
        assert "logs" in artifacts
        assert "screenshots" in artifacts
        assert "warnings" in artifacts
