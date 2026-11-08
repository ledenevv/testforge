"""Unit tests for the execution trace model, cost record and run folders (M9b-2)."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from testforge.reporting import CostReport, LLMCall, RunNotFoundError, RunStore
from testforge.scenarios import ActionType, ExecutionTrace, ScenarioResult, StepTrace

NOW = datetime(2026, 11, 8, 15, 30, 22)


def _call(cost, tokens_in=10, tokens_out=5):
    return LLMCall(
        purpose="judge",
        model="claude-sonnet-4",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost,
        duration_sec=1.0,
    )


def _trace(passed=True):
    return ExecutionTrace(
        scenario_id="smoke_test",
        started_at=datetime(2026, 11, 8, 15, 30, 22, tzinfo=timezone.utc),
        duration_sec=1.5,
        passed=passed,
        steps=[
            StepTrace(
                index=0,
                action=ActionType.SEND_MESSAGE,
                started_sec=0.0,
                duration_sec=0.5,
                sent="/start",
                replies=["Привет! Этот бот анализирует документы."],
                passed=True,
            )
        ],
        captures={"interpretation": "Резюме: норма"},
    )


def _result(trace=None):
    return ScenarioResult(
        scenario_id="smoke_test",
        passed=True,
        duration_sec=1.5,
        steps_executed=1,
        steps_passed=1,
        steps_failed=0,
        trace=trace,
    )


class TestTraceModels:
    def test_step_index_and_timing_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            StepTrace(index=-1, action=ActionType.WAIT, started_sec=0)
        with pytest.raises(ValidationError):
            StepTrace(index=0, action=ActionType.WAIT, started_sec=-1)

    def test_step_starts_as_not_passed_with_no_replies(self):
        step = StepTrace(index=0, action=ActionType.WAIT, started_sec=0)

        assert step.passed is False
        assert step.replies == []
        assert step.error is None

    def test_trace_is_optional_on_scenario_result(self):
        assert _result().trace is None


class TestCostReport:
    def test_total_is_the_sum_of_the_calls(self):
        report = CostReport.from_calls("s", [_call(0.02), _call(0.03)], budget_usd=0.2)

        assert report.total_cost_usd == pytest.approx(0.05)
        assert report.budget_used == pytest.approx(0.25)
        assert len(report.calls) == 2

    def test_no_calls_means_zero_spend(self):
        report = CostReport.from_calls("s", [], budget_usd=0.2)

        assert report.total_cost_usd == 0.0
        assert report.budget_used == 0.0

    def test_without_budget_there_is_no_share(self):
        assert CostReport.from_calls("s", [_call(0.02)]).budget_used is None

    def test_budget_must_be_positive(self):
        with pytest.raises(ValidationError):
            CostReport.from_calls("s", [], budget_usd=0)

    def test_negative_call_cost_rejected(self):
        with pytest.raises(ValidationError):
            _call(-0.01)


class TestRunFolders:
    def test_folder_is_named_after_the_start_time(self, tmp_path):
        run_dir = RunStore(tmp_path).create_run(NOW)

        assert run_dir.name == "run-20261108-153022"
        assert run_dir.is_dir()

    def test_two_runs_in_the_same_second_get_separate_folders(self, tmp_path):
        store = RunStore(tmp_path)

        first = store.create_run(NOW)
        second = store.create_run(NOW)

        assert first != second
        assert first.is_dir() and second.is_dir()


class TestSaveAndLoad:
    def test_save_run_writes_trace_and_cost_files(self, tmp_path):
        run_dir = RunStore(tmp_path).save_run(
            _result(_trace()), calls=[_call(0.02)], budget_usd=0.2, now=NOW
        )

        assert (run_dir / "trace.json").is_file()
        cost = json.loads((run_dir / "cost.json").read_text(encoding="utf-8"))
        assert cost["total_cost_usd"] == pytest.approx(0.02)
        assert cost["budget_used"] == pytest.approx(0.1)

    def test_trace_reads_back_unchanged(self, tmp_path):
        store = RunStore(tmp_path)
        trace = _trace()

        run_dir = store.save_run(_result(trace), now=NOW)

        assert store.load_trace(run_dir) == trace

    def test_trace_file_keeps_russian_text_readable(self, tmp_path):
        run_dir = RunStore(tmp_path).save_run(_result(_trace()), now=NOW)

        raw = (run_dir / "trace.json").read_text(encoding="utf-8")
        assert "Привет" in raw
        assert "\\u" not in raw

    def test_run_without_trace_cannot_be_saved(self, tmp_path):
        with pytest.raises(ValueError, match="no execution trace"):
            RunStore(tmp_path).save_run(_result(None), now=NOW)


class TestResolve:
    def test_latest_follows_the_most_recent_save(self, tmp_path):
        store = RunStore(tmp_path)
        store.save_run(_result(_trace()), now=datetime(2026, 11, 8, 15, 0, 0))
        last = store.save_run(_result(_trace()), now=datetime(2026, 11, 8, 16, 0, 0))

        assert store.resolve("latest") == last
        assert store.resolve("run-20261108-160000") == last

    def test_latest_without_any_run_is_an_error(self, tmp_path):
        with pytest.raises(RunNotFoundError, match="no runs"):
            RunStore(tmp_path).resolve("latest")

    def test_unknown_run_name_is_an_error(self, tmp_path):
        store = RunStore(tmp_path)
        store.create_run(NOW)

        with pytest.raises(RunNotFoundError):
            store.resolve("run-19990101-000000")

    @pytest.mark.parametrize("ref", ["../outside", "sub/run", "."])
    def test_reference_cannot_leave_the_runs_folder(self, tmp_path, ref):
        (tmp_path / "outside").mkdir()
        (tmp_path / "runs" / "sub" / "run").mkdir(parents=True)

        with pytest.raises(RunNotFoundError):
            RunStore(tmp_path / "runs").resolve(ref)
