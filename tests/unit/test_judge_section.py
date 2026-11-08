"""Expectations: the llm_judge section and document_summary (M9b-4)."""

import pytest

from testforge.validation.schema import ExpectationsError, load_expectations


def _write(tmp_path, text):
    path = tmp_path / "expectations.yml"
    path.write_text(text, encoding="utf-8")
    return path


class TestJudgeSection:
    def test_rubric_name_is_the_only_judge_setting(self, tmp_path):
        expectations = load_expectations(
            _write(tmp_path, "document_id: d\nllm_judge:\n  rubric: interpretation_quality_v1\n")
        )

        assert expectations.llm_judge.rubric == "interpretation_quality_v1"

    def test_model_is_rejected_because_the_provider_sets_it(self, tmp_path):
        with pytest.raises(ExpectationsError, match="model"):
            load_expectations(
                _write(tmp_path, "document_id: d\nllm_judge:\n  rubric: r\n  model: claude-sonnet-4\n")
            )

    def test_weights_in_expectations_are_rejected(self, tmp_path):
        with pytest.raises(ExpectationsError, match="dimensions"):
            load_expectations(
                _write(tmp_path, "document_id: d\nllm_judge:\n  rubric: r\n  dimensions: []\n")
            )

    def test_empty_rubric_name_is_rejected(self, tmp_path):
        with pytest.raises(ExpectationsError):
            load_expectations(_write(tmp_path, 'document_id: d\nllm_judge:\n  rubric: ""\n'))

    def test_judge_section_is_optional(self, tmp_path):
        assert load_expectations(_write(tmp_path, "document_id: d\n")).llm_judge is None


class TestDocumentSummary:
    def test_summary_is_loaded(self, tmp_path):
        expectations = load_expectations(
            _write(tmp_path, 'document_id: d\ndocument_summary: "АЛТ 25 Ед/л."\n')
        )

        assert expectations.document_summary == "АЛТ 25 Ед/л."

    def test_summary_is_optional(self, tmp_path):
        assert load_expectations(_write(tmp_path, "document_id: d\n")).document_summary is None
