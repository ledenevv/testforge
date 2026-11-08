"""Run artifacts written from real executor runs against the mock bot (M9b-2)."""

import json
from datetime import datetime

import pytest

from testforge.executor import ScenarioExecutor
from testforge.reporting import LLMCall, RunStore
from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step, load_scenario
from testforge.telegram import MockTelegramBot

SMOKE = "fixtures/scenarios/smoke_test.yaml"
SAVED_AT = datetime(2026, 11, 8, 15, 30, 22)


@pytest.fixture
def executor():
    return ScenarioExecutor(bot=MockTelegramBot(responses_dir="fixtures/mock_responses"))


@pytest.fixture
def store(tmp_path):
    return RunStore(tmp_path / "runs")


class TestSmokeRunArtifacts:
    @pytest.mark.asyncio
    async def test_trace_json_reads_back_as_the_same_trace(self, executor, store):
        result = await executor.run(load_scenario(SMOKE))

        run_dir = store.save_run(result, now=SAVED_AT)

        assert store.load_trace(run_dir) == result.trace

    @pytest.mark.asyncio
    async def test_trace_has_one_entry_per_step_with_what_was_sent_and_said(self, executor):
        trace = (await executor.run(load_scenario(SMOKE))).trace

        assert trace.passed is True
        assert trace.error is None
        assert [s.index for s in trace.steps] == [0, 1, 2]
        assert all(s.passed and s.error is None for s in trace.steps)
        assert all(s.action == ActionType.SEND_MESSAGE for s in trace.steps)
        assert [s.sent for s in trace.steps] == ["/start", "/help", "/unknown_command_xyz"]
        assert any("Привет" in text for text in trace.steps[0].replies)
        assert trace.steps[1].started_sec >= trace.steps[0].started_sec
        assert trace.captures == {}

    @pytest.mark.asyncio
    async def test_cost_json_total_is_the_sum_of_judge_calls(self, executor, store):
        result = await executor.run(load_scenario(SMOKE))
        calls = [
            LLMCall(
                purpose="judge",
                model="claude-sonnet-4",
                tokens_in=5000,
                tokens_out=800,
                cost_usd=0.0230,
                duration_sec=4.1,
            ),
            LLMCall(
                purpose="judge",
                model="claude-sonnet-4",
                tokens_in=5100,
                tokens_out=750,
                cost_usd=0.0228,
                duration_sec=3.9,
            ),
        ]

        run_dir = store.save_run(result, calls=calls, budget_usd=0.20, now=SAVED_AT)

        cost = json.loads((run_dir / "cost.json").read_text(encoding="utf-8"))
        expected_total = sum(call.cost_usd for call in calls)
        assert cost["total_cost_usd"] == pytest.approx(expected_total)
        assert [call["cost_usd"] for call in cost["calls"]] == [0.0230, 0.0228]
        assert cost["budget_used"] == pytest.approx(expected_total / 0.20)

    @pytest.mark.asyncio
    async def test_cost_json_without_judge_calls_is_zero(self, executor, store):
        result = await executor.run(load_scenario(SMOKE))

        run_dir = store.save_run(result, now=SAVED_AT)

        cost = json.loads((run_dir / "cost.json").read_text(encoding="utf-8"))
        assert cost["total_cost_usd"] == 0.0
        assert cost["calls"] == []
        assert cost["budget_used"] is None

    @pytest.mark.asyncio
    async def test_latest_resolves_to_the_last_saved_run(self, executor, store):
        first = await executor.run(load_scenario(SMOKE))
        store.save_run(first, now=datetime(2026, 11, 8, 15, 0, 0))
        second = await executor.run(load_scenario(SMOKE))
        last_dir = store.save_run(second, now=datetime(2026, 11, 8, 16, 0, 0))

        assert store.resolve("latest") == last_dir
        assert store.load_trace(store.resolve("latest")) == second.trace


class TestFailedRunsAreRecorded:
    @pytest.mark.asyncio
    async def test_critical_failure_ends_the_trace_and_keeps_what_the_bot_said(self, executor):
        scenario = Scenario(
            id="fails_early",
            description="The first step can never match",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(contains="NOT_THERE"),
                ),
                Step(action=ActionType.SEND_MESSAGE, text="/help"),
            ],
        )

        trace = (await executor.run(scenario)).trace

        assert trace.passed is False
        assert len(trace.steps) == 1
        assert trace.steps[0].passed is False
        assert "NOT_THERE" in trace.steps[0].error
        assert trace.steps[0].replies  # the bot's actual answer is kept for debugging
        assert trace.error == trace.steps[0].error

    @pytest.mark.asyncio
    async def test_non_critical_failure_keeps_later_steps_in_the_trace(self, executor):
        scenario = Scenario(
            id="soft_fail",
            description="An optional check fails, the rest still runs",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(contains="NOT_THERE"),
                    critical=False,
                ),
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/help",
                    expect=ExpectCondition(contains="Справка"),
                ),
            ],
        )

        trace = (await executor.run(scenario)).trace

        assert [s.passed for s in trace.steps] == [False, True]
        assert trace.passed is False

    @pytest.mark.asyncio
    async def test_timeout_records_the_step_that_was_running(self, executor):
        scenario = Scenario(
            id="too_slow",
            description="The second wait outlasts the scenario timeout",
            timeout_sec=1,
            steps=[
                Step(action=ActionType.WAIT, duration_sec=0.1),
                Step(action=ActionType.WAIT, duration_sec=30),
            ],
        )

        trace = (await executor.run(scenario)).trace

        assert trace.passed is False
        assert "timed out" in trace.error
        assert len(trace.steps) == 2
        assert trace.steps[1].passed is False
        assert "timed out" in trace.steps[1].error
        assert trace.steps[1].duration_sec >= 0.8  # it ran until the timeout


class TestCapture:
    @pytest.mark.asyncio
    async def test_captured_replies_are_stored_under_their_name(self, executor, tmp_path):
        document = tmp_path / "lab_report.pdf"
        document.write_text("fake", encoding="utf-8")
        scenario = Scenario(
            id="capture_me",
            description="Upload a document, then keep the interpretation",
            steps=[
                Step(action=ActionType.SEND_DOCUMENT, document_path=str(document)),
                Step(
                    action=ActionType.EXPECT_RESPONSE,
                    expect=ExpectCondition(contains="Резюме"),
                    capture="interpretation",
                ),
            ],
        )

        result = await executor.run(scenario)

        assert result.passed is True
        assert "Резюме" in result.trace.captures["interpretation"]
        assert result.trace.steps[0].sent == "lab_report.pdf"
