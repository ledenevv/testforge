"""Run duration against the time budget, with a per-step breakdown from the trace."""

from testforge.scenarios.models import ExecutionTrace
from testforge.validation.models import CheckResult


def check_performance(trace: ExecutionTrace, budget_sec: float | None) -> CheckResult:
    """
    Compare the total run duration with the time budget.

    Args:
        trace: Trace of the run
        budget_sec: Time budget in seconds, or None when no budget applies

    Returns:
        CheckResult named 'performance'. Skipped when there is no budget.
    """
    steps = [
        {"index": s.index, "action": s.action.value, "duration_sec": round(s.duration_sec, 3)}
        for s in trace.steps
    ]
    total = round(trace.duration_sec, 3)
    details = {"total_sec": total, "budget_sec": budget_sec, "steps": steps}

    if budget_sec is None:
        return CheckResult(
            name="performance",
            status="skipped",
            messages=["no time budget set"],
            details=details,
        )

    messages: list[str] = []
    slowest = max(trace.steps, key=lambda s: s.duration_sec, default=None)
    if slowest is not None:
        messages.append(
            f"slowest step: #{slowest.index + 1} {slowest.action.value}, {slowest.duration_sec:.1f}s"
        )

    if total > budget_sec:
        status = "fail"
        messages.insert(0, f"total {total:.1f}s exceeds budget {budget_sec:.1f}s")
    else:
        status = "pass"
        messages.insert(0, f"total {total:.1f}s within budget {budget_sec:.1f}s")

    return CheckResult(name="performance", status=status, messages=messages, details=details)
