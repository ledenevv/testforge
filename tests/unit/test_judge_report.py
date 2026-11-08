"""Unit tests for the judge's markdown report, judge_detailed.md (M9b-4)."""

from testforge.judge import DimensionScore, JudgeVerdict, render_judge_report


def _dim(dim_id, name, weight, min_score, critical, score, reasoning="Обосновано."):
    return DimensionScore(
        id=dim_id,
        name=name,
        weight=weight,
        min_score=min_score,
        critical=critical,
        score=score,
        reasoning=reasoning,
    )


def _verdict(*, passed=True, dimensions=None, failed_critical=(), warnings=()):
    return JudgeVerdict(
        rubric_id="interpretation_quality_v1",
        rubric_version="1.0",
        passed=passed,
        weighted_score=8.67,
        threshold=7.5,
        dimensions=dimensions
        or [
            _dim("clarity", "Ясность", 0.25, 7.0, False, 8.2),
            _dim("medical_appropriateness", "Медицинская корректность", 0.40, 8.0, True, 8.8),
            _dim("russian_grammar", "Качество русского языка", 0.20, 7.0, False, 8.0),
            _dim("disclaimer_compliance", "Соответствие дисклеймеру", 0.15, 9.0, True, 10.0),
        ],
        failed_critical=list(failed_critical),
        warnings=list(warnings),
        overall_assessment="Разбор понятный и корректный.",
        model_used="claude-sonnet-4",
        tokens_in=5000,
        tokens_out=800,
        cost_usd=0.0230,
        duration_sec=4.1,
    )


class TestJudgeReport:
    def test_header_and_overall_line(self):
        report = render_judge_report(_verdict(), "run-20261109-100000")

        assert report.startswith("# Judge report: interpretation_quality_v1 (v1.0)")
        assert "Run: run-20261109-100000" in report
        assert "Model: claude-sonnet-4" in report
        assert "**Overall: 8.67/10 — PASS (threshold 7.5)**" in report

    def test_cost_line_has_tokens_and_dollars(self):
        report = render_judge_report(_verdict(), "run-1")

        assert "Cost: $0.0230 (5000 in / 800 out tokens)" in report

    def test_table_marks_critical_dimensions(self):
        report = render_judge_report(_verdict(), "run-1")

        assert "| Медицинская корректность | 8.8 | 8.0 | 0.40 | yes | ok |" in report
        assert "| Ясность | 8.2 | 7.0 | 0.25 |  | ok |" in report

    def test_reasoning_is_given_for_every_dimension(self):
        report = render_judge_report(_verdict(), "run-1")

        for name in ["Ясность", "Медицинская корректность", "Качество русского языка"]:
            assert f"### {name}:" in report
        assert "## Overall assessment" in report
        assert "Разбор понятный и корректный." in report

    def test_failed_report_names_critical_dimensions(self):
        verdict = _verdict(
            passed=False,
            failed_critical=["medical_appropriateness"],
            dimensions=[
                _dim("medical_appropriateness", "Медицинская корректность", 0.40, 8.0, True, 7.9),
            ],
        )

        report = render_judge_report(verdict, "run-1")

        assert "**Overall: 8.67/10 — FAIL (threshold 7.5)**" in report
        assert "Critical dimensions below minimum: medical_appropriateness" in report
        assert "| below minimum |" in report

    def test_warnings_section_only_when_there_are_warnings(self):
        assert "## Warnings" not in render_judge_report(_verdict(), "run-1")

        report = render_judge_report(_verdict(warnings=["clarity: 6 is below the minimum 7"]), "run-1")

        assert "## Warnings" in report
        assert "- clarity: 6 is below the minimum 7" in report
