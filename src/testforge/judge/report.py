"""Markdown report for one judge verdict: judge_detailed.md (M9b-4)."""

from testforge.judge.models import JudgeVerdict


def render_judge_report(verdict: JudgeVerdict, run_id: str) -> str:
    outcome = "PASS" if verdict.passed else "FAIL"
    lines = [
        f"# Judge report: {verdict.rubric_id} (v{verdict.rubric_version})",
        "",
        f"Run: {run_id}",
        f"Model: {verdict.model_used}",
        "",
        f"**Overall: {verdict.weighted_score:.2f}/10 — {outcome} (threshold {verdict.threshold:.1f})**",
        "",
        f"Cost: ${verdict.cost_usd:.4f} ({verdict.tokens_in} in / {verdict.tokens_out} out tokens)",
    ]

    if verdict.failed_critical:
        lines += ["", "Critical dimensions below minimum: " + ", ".join(verdict.failed_critical)]

    lines += [
        "",
        "| Dimension | Score | Minimum | Weight | Critical | Result |",
        "|---|---|---|---|---|---|",
    ]
    for dimension in verdict.dimensions:
        result = "below minimum" if dimension.below_minimum else "ok"
        critical = "yes" if dimension.critical else ""
        lines.append(
            f"| {dimension.name} | {dimension.score:.1f} | {dimension.min_score:.1f} "
            f"| {dimension.weight:.2f} | {critical} | {result} |"
        )

    lines += ["", "## Reasoning", ""]
    for dimension in verdict.dimensions:
        lines += [f"### {dimension.name}: {dimension.score:.1f}/10", "", dimension.reasoning, ""]

    lines += ["## Overall assessment", "", verdict.overall_assessment, ""]

    if verdict.warnings:
        lines += ["## Warnings", ""] + [f"- {warning}" for warning in verdict.warnings] + [""]

    return "\n".join(lines)
