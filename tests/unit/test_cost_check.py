"""Unit tests for the cost check against scenario and config budgets (M9b-3)."""

from testforge.config import CostLimits
from testforge.reporting import CostReport, LLMCall
from testforge.validation.cost import check_cost

LIMITS = CostLimits(per_scenario_max_usd=0.20, per_run_max_usd=0.50, alert_threshold_usd=0.40)
LOW_ALERT = CostLimits(per_scenario_max_usd=0.20, per_run_max_usd=0.50, alert_threshold_usd=0.10)


def _report(total):
    calls = []
    if total:
        calls = [
            LLMCall(
                purpose="judge",
                model="claude-sonnet-4",
                tokens_in=1,
                tokens_out=1,
                cost_usd=total,
                duration_sec=0.1,
            )
        ]
    return CostReport.from_calls("s", calls)


class TestCostCheck:
    def test_spend_within_budget_passes(self):
        result = check_cost(_report(0.05), scenario_budget_usd=0.20, limits=LIMITS)

        assert result.name == "cost"
        assert result.status == "pass"
        assert result.details["limit_usd"] == 0.20

    def test_no_spend_passes(self):
        assert check_cost(_report(0), scenario_budget_usd=None, limits=LIMITS).status == "pass"

    def test_spend_above_alert_threshold_warns(self):
        result = check_cost(_report(0.15), scenario_budget_usd=None, limits=LOW_ALERT)

        assert result.status == "warn"
        assert any("alert threshold" in message for message in result.messages)

    def test_spend_above_scenario_budget_fails(self):
        result = check_cost(_report(0.08), scenario_budget_usd=0.05, limits=LIMITS)

        assert result.status == "fail"
        assert result.details["limit_usd"] == 0.05

    def test_spend_above_config_cap_fails_without_scenario_budget(self):
        result = check_cost(_report(0.25), scenario_budget_usd=None, limits=LIMITS)

        assert result.status == "fail"
        assert result.details["limit_usd"] == 0.20

    def test_scenario_budget_above_cap_warns_and_cap_applies(self):
        result = check_cost(_report(0.05), scenario_budget_usd=0.50, limits=LIMITS)

        assert result.status == "warn"
        assert result.details["limit_usd"] == 0.20
        assert any("above the config cap" in message for message in result.messages)

    def test_scenario_budget_above_cap_still_fails_over_the_cap(self):
        result = check_cost(_report(0.25), scenario_budget_usd=0.50, limits=LIMITS)

        assert result.status == "fail"

    def test_details_record_the_numbers(self):
        result = check_cost(_report(0.05), scenario_budget_usd=0.20, limits=LIMITS)

        assert result.details["total_usd"] == 0.05
        assert result.details["config_cap_usd"] == 0.20
        assert result.details["budget_used"] == 0.25
