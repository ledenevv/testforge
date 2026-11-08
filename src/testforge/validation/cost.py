"""TestForge's own LLM spend against the budgets. The bot's pipeline cost is not measured."""

from testforge.config import CostLimits
from testforge.reporting.run_store import CostReport
from testforge.validation.models import CheckResult


def check_cost(
    report: CostReport,
    scenario_budget_usd: float | None,
    limits: CostLimits,
) -> CheckResult:
    """
    Compare TestForge's spend for a run with its budgets.

    The limit is the lower of the config's per-scenario cap and the scenario's own
    budget. Above the limit: fail. Above the config's alert threshold: warn. A
    scenario budget above the config cap is reported as a warning, and the cap applies.

    Args:
        report: Spend recorded for the run (cost.json)
        scenario_budget_usd: Budget from the scenario's validation block, if set
        limits: Cost limits from the config

    Returns:
        CheckResult named 'cost'
    """
    cap = limits.per_scenario_max_usd
    limit = cap
    cap_warning = scenario_budget_usd is not None and scenario_budget_usd > cap
    messages: list[str] = []

    if cap_warning:
        messages.append(
            f"scenario budget ${scenario_budget_usd:.4f} is above the config cap "
            f"${cap:.4f}; the cap applies"
        )
    if scenario_budget_usd is not None:
        limit = min(cap, scenario_budget_usd)

    total = report.total_cost_usd
    if total > limit:
        status = "fail"
        messages.append(f"spend ${total:.4f} exceeds the limit ${limit:.4f}")
    elif total > limits.alert_threshold_usd:
        status = "warn"
        messages.append(
            f"spend ${total:.4f} is above the alert threshold ${limits.alert_threshold_usd:.4f}"
        )
    else:
        status = "pass"
        messages.append(f"spend ${total:.4f} within the limit ${limit:.4f}")

    if cap_warning and status == "pass":
        status = "warn"

    return CheckResult(
        name="cost",
        status=status,
        messages=messages,
        details={
            "total_usd": total,
            "limit_usd": limit,
            "config_cap_usd": cap,
            "scenario_budget_usd": scenario_budget_usd,
            "alert_threshold_usd": limits.alert_threshold_usd,
            "budget_used": total / limit,
        },
    )
