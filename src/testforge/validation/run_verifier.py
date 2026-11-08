"""Checks a finished run against its scenario and expectations, and saves verification.json."""

from pathlib import Path

from pydantic import BaseModel, Field

from testforge.config import CostLimits
from testforge.reporting.run_store import RunStore
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


class RunVerifier:
    """Runs every check a scenario asks for against one run folder."""

    def __init__(self, store: RunStore | None = None, limits: CostLimits | None = None):
        self.store = store or RunStore()
        self.limits = limits or CostLimits()

    def verify(self, run_dir: Path, scenario: Scenario) -> RunVerification:
        """
        Check a saved run.

        Raises:
            ExpectationsError: If the scenario's expectations file is missing or invalid
        """
        trace = self.store.load_trace(run_dir)
        cost = self.store.load_cost(run_dir)
        text = trace.captures.get(INTERPRETATION)

        expectations = self._load_expectations(scenario)
        interpretation_rules = expectations.interpretation if expectations else None

        budgets = [scenario.validation.performance_budget_sec]
        if expectations is not None and expectations.performance is not None:
            budgets.append(expectations.performance.total_e2e_max_sec)
        defined = [budget for budget in budgets if budget is not None]

        checks = [
            self._schema(expectations, text),
            self._compliance(scenario, interpretation_rules, text),
            check_cost(cost, scenario.validation.cost_budget_usd, self.limits),
            check_performance(trace, min(defined) if defined else None),
            self._judge(scenario),
        ]
        unverified = unverified_sections(expectations) if expectations else []

        return RunVerification(
            run_id=run_dir.name,
            scenario_id=scenario.id,
            expectations_file=scenario.validation.expectations,
            status=combine_status(checks, unverified),
            checks=checks,
            unverified=unverified,
        )

    def write(self, run_dir: Path, verification: RunVerification) -> Path:
        path = run_dir / VERIFICATION_FILE
        path.write_text(verification.model_dump_json(indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _load_expectations(scenario: Scenario) -> Expectations | None:
        if not scenario.validation.expectations:
            return None
        return load_expectations(scenario.validation.expectations)

    @staticmethod
    def _schema(expectations: Expectations | None, text: str | None) -> CheckResult:
        if expectations is None or expectations.interpretation is None:
            return CheckResult(
                name="schema",
                status="skipped",
                messages=["no interpretation section in expectations"],
            )
        if text is None:
            return CheckResult(
                name="schema",
                status="fail",
                messages=["no step captured the interpretation"],
            )
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
            return CheckResult(
                name="compliance",
                status="fail",
                messages=["no step captured the interpretation"],
            )
        return check_compliance(
            text,
            disclaimer_pattern=rules.disclaimer_pattern if rules else None,
            extra_forbidden=rules.must_not_contain_phrases if rules else None,
        )

    @staticmethod
    def _judge(scenario: Scenario) -> CheckResult:
        if not scenario.validation.llm_judge:
            return CheckResult(
                name="llm_judge",
                status="skipped",
                messages=["not requested by the scenario"],
            )
        return CheckResult(
            name="llm_judge",
            status="warn",
            messages=["required by the scenario, but the judge is not wired in yet (M9b-4)"],
        )
