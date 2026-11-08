"""Checks a finished run against its scenario and expectations, and saves the verdict."""

from pathlib import Path

from pydantic import BaseModel, Field

from testforge.config import CostLimits
from testforge.judge import (
    RUBRICS_DIR,
    JudgeEvaluationError,
    JudgeVerdict,
    LLMJudge,
    RubricError,
    find_rubric,
    load_rubric,
    render_judge_report,
)
from testforge.providers.base import LLMProvider
from testforge.reporting.run_store import CostReport, LLMCall, RunStore
from testforge.scenarios.models import Scenario
from testforge.validation.compliance import check_compliance
from testforge.validation.cost import check_cost
from testforge.validation.models import CheckResult, CheckStatus, combine_status
from testforge.validation.performance import check_performance
from testforge.validation.schema import (
    Expectations,
    check_interpretation,
    load_expectations,
    unverified_sections,
)

VERIFICATION_FILE = "verification.json"
JUDGE_REPORT_FILE = "judge_detailed.md"
# Name of the capture the interpretation text is read from (see Step.capture)
INTERPRETATION = "interpretation"


class RunVerification(BaseModel):
    """Verdict for one run, saved as verification.json."""

    run_id: str = Field(description="Name of the run folder")
    scenario_id: str
    expectations_file: str | None = Field(default=None, description="Expectations file used, if any")
    status: CheckStatus = Field(description="Overall verdict")
    checks: list[CheckResult] = Field(default_factory=list)
    unverified: list[str] = Field(
        default_factory=list,
        description="Expectations this version cannot check, each with the reason",
    )
    judge: JudgeVerdict | None = Field(
        default=None,
        description="Per-dimension judge scores, if the judge ran",
    )


def _failed(name: str, message: str) -> CheckResult:
    return CheckResult(name=name, status="fail", messages=[message])


class RunVerifier:
    """Runs every check a scenario asks for against one run folder and saves the verdict."""

    def __init__(
        self,
        store: RunStore | None = None,
        limits: CostLimits | None = None,
        provider: LLMProvider | None = None,
        rubrics_dir: str = RUBRICS_DIR,
    ):
        """
        Args:
            store: Where runs are kept (default: ./runs)
            limits: Cost limits from the config (default: CostLimits defaults)
            provider: LLM provider for the judge. Without one, a judge the scenario
                requires is reported as not run
            rubrics_dir: Folder with rubric files
        """
        self.store = store or RunStore()
        self.limits = limits or CostLimits()
        self.provider = provider
        self.rubrics_dir = rubrics_dir

    async def verify(self, run_dir: Path, scenario: Scenario) -> RunVerification:
        """
        Check a saved run and save the results.

        Writes verification.json. When the judge runs, also writes judge_detailed.md
        and appends the judge call to cost.json. Re-verifying a run makes a new
        judge call and records it too.

        Raises:
            ExpectationsError: If the scenario's expectations file is missing or invalid
        """
        trace = self.store.load_trace(run_dir)
        recorded = self.store.load_cost(run_dir)
        text = trace.captures.get(INTERPRETATION)
        expectations = self._load_expectations(scenario)
        rules = expectations.interpretation if expectations else None

        judge_check, verdict, new_calls = await self._judge(scenario, expectations, text)

        budget = scenario.validation.cost_budget_usd
        cost = CostReport.from_calls(scenario.id, [*recorded.calls, *new_calls], budget)

        budgets = [scenario.validation.performance_budget_sec]
        if expectations is not None and expectations.performance is not None:
            budgets.append(expectations.performance.total_e2e_max_sec)
        defined = [value for value in budgets if value is not None]

        checks = [
            self._schema(expectations, text),
            self._compliance(scenario, rules, text),
            check_cost(cost, budget, self.limits),
            check_performance(trace, min(defined) if defined else None),
            judge_check,
        ]
        unverified = unverified_sections(expectations) if expectations else []
        if (
            expectations is not None
            and expectations.llm_judge is not None
            and not scenario.validation.llm_judge
        ):
            unverified.append("llm_judge: the scenario does not request the judge")

        verification = RunVerification(
            run_id=run_dir.name,
            scenario_id=scenario.id,
            expectations_file=scenario.validation.expectations,
            status=combine_status(checks, unverified),
            checks=checks,
            unverified=unverified,
            judge=verdict,
        )

        self.store.save_cost(run_dir, cost)
        if verdict is not None:
            report = render_judge_report(verdict, run_dir.name)
            (run_dir / JUDGE_REPORT_FILE).write_text(report, encoding="utf-8")
        (run_dir / VERIFICATION_FILE).write_text(
            verification.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return verification

    @staticmethod
    def _load_expectations(scenario: Scenario) -> Expectations | None:
        if not scenario.validation.expectations:
            return None
        return load_expectations(scenario.validation.expectations)

    async def _judge(
        self,
        scenario: Scenario,
        expectations: Expectations | None,
        text: str | None,
    ) -> tuple[CheckResult, JudgeVerdict | None, list[LLMCall]]:
        """Run the judge if the scenario asks for it. Every precondition is checked before any spend."""
        if not scenario.validation.llm_judge:
            skipped = CheckResult(
                name="llm_judge",
                status="skipped",
                messages=["not requested by the scenario"],
            )
            return skipped, None, []

        if expectations is None or expectations.llm_judge is None:
            return _failed("llm_judge", "expectations file has no llm_judge section"), None, []

        if self.provider is None:
            not_run = CheckResult(
                name="llm_judge",
                status="warn",
                messages=["required by the scenario, but no LLM provider is configured"],
            )
            return not_run, None, []

        if expectations.document_summary is None:
            return _failed("llm_judge", "the judge needs document_summary in the expectations file"), None, []

        if text is None:
            return _failed("llm_judge", "no step captured the interpretation"), None, []

        rubric_id = expectations.llm_judge.rubric
        path = find_rubric(rubric_id, self.rubrics_dir)
        if path is None:
            return _failed("llm_judge", f"rubric not found: {rubric_id} in {self.rubrics_dir}"), None, []

        try:
            rubric = load_rubric(path)
        except RubricError as e:
            return _failed("llm_judge", f"invalid rubric: {e}"), None, []

        try:
            verdict = await LLMJudge(self.provider).evaluate(
                rubric,
                expectations.document_summary,
                text,
            )
        except JudgeEvaluationError as e:
            return _failed("llm_judge", f"judge failed: {e}"), None, []

        call = LLMCall(
            purpose="judge",
            model=verdict.model_used,
            tokens_in=verdict.tokens_in,
            tokens_out=verdict.tokens_out,
            cost_usd=verdict.cost_usd,
            duration_sec=verdict.duration_sec,
        )
        return self._judge_check(verdict), verdict, [call]

    @staticmethod
    def _judge_check(verdict: JudgeVerdict) -> CheckResult:
        status = "fail" if not verdict.passed else ("warn" if verdict.warnings else "pass")
        by_id = {dimension.id: dimension for dimension in verdict.dimensions}

        messages = [
            f"weighted score {verdict.weighted_score:.2f} against threshold {verdict.threshold:.1f}"
        ]
        for dimension_id in verdict.failed_critical:
            dimension = by_id[dimension_id]
            messages.append(
                f"critical dimension below minimum: {dimension.name} "
                f"{dimension.score:g} < {dimension.min_score:g}"
            )
        messages.extend(verdict.warnings)

        return CheckResult(
            name="llm_judge",
            status=status,
            messages=messages,
            details={
                "weighted_score": round(verdict.weighted_score, 4),
                "threshold": verdict.threshold,
                "scores": {dimension.id: dimension.score for dimension in verdict.dimensions},
                "model": verdict.model_used,
                "cost_usd": verdict.cost_usd,
            },
        )

    @staticmethod
    def _schema(expectations: Expectations | None, text: str | None) -> CheckResult:
        if expectations is None or expectations.interpretation is None:
            return CheckResult(
                name="schema",
                status="skipped",
                messages=["no interpretation section in expectations"],
            )
        if text is None:
            return _failed("schema", "no step captured the interpretation")
        return check_interpretation(text, expectations.interpretation)

    @staticmethod
    def _compliance(scenario: Scenario, rules, text: str | None) -> CheckResult:
        if not scenario.validation.compliance:
            return CheckResult(
                name="compliance",
                status="skipped",
                messages=["not requested by the scenario"],
            )
        if text is None:
            return _failed("compliance", "no step captured the interpretation")
        return check_compliance(
            text,
            disclaimer_pattern=rules.disclaimer_pattern if rules else None,
            extra_forbidden=rules.must_not_contain_phrases if rules else None,
        )
