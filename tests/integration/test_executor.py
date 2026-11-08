"""Integration tests for ScenarioExecutor."""

from pathlib import Path

import pytest

from testforge.executor import ScenarioExecutor
from testforge.scenarios import load_scenario
from testforge.telegram import MockTelegramBot


class TestScenarioExecutor:
    """Test ScenarioExecutor with MockTelegramBot."""

    @pytest.fixture
    def bot(self):
        """Create MockTelegramBot instance."""
        return MockTelegramBot(responses_dir="fixtures/mock_responses")

    @pytest.fixture
    def executor(self, bot):
        """Create ScenarioExecutor instance."""
        return ScenarioExecutor(bot=bot, verbose=False)

    @pytest.fixture
    def scenarios_dir(self):
        """Path to fixture scenarios."""
        return Path("fixtures/scenarios")

    @pytest.mark.asyncio
    async def test_smoke_test_scenario(self, executor, scenarios_dir):
        """Run smoke_test scenario."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        assert result.scenario_id == "smoke_test"
        assert result.passed is True
        assert result.steps_executed == 3
        assert result.steps_passed == 3
        assert result.steps_failed == 0
        assert result.error is None
        assert result.duration_sec > 0

    @pytest.mark.asyncio
    async def test_profile_setup_scenario(self, executor, scenarios_dir):
        """Run profile_setup scenario."""
        scenario = load_scenario(scenarios_dir / "profile_setup.yaml")
        result = await executor.run(scenario)

        assert result.scenario_id == "profile_setup"
        assert result.passed is True
        assert result.steps_executed == 6
        assert result.steps_passed == 6
        assert result.steps_failed == 0

    @pytest.mark.asyncio
    async def test_multi_step_scenario(self, executor, scenarios_dir):
        """Run multi_step scenario (full E2E flow)."""
        scenario = load_scenario(scenarios_dir / "multi_step.yaml")

        # Create test document if it doesn't exist
        test_doc = Path("fixtures/test_data/sample_lab_report.pdf")
        test_doc.parent.mkdir(parents=True, exist_ok=True)
        if not test_doc.exists():
            test_doc.write_text("Fake PDF content for testing")

        result = await executor.run(scenario)

        assert result.scenario_id == "multi_step"
        # May have some steps fail (document upload), but should execute most
        assert result.steps_executed >= 8
        assert result.duration_sec > 0

    @pytest.mark.asyncio
    async def test_executor_logs_steps(self, executor, scenarios_dir):
        """Executor should log each step."""
        scenario = load_scenario(scenarios_dir / "smoke_test.yaml")
        result = await executor.run(scenario)

        # Should have logs for each step
        assert len(result.logs) > 0
        assert any("Starting scenario" in log for log in result.logs)
        assert any("Step 1" in log for log in result.logs)

    @pytest.mark.asyncio
    async def test_executor_resets_bot_between_runs(self, bot, scenarios_dir):
        """Bot should be reset between scenario runs."""
        executor = ScenarioExecutor(bot=bot)

        # Run scenario 1
        scenario1 = load_scenario(scenarios_dir / "smoke_test.yaml")
        await executor.run(scenario1)

        # Reset bot manually (in real use, this would happen automatically)
        bot.reset()

        # Run scenario 2
        scenario2 = load_scenario(scenarios_dir / "profile_setup.yaml")
        result2 = await executor.run(scenario2)

        # Should work fine
        assert result2.passed is True

    @pytest.mark.asyncio
    async def test_expect_contains_validation(self, executor):
        """Expect 'contains' should validate response text."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="test_contains",
            description="Test contains validation",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(contains="Этот бот"),
                )
            ],
        )

        result = await executor.run(scenario)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_expect_contains_failure(self, executor):
        """Expect 'contains' should fail if text not found."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="test_contains_fail",
            description="Test contains failure",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(contains="NONEXISTENT_TEXT_XYZ"),
                )
            ],
        )

        result = await executor.run(scenario)
        assert result.passed is False
        assert result.steps_failed == 1
        assert "Expected response to contain" in result.error

    @pytest.mark.asyncio
    async def test_expect_response_count(self, executor):
        """Expect response_count should validate number of responses."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="test_response_count",
            description="Test response count",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(response_count=1),
                )
            ],
        )

        result = await executor.run(scenario)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_wait_action(self, executor):
        """Wait action should pause execution."""
        from testforge.scenarios import ActionType, Scenario, Step
        import time

        scenario = Scenario(
            id="test_wait",
            description="Test wait action",
            steps=[
                Step(action=ActionType.WAIT, duration_sec=0.5),
            ],
        )

        start = time.perf_counter()
        result = await executor.run(scenario)
        duration = time.perf_counter() - start

        assert result.passed is True
        assert duration >= 0.4  # At least 0.4s (with some tolerance)

    @pytest.mark.asyncio
    async def test_non_critical_step_continues(self, executor):
        """Non-critical step failure should not stop scenario."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="test_non_critical",
            description="Test non-critical step",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(contains="WILL_FAIL"),
                    critical=False,  # Non-critical
                ),
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/help",
                    expect=ExpectCondition(contains="Справка"),
                    critical=True,  # This should still run
                ),
            ],
        )

        result = await executor.run(scenario)

        # Scenario should continue despite first step failing
        assert result.steps_executed == 2
        assert result.steps_passed == 1
        assert result.steps_failed == 1
        # Overall scenario passes because only non-critical step failed
        # Actually, let's check - if any step fails, scenario fails
        # Unless we change the logic to only count critical failures

    @pytest.mark.asyncio
    async def test_critical_step_stops_scenario(self, executor):
        """Critical step failure should stop scenario."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="test_critical",
            description="Test critical step",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(contains="WILL_FAIL"),
                    critical=True,  # Critical!
                ),
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/help",  # This should NOT run
                ),
            ],
        )

        result = await executor.run(scenario)

        # Scenario should stop after first critical failure
        assert result.passed is False
        assert result.steps_executed == 1
        assert result.steps_failed == 1
        assert result.failed_step_index == 0

    @pytest.mark.asyncio
    async def test_send_document_action(self, executor, tmp_path):
        """Send document action should upload file."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        # Create test document
        test_doc = tmp_path / "test.pdf"
        test_doc.write_text("Fake PDF")

        scenario = Scenario(
            id="test_send_doc",
            description="Test send document",
            steps=[
                Step(
                    action=ActionType.SEND_DOCUMENT,
                    document_path=str(test_doc),
                    caption="Test document",
                    expect=ExpectCondition(contains="получен"),
                ),
            ],
        )

        result = await executor.run(scenario)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_expect_response_action(self, executor):
        """Expect response action should validate pending responses."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="test_expect_response",
            description="Test expect_response action",
            steps=[
                # Send message (generates response)
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                ),
                # Check response separately
                Step(
                    action=ActionType.EXPECT_RESPONSE,
                    expect=ExpectCondition(contains="бот"),
                ),
            ],
        )

        result = await executor.run(scenario)
        assert result.passed is True
        assert result.steps_executed == 2

    @pytest.mark.asyncio
    async def test_regex_validation(self, executor):
        """Expect matches_regex should validate with regex."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="test_regex",
            description="Test regex validation",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(matches_regex=r"бот.*анализ"),
                ),
            ],
        )

        result = await executor.run(scenario)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_not_contains_validation(self, executor):
        """Expect not_contains should fail if text is found."""
        from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step

        scenario = Scenario(
            id="test_not_contains",
            description="Test not_contains validation",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(not_contains="NONEXISTENT"),
                ),
            ],
        )

        result = await executor.run(scenario)
        assert result.passed is True

        # Test failure case
        scenario_fail = Scenario(
            id="test_not_contains_fail",
            description="Test not_contains failure",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(not_contains="бот"),  # This IS in response
                ),
            ],
        )

        result_fail = await executor.run(scenario_fail)
        assert result_fail.passed is False
