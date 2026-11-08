"""Unit tests for the run verifier on prepared run folders (M9b-3)."""

import json
from datetime import datetime, timezone

import pytest

from testforge.config import CostLimits
from testforge.reporting import LLMCall, RunStore
from testforge.scenarios import ActionType, ExecutionTrace, Scenario, ScenarioResult, Step, StepTrace
from testforge.validation import ExpectationsError, RunVerifier
from testforge.validation.models import CheckResult, combine_status

NOW = datetime(2026, 11, 9, 10, 0, 0)
GOOD = (
    "📊 **Резюме**\n\n**Ключевые моменты:**\n- АЛТ: 25 Ед/л\n\n"
    "**Что обсудить с врачом:**\nРегулярный мониторинг полезен.\n\n"
    "⚠️ Это информационный разбор. Не заменяет консультацию врача."
)
EXPECTATIONS = """\
document_id: lab_report_001
interpretation:
  must_contain_sections:
    - "Резюме"
    - "Ключевые моменты"
    - "Что обсудить с врачом"
  must_not_contain_phrases:
    - "назначаю"
"""
LIMITS = CostLimits(per_scenario_max_usd=0.20, per_run_max_usd=0.50, alert_threshold_usd=0.40)


def _call(cost):
    return LLMCall(
        purpose="judge",
        model="claude-sonnet-4",
        tokens_in=1,
        tokens_out=1,
        cost_usd=cost,
        duration_sec=0.1,
    )


def _save(tmp_path, *, text=GOOD, duration=3.0, calls=()):
    """Save a run with one upload step whose replies carry `text` as the interpretation."""
    trace = ExecutionTrace(
        scenario_id="single_upload",
        started_at=datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc),
        duration_sec=duration,
        passed=True,
        steps=[
            StepTrace(
                index=0,
                action=ActionType.SEND_DOCUMENT,
                started_sec=0.0,
                duration_sec=duration,
                sent="lab_report_001.pdf",
                replies=[text] if text is not None else [],
                passed=True,
            )
        ],
        captures={"interpretation": text} if text is not None else {},
    )
    result = ScenarioResult(
        scenario_id="single_upload",
        passed=True,
        duration_sec=duration,
        steps_executed=1,
        steps_passed=1,
        steps_failed=0,
        trace=trace,
    )
    store = RunStore(tmp_path / "runs")
    run_dir = store.save_run(result, calls=list(calls), now=NOW)
    return store, run_dir


def _expectations_file(tmp_path, text=EXPECTATIONS):
    path = tmp_path / "expectations.yml"
    path.write_text(text, encoding="utf-8")
    return path


def _scenario(expectations=None, **validation):
    if expectations is not None:
        validation["expectations"] = str(expectations)
    return Scenario(
        id="single_upload",
        description="Upload one report",
        steps=[Step(action=ActionType.WAIT, duration_sec=0.1)],
        validation=validation,
    )


def _statuses(verification):
    return {check.name: check.status for check in verification.checks}


class TestAllChecks:
    def test_good_run_passes_every_requested_check(self, tmp_path):
        store, run_dir = _save(tmp_path, calls=[_call(0.02)])
        scenario = _scenario(
            _expectations_file(tmp_path),
            compliance=True,
            cost_budget_usd=0.20,
            performance_budget_sec=120,
        )

        verification = RunVerifier(store, LIMITS).verify(run_dir, scenario)

        assert _statuses(verification) == {
            "schema": "pass",
            "compliance": "pass",
            "cost": "pass",
            "performance": "pass",
            "llm_judge": "skipped",
        }
        assert verification.status == "pass"
        assert verification.unverified == []
        assert verification.expectations_file == str(tmp_path / "expectations.yml")

    def test_nothing_requested_only_checks_cost_against_the_cap(self, tmp_path):
        store, run_dir = _save(tmp_path)

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario())

        assert _statuses(verification) == {
            "schema": "skipped",
            "compliance": "skipped",
            "cost": "pass",
            "performance": "skipped",
            "llm_judge": "skipped",
        }
        assert verification.status == "pass"


class TestSchemaCheck:
    def test_missing_section_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD.replace("**Ключевые моменты:**", ""))
        scenario = _scenario(_expectations_file(tmp_path))

        verification = RunVerifier(store, LIMITS).verify(run_dir, scenario)

        assert _statuses(verification)["schema"] == "fail"
        assert verification.status == "fail"

    def test_no_capture_fails_the_schema_check(self, tmp_path):
        store, run_dir = _save(tmp_path, text=None)
        scenario = _scenario(_expectations_file(tmp_path))

        verification = RunVerifier(store, LIMITS).verify(run_dir, scenario)

        schema = next(check for check in verification.checks if check.name == "schema")
        assert schema.status == "fail"
        assert "no step captured the interpretation" in schema.messages

    def test_without_interpretation_section_schema_is_skipped(self, tmp_path):
        store, run_dir = _save(tmp_path)
        path = _expectations_file(tmp_path, "document_id: d\nperformance:\n  total_e2e_max_sec: 120\n")

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(path))

        assert _statuses(verification)["schema"] == "skipped"


class TestComplianceCheck:
    def test_forbidden_phrase_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD + " Нужен диагноз.")

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(compliance=True))

        assert _statuses(verification)["compliance"] == "fail"
        assert verification.status == "fail"

    def test_phrase_forbidden_by_the_expectations_file_fails(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD + " Вам назначаю витамины.")
        scenario = _scenario(_expectations_file(tmp_path), compliance=True)

        verification = RunVerifier(store, LIMITS).verify(run_dir, scenario)

        assert _statuses(verification)["compliance"] == "fail"

    def test_missing_disclaimer_fails(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD.replace("Не заменяет консультацию врача.", ""))

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(compliance=True))

        assert _statuses(verification)["compliance"] == "fail"

    def test_no_capture_fails_when_compliance_is_requested(self, tmp_path):
        store, run_dir = _save(tmp_path, text=None)

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(compliance=True))

        assert _statuses(verification)["compliance"] == "fail"

    def test_compliance_not_requested_is_skipped_even_with_bad_text(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD + " Нужен диагноз.")

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario())

        assert _statuses(verification)["compliance"] == "skipped"


class TestCostCheck:
    def test_spend_over_scenario_budget_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path, calls=[_call(0.30)])

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(cost_budget_usd=0.20))

        assert _statuses(verification)["cost"] == "fail"
        assert verification.status == "fail"

    def test_scenario_budget_above_config_cap_warns(self, tmp_path):
        store, run_dir = _save(tmp_path)

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(cost_budget_usd=0.50))

        assert _statuses(verification)["cost"] == "warn"
        assert verification.status == "warn"


class TestPerformanceCheck:
    def test_over_budget_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path, duration=130.0)

        verification = RunVerifier(store, LIMITS).verify(
            run_dir, _scenario(performance_budget_sec=120)
        )

        assert _statuses(verification)["performance"] == "fail"
        assert verification.status == "fail"

    def test_tighter_of_scenario_and_expectations_budget_applies(self, tmp_path):
        store, run_dir = _save(tmp_path, duration=90.0)
        path = _expectations_file(
            tmp_path,
            EXPECTATIONS + "performance:\n  total_e2e_max_sec: 60\n",
        )

        verification = RunVerifier(store, LIMITS).verify(
            run_dir, _scenario(path, performance_budget_sec=120)
        )

        performance = next(check for check in verification.checks if check.name == "performance")
        assert performance.status == "fail"
        assert performance.details["budget_sec"] == 60

    def test_expectations_budget_alone_is_used_when_scenario_has_none(self, tmp_path):
        store, run_dir = _save(tmp_path, duration=90.0)
        path = _expectations_file(tmp_path, EXPECTATIONS + "performance:\n  total_e2e_max_sec: 60\n")

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(path))

        assert _statuses(verification)["performance"] == "fail"


class TestJudgeAndUnverified:
    def test_judge_required_but_not_wired_warns(self, tmp_path):
        store, run_dir = _save(tmp_path)

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(llm_judge=True))

        assert _statuses(verification)["llm_judge"] == "warn"
        assert verification.status == "warn"

    def test_unverified_expectations_make_the_verdict_warn(self, tmp_path):
        store, run_dir = _save(tmp_path)
        path = _expectations_file(
            tmp_path,
            EXPECTATIONS + "vision_extraction:\n  min_count: 4\n",
        )

        verification = RunVerifier(store, LIMITS).verify(run_dir, _scenario(path))

        assert _statuses(verification)["schema"] == "pass"
        assert any(note.startswith("vision_extraction:") for note in verification.unverified)
        assert verification.status == "warn"

    def test_invalid_expectations_file_is_an_error_not_a_verdict(self, tmp_path):
        store, run_dir = _save(tmp_path)
        path = _expectations_file(tmp_path, "document_id: d\ninterpretaton: {}\n")

        with pytest.raises(ExpectationsError):
            RunVerifier(store, LIMITS).verify(run_dir, _scenario(path))


class TestVerificationFile:
    def test_verification_json_is_written_and_readable(self, tmp_path):
        store, run_dir = _save(tmp_path)
        verifier = RunVerifier(store, LIMITS)
        verification = verifier.verify(run_dir, _scenario(compliance=True))

        path = verifier.write(run_dir, verification)

        assert path == run_dir / "verification.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["run_id"] == run_dir.name
        assert saved["status"] == "pass"
        assert [check["name"] for check in saved["checks"]] == [
            "schema",
            "compliance",
            "cost",
            "performance",
            "llm_judge",
        ]


class TestCombineStatus:
    @staticmethod
    def _check(status):
        return CheckResult(name="x", status=status)

    def test_any_fail_wins(self):
        assert combine_status([self._check("pass"), self._check("fail"), self._check("warn")]) == "fail"

    def test_warn_beats_pass(self):
        assert combine_status([self._check("pass"), self._check("warn")]) == "warn"

    def test_unverified_items_make_it_warn(self):
        assert combine_status([self._check("pass")], unverified=["vision"]) == "warn"

    def test_skipped_checks_do_not_count_as_pass(self):
        assert combine_status([self._check("skipped")]) == "skipped"

    def test_pass_when_something_ran_and_passed(self):
        assert combine_status([self._check("skipped"), self._check("pass")]) == "pass"
