"""Unit tests for the run duration check against the time budget (M9b-3)."""

from datetime import datetime, timezone

from testforge.scenarios import ActionType, ExecutionTrace, StepTrace
from testforge.validation.performance import check_performance


def _trace(total, step_durations):
    return ExecutionTrace(
        scenario_id="s",
        started_at=datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc),
        duration_sec=total,
        passed=True,
        steps=[
            StepTrace(
                index=index,
                action=ActionType.WAIT,
                started_sec=0.0,
                duration_sec=duration,
                passed=True,
            )
            for index, duration in enumerate(step_durations)
        ],
    )


class TestPerformanceCheck:
    def test_no_budget_is_skipped_but_keeps_the_breakdown(self):
        result = check_performance(_trace(3.0, [1.0, 2.0]), budget_sec=None)

        assert result.name == "performance"
        assert result.status == "skipped"
        assert len(result.details["steps"]) == 2

    def test_within_budget_passes(self):
        result = check_performance(_trace(68.0, [10.0, 58.0]), budget_sec=120)

        assert result.status == "pass"
        assert result.details["total_sec"] == 68.0

    def test_exactly_the_budget_passes(self):
        assert check_performance(_trace(120.0, [120.0]), budget_sec=120).status == "pass"

    def test_over_budget_fails(self):
        result = check_performance(_trace(130.0, [30.0, 100.0]), budget_sec=120)

        assert result.status == "fail"
        assert "exceeds budget 120.0s" in result.messages[0]

    def test_slowest_step_is_named_with_its_number(self):
        result = check_performance(_trace(130.0, [30.0, 100.0]), budget_sec=120)

        assert any("slowest step: #2 wait, 100.0s" in message for message in result.messages)

    def test_breakdown_lists_every_step(self):
        result = check_performance(_trace(3.0, [1.0, 2.0]), budget_sec=120)

        assert result.details["steps"] == [
            {"index": 0, "action": "wait", "duration_sec": 1.0},
            {"index": 1, "action": "wait", "duration_sec": 2.0},
        ]
