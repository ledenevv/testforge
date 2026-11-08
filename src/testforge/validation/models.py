"""Result types shared by the post-run checks."""

from typing import Any, Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["pass", "warn", "fail", "skipped"]


class CheckResult(BaseModel):
    """Outcome of one check on a finished run."""

    name: str = Field(description="Check name: schema, compliance, cost, performance, llm_judge")
    status: CheckStatus = Field(description="pass, warn, fail, or skipped if the check did not apply")
    messages: list[str] = Field(default_factory=list, description="What was found, one line each")
    details: dict[str, Any] = Field(default_factory=dict, description="Numbers and per-item data")


def combine_status(checks: list[CheckResult], unverified: list[str] | None = None) -> CheckStatus:
    """
    Overall verdict for a run.

    fail if any check failed; warn if any check warned or part of the expectations
    could not be verified; pass if at least one check ran and passed; skipped if
    nothing ran.
    """
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses or unverified:
        return "warn"
    if "pass" in statuses:
        return "pass"
    return "skipped"
