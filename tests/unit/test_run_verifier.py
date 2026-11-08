"""Unit tests for the run verifier on prepared run folders, judge included (M9b-3, M9b-4)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from testforge.config import CostLimits, LLMConfig
from testforge.providers import MockProvider
from testforge.providers.base import LLMResponse
from testforge.reporting import LLMCall, RunStore
from testforge.scenarios import ActionType, ExecutionTrace, Scenario, ScenarioResult, Step, StepTrace
from testforge.validation import ExpectationsError, RunVerifier
from testforge.validation.models import CheckResult, combine_status

NOW = datetime(2026, 11, 9, 10, 0, 0)
RUBRICS = str(Path(__file__).resolve().parents[2] / "fixtures" / "rubrics")
LIMITS = CostLimits(per_scenario_max_usd=0.20, per_run_max_usd=0.50, alert_threshold_usd=0.40)
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
JUDGE_EXPECTATIONS = EXPECTATIONS + (
    'document_summary: "АЛТ 25 Ед/л. Все значения в норме."\n'
    "llm_judge:\n"
    "  rubric: interpretation_quality_v1\n"
)


def _judge_text(overrides=None, *, overall="Разбор понятный."):
    values = {
        "clarity": 8.2,
        "medical_appropriateness": 8.8,
        "russian_grammar": 8.0,
        "disclaimer_compliance": 10.0,
    }
    values.update(overrides or {})
    data = {name: {"score": score, "reasoning": "Обосновано."} for name, score in values.items()}
    data["overall_assessment"] = overall
    return json.dumps(data, ensure_ascii=False)


class ScriptedProvider(MockProvider):
    """Judge stand-in: records prompts, returns fixed text and cost, or fails on request."""

    def __init__(self, text=None, cost=0.02, error=None):
        super().__init__(
            LLMConfig(provider="mock", api_key="", model="judge-model"),
            responses={"default": text or _judge_text()},
        )
        self.text = text or _judge_text()
        self.cost = cost
        self.error = error
        self.prompts = []

    async def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return LLMResponse(
            text=self.text,
            tokens_in=100,
            tokens_out=50,
            cost_usd=self.cost,
            duration_sec=0.1,
            model="judge-model",
            provider="mock",
        )


def _call(cost):
    return LLMCall(
        purpose="judge",
        model="claude-sonnet-4",
        tokens_in=10,
        tokens_out=5,
        cost_usd=cost,
        duration_sec=1.0,
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


def _expectations(tmp_path, text=EXPECTATIONS):
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


def _verifier(store, provider=None):
    return RunVerifier(store, LIMITS, provider=provider, rubrics_dir=RUBRICS)


def _statuses(verification):
    return {check.name: check.status for check in verification.checks}


class TestChecksWithoutJudge:
    @pytest.mark.asyncio
    async def test_good_run_passes_every_requested_check(self, tmp_path):
        store, run_dir = _save(tmp_path, calls=[_call(0.02)])
        scenario = _scenario(
            _expectations(tmp_path),
            compliance=True,
            cost_budget_usd=0.20,
            performance_budget_sec=120,
        )

        verification = await _verifier(store).verify(run_dir, scenario)

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

    @pytest.mark.asyncio
    async def test_nothing_requested_only_checks_cost_against_the_cap(self, tmp_path):
        store, run_dir = _save(tmp_path)

        verification = await _verifier(store).verify(run_dir, _scenario())

        assert _statuses(verification) == {
            "schema": "skipped",
            "compliance": "skipped",
            "cost": "pass",
            "performance": "skipped",
            "llm_judge": "skipped",
        }
        assert verification.status == "pass"

    @pytest.mark.asyncio
    async def test_missing_section_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD.replace("**Ключевые моменты:**", ""))

        verification = await _verifier(store).verify(run_dir, _scenario(_expectations(tmp_path)))

        assert _statuses(verification)["schema"] == "fail"
        assert verification.status == "fail"

    @pytest.mark.asyncio
    async def test_no_capture_fails_schema_and_compliance(self, tmp_path):
        store, run_dir = _save(tmp_path, text=None)

        verification = await _verifier(store).verify(
            run_dir, _scenario(_expectations(tmp_path), compliance=True)
        )

        statuses = _statuses(verification)
        assert statuses["schema"] == "fail"
        assert statuses["compliance"] == "fail"

    @pytest.mark.asyncio
    async def test_forbidden_phrase_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD + " Нужен диагноз.")

        verification = await _verifier(store).verify(run_dir, _scenario(compliance=True))

        assert _statuses(verification)["compliance"] == "fail"
        assert verification.status == "fail"

    @pytest.mark.asyncio
    async def test_phrase_forbidden_by_the_expectations_file_fails(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD + " Вам назначаю витамины.")

        verification = await _verifier(store).verify(
            run_dir, _scenario(_expectations(tmp_path), compliance=True)
        )

        assert _statuses(verification)["compliance"] == "fail"

    @pytest.mark.asyncio
    async def test_missing_disclaimer_fails(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD.replace("Не заменяет консультацию врача.", ""))

        verification = await _verifier(store).verify(run_dir, _scenario(compliance=True))

        assert _statuses(verification)["compliance"] == "fail"

    @pytest.mark.asyncio
    async def test_compliance_not_requested_is_skipped_even_with_bad_text(self, tmp_path):
        store, run_dir = _save(tmp_path, text=GOOD + " Нужен диагноз.")

        verification = await _verifier(store).verify(run_dir, _scenario())

        assert _statuses(verification)["compliance"] == "skipped"

    @pytest.mark.asyncio
    async def test_spend_over_scenario_budget_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path, calls=[_call(0.30)])

        verification = await _verifier(store).verify(run_dir, _scenario(cost_budget_usd=0.20))

        assert _statuses(verification)["cost"] == "fail"
        assert verification.status == "fail"

    @pytest.mark.asyncio
    async def test_scenario_budget_above_config_cap_warns(self, tmp_path):
        store, run_dir = _save(tmp_path)

        verification = await _verifier(store).verify(run_dir, _scenario(cost_budget_usd=0.50))

        assert _statuses(verification)["cost"] == "warn"
        assert verification.status == "warn"

    @pytest.mark.asyncio
    async def test_over_time_budget_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path, duration=130.0)

        verification = await _verifier(store).verify(run_dir, _scenario(performance_budget_sec=120))

        assert _statuses(verification)["performance"] == "fail"
        assert verification.status == "fail"

    @pytest.mark.asyncio
    async def test_tighter_of_scenario_and_expectations_time_budget_applies(self, tmp_path):
        store, run_dir = _save(tmp_path, duration=90.0)
        path = _expectations(tmp_path, EXPECTATIONS + "performance:\n  total_e2e_max_sec: 60\n")

        verification = await _verifier(store).verify(
            run_dir, _scenario(path, performance_budget_sec=120)
        )

        performance = next(check for check in verification.checks if check.name == "performance")
        assert performance.status == "fail"
        assert performance.details["budget_sec"] == 60

    @pytest.mark.asyncio
    async def test_expectations_time_budget_alone_is_used_when_scenario_has_none(self, tmp_path):
        store, run_dir = _save(tmp_path, duration=90.0)
        path = _expectations(tmp_path, EXPECTATIONS + "performance:\n  total_e2e_max_sec: 60\n")

        verification = await _verifier(store).verify(run_dir, _scenario(path))

        assert _statuses(verification)["performance"] == "fail"

    @pytest.mark.asyncio
    async def test_unverified_expectations_make_the_verdict_warn(self, tmp_path):
        store, run_dir = _save(tmp_path)
        path = _expectations(tmp_path, EXPECTATIONS + "vision_extraction:\n  min_count: 4\n")

        verification = await _verifier(store).verify(run_dir, _scenario(path))

        assert _statuses(verification)["schema"] == "pass"
        assert any(note.startswith("vision_extraction:") for note in verification.unverified)
        assert verification.status == "warn"

    @pytest.mark.asyncio
    async def test_invalid_expectations_file_is_an_error_not_a_verdict(self, tmp_path):
        store, run_dir = _save(tmp_path)
        path = _expectations(tmp_path, "document_id: d\ninterpretaton: {}\n")

        with pytest.raises(ExpectationsError):
            await _verifier(store).verify(run_dir, _scenario(path))


class TestJudgeCheck:
    @pytest.mark.asyncio
    async def test_judge_pass_is_recorded_with_cost_report_and_verdict(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider(cost=0.02)
        scenario = _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS), llm_judge=True)

        verification = await _verifier(store, provider).verify(run_dir, scenario)

        assert _statuses(verification)["llm_judge"] == "pass"
        assert verification.status == "pass"
        assert verification.judge.weighted_score == pytest.approx(8.67)
        assert len(provider.prompts) == 1
        cost = json.loads((run_dir / "cost.json").read_text(encoding="utf-8"))
        assert [call["purpose"] for call in cost["calls"]] == ["judge"]
        assert cost["total_cost_usd"] == pytest.approx(0.02)
        report = (run_dir / "judge_detailed.md").read_text(encoding="utf-8")
        assert report.startswith("# Judge report: interpretation_quality_v1")

    @pytest.mark.asyncio
    async def test_critical_failure_fails_the_run(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider(text=_judge_text({"medical_appropriateness": 7.0}))
        scenario = _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS), llm_judge=True)

        verification = await _verifier(store, provider).verify(run_dir, scenario)

        assert _statuses(verification)["llm_judge"] == "fail"
        assert verification.status == "fail"

    @pytest.mark.asyncio
    async def test_non_critical_warning_makes_the_check_warn(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider(text=_judge_text({"clarity": 6.0}))
        scenario = _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS), llm_judge=True)

        verification = await _verifier(store, provider).verify(run_dir, scenario)

        assert _statuses(verification)["llm_judge"] == "warn"
        assert verification.status == "warn"

    @pytest.mark.asyncio
    async def test_required_judge_without_provider_warns(self, tmp_path):
        store, run_dir = _save(tmp_path)
        scenario = _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS), llm_judge=True)

        verification = await _verifier(store).verify(run_dir, scenario)

        assert _statuses(verification)["llm_judge"] == "warn"
        assert verification.judge is None

    @pytest.mark.asyncio
    async def test_missing_summary_fails_before_any_spend(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider()
        path = _expectations(tmp_path, EXPECTATIONS + "llm_judge:\n  rubric: interpretation_quality_v1\n")

        verification = await _verifier(store, provider).verify(
            run_dir, _scenario(path, llm_judge=True)
        )

        assert _statuses(verification)["llm_judge"] == "fail"
        assert provider.prompts == []

    @pytest.mark.asyncio
    async def test_missing_capture_fails_before_any_spend(self, tmp_path):
        store, run_dir = _save(tmp_path, text=None)
        provider = ScriptedProvider()

        verification = await _verifier(store, provider).verify(
            run_dir, _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS), llm_judge=True)
        )

        assert _statuses(verification)["llm_judge"] == "fail"
        assert provider.prompts == []

    @pytest.mark.asyncio
    async def test_no_llm_judge_section_fails(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider()
        path = _expectations(tmp_path, EXPECTATIONS + 'document_summary: "x"\n')

        verification = await _verifier(store, provider).verify(
            run_dir, _scenario(path, llm_judge=True)
        )

        assert _statuses(verification)["llm_judge"] == "fail"
        assert provider.prompts == []

    @pytest.mark.asyncio
    async def test_unknown_rubric_fails_before_any_spend(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider()
        path = _expectations(
            tmp_path,
            JUDGE_EXPECTATIONS.replace("interpretation_quality_v1", "no_such_rubric"),
        )

        verification = await _verifier(store, provider).verify(
            run_dir, _scenario(path, llm_judge=True)
        )

        llm_judge = next(check for check in verification.checks if check.name == "llm_judge")
        assert llm_judge.status == "fail"
        assert "rubric not found" in llm_judge.messages[0]
        assert provider.prompts == []

    @pytest.mark.asyncio
    async def test_provider_error_fails_the_check_and_records_nothing(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider(error=RuntimeError("network down"))

        verification = await _verifier(store, provider).verify(
            run_dir, _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS), llm_judge=True)
        )

        llm_judge = next(check for check in verification.checks if check.name == "llm_judge")
        assert llm_judge.status == "fail"
        assert "judge failed: LLM call failed: network down" in llm_judge.messages[0]
        assert verification.judge is None
        cost = json.loads((run_dir / "cost.json").read_text(encoding="utf-8"))
        assert cost["calls"] == []

    @pytest.mark.asyncio
    async def test_judge_spend_counts_against_the_scenario_budget(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider(cost=0.30)
        scenario = _scenario(
            _expectations(tmp_path, JUDGE_EXPECTATIONS),
            llm_judge=True,
            cost_budget_usd=0.20,
        )

        verification = await _verifier(store, provider).verify(run_dir, scenario)

        assert _statuses(verification)["cost"] == "fail"
        assert verification.status == "fail"

    @pytest.mark.asyncio
    async def test_every_verification_records_its_judge_call(self, tmp_path):
        store, run_dir = _save(tmp_path)
        verifier = _verifier(store, ScriptedProvider(cost=0.02))
        scenario = _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS), llm_judge=True)

        await verifier.verify(run_dir, scenario)
        await verifier.verify(run_dir, scenario)

        cost = json.loads((run_dir / "cost.json").read_text(encoding="utf-8"))
        assert len(cost["calls"]) == 2
        assert cost["total_cost_usd"] == pytest.approx(0.04)

    @pytest.mark.asyncio
    async def test_cost_json_gets_the_scenario_budget(self, tmp_path):
        store, run_dir = _save(tmp_path)

        await _verifier(store).verify(run_dir, _scenario(cost_budget_usd=0.20))

        cost = json.loads((run_dir / "cost.json").read_text(encoding="utf-8"))
        assert cost["budget_usd"] == 0.20

    @pytest.mark.asyncio
    async def test_judge_section_without_request_is_reported_as_unverified(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider()

        verification = await _verifier(store, provider).verify(
            run_dir, _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS))
        )

        assert _statuses(verification)["llm_judge"] == "skipped"
        assert provider.prompts == []
        assert "llm_judge: the scenario does not request the judge" in verification.unverified
        assert verification.status == "warn"

    @pytest.mark.asyncio
    async def test_judge_not_requested_is_skipped_and_costs_nothing(self, tmp_path):
        store, run_dir = _save(tmp_path)
        provider = ScriptedProvider()

        verification = await _verifier(store, provider).verify(run_dir, _scenario())

        assert _statuses(verification)["llm_judge"] == "skipped"
        assert provider.prompts == []


class TestVerificationFile:
    @pytest.mark.asyncio
    async def test_verification_json_is_saved_by_verify(self, tmp_path):
        store, run_dir = _save(tmp_path)

        await _verifier(store).verify(run_dir, _scenario(compliance=True))

        saved = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
        assert saved["run_id"] == run_dir.name
        assert saved["status"] == "pass"
        assert [check["name"] for check in saved["checks"]] == [
            "schema",
            "compliance",
            "cost",
            "performance",
            "llm_judge",
        ]

    @pytest.mark.asyncio
    async def test_judge_scores_are_saved_for_later_baselines(self, tmp_path):
        store, run_dir = _save(tmp_path)

        await _verifier(store, ScriptedProvider()).verify(
            run_dir, _scenario(_expectations(tmp_path, JUDGE_EXPECTATIONS), llm_judge=True)
        )

        saved = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
        scores = {d["id"]: d["score"] for d in saved["judge"]["dimensions"]}
        assert scores == {
            "clarity": 8.2,
            "medical_appropriateness": 8.8,
            "russian_grammar": 8.0,
            "disclaimer_compliance": 10.0,
        }


class TestCombineStatus:
    @staticmethod
    def _check(status):
        return CheckResult(name="x", status=status)

    def test_any_fail_wins(self):
        checks = [self._check("pass"), self._check("fail"), self._check("warn")]

        assert combine_status(checks) == "fail"

    def test_warn_beats_pass(self):
        assert combine_status([self._check("pass"), self._check("warn")]) == "warn"

    def test_unverified_items_make_it_warn(self):
        assert combine_status([self._check("pass")], unverified=["vision"]) == "warn"

    def test_skipped_checks_do_not_count_as_pass(self):
        assert combine_status([self._check("skipped")]) == "skipped"

    def test_pass_when_something_ran_and_passed(self):
        assert combine_status([self._check("skipped"), self._check("pass")]) == "pass"
