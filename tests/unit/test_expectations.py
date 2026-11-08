"""Unit tests for expectations files and the interpretation section check (M9b-3)."""

import pytest

from testforge.validation.schema import (
    ExpectationsError,
    InterpretationExpectations,
    check_interpretation,
    load_expectations,
    unverified_sections,
)

PLAN_FORMAT = """\
document_id: lab_report_001
fixture_file: lab_report_001_biochem_normal.pdf

vision_extraction:
  schema: LabExtractionSchema
  required_fields: [tests, source_lab, lab_date]

loinc_normalization:
  expected_mappings:
    "АЛТ": "1742-6"

interpretation:
  must_contain_sections:
    - "Резюме"
    - "Ключевые моменты"
  must_not_contain_phrases:
    - "назначаю"
  disclaimer_pattern: "Это информационный разбор.*не заменяет консультацию врача"

cost_budget:
  total_max: 0.20

performance:
  total_e2e_max_sec: 120
  interpretation_duration_max_sec: 60
"""


def _write(tmp_path, text):
    path = tmp_path / "expectations.yml"
    path.write_text(text, encoding="utf-8")
    return path


class TestLoading:
    def test_plan_format_file_loads(self, tmp_path):
        expectations = load_expectations(_write(tmp_path, PLAN_FORMAT))

        assert expectations.document_id == "lab_report_001"
        assert expectations.interpretation.must_contain_sections == ["Резюме", "Ключевые моменты"]
        assert expectations.performance.total_e2e_max_sec == 120

    def test_unknown_top_level_section_is_rejected(self, tmp_path):
        path = _write(tmp_path, "document_id: d\ninterpretaton:\n  must_contain_sections: []\n")

        with pytest.raises(ExpectationsError, match="interpretaton"):
            load_expectations(path)

    def test_unknown_key_inside_interpretation_is_rejected(self, tmp_path):
        path = _write(
            tmp_path,
            "document_id: d\ninterpretation:\n  must_contian_sections: [Резюме]\n",
        )

        with pytest.raises(ExpectationsError, match="must_contian_sections"):
            load_expectations(path)

    def test_unknown_key_inside_performance_is_rejected(self, tmp_path):
        path = _write(tmp_path, "document_id: d\nperformance:\n  total_e2e_max_secs: 60\n")

        with pytest.raises(ExpectationsError, match="total_e2e_max_secs"):
            load_expectations(path)

    def test_invalid_disclaimer_pattern_is_rejected(self, tmp_path):
        path = _write(
            tmp_path,
            'document_id: d\ninterpretation:\n  disclaimer_pattern: "(unclosed"\n',
        )

        with pytest.raises(ExpectationsError, match="disclaimer_pattern"):
            load_expectations(path)

    @pytest.mark.parametrize("value", ["0", "-5"])
    def test_performance_limits_must_be_positive(self, tmp_path, value):
        path = _write(tmp_path, f"document_id: d\nperformance:\n  total_e2e_max_sec: {value}\n")

        with pytest.raises(ExpectationsError):
            load_expectations(path)

    def test_malformed_yaml_is_an_expectations_error(self, tmp_path):
        with pytest.raises(ExpectationsError, match="invalid YAML"):
            load_expectations(_write(tmp_path, "document_id: [unclosed"))

    def test_top_level_list_is_an_expectations_error(self, tmp_path):
        with pytest.raises(ExpectationsError, match="mapping"):
            load_expectations(_write(tmp_path, "- just\n- a list\n"))

    def test_missing_file_is_an_expectations_error(self, tmp_path):
        with pytest.raises(ExpectationsError, match="cannot read"):
            load_expectations(tmp_path / "absent.yml")


class TestUnverifiedSections:
    def test_plan_format_sections_are_reported_with_reasons(self, tmp_path):
        notes = unverified_sections(load_expectations(_write(tmp_path, PLAN_FORMAT)))

        assert any(note.startswith("vision_extraction:") for note in notes)
        assert any(note.startswith("loinc_normalization:") for note in notes)
        assert any(note.startswith("cost_budget:") for note in notes)
        assert any(note.startswith("performance.interpretation_duration_max_sec:") for note in notes)

    def test_fully_checkable_file_has_nothing_unverified(self, tmp_path):
        path = _write(
            tmp_path,
            "document_id: d\ninterpretation:\n  must_contain_sections: [Резюме]\n"
            "performance:\n  total_e2e_max_sec: 120\n",
        )

        assert unverified_sections(load_expectations(path)) == []

    def test_schema_name_is_accepted_and_reported(self, tmp_path):
        path = _write(
            tmp_path,
            "document_id: d\ninterpretation:\n  schema: InterpretationResponse\n",
        )

        expectations = load_expectations(path)

        assert expectations.interpretation.schema_name == "InterpretationResponse"
        assert unverified_sections(expectations) == ["interpretation.schema: no schema registry yet"]


class TestInterpretationSections:
    TEXT = "📊 **Резюме**\n\n**Ключевые моменты:**\n- АЛТ: 25 Ед/л\n\n**Что обсудить с врачом:**"

    def test_all_required_sections_present_passes(self):
        result = check_interpretation(
            self.TEXT,
            InterpretationExpectations(must_contain_sections=["Резюме", "Ключевые моменты"]),
        )

        assert result.name == "schema"
        assert result.status == "pass"

    def test_match_ignores_case(self):
        result = check_interpretation(
            self.TEXT,
            InterpretationExpectations(must_contain_sections=["ключевые моменты"]),
        )

        assert result.status == "pass"

    def test_missing_section_fails_and_names_it(self):
        result = check_interpretation(
            self.TEXT,
            InterpretationExpectations(must_contain_sections=["Резюме", "Противопоказания"]),
        )

        assert result.status == "fail"
        assert result.details["missing"] == ["Противопоказания"]
        assert "'Противопоказания'" in result.messages[0]

    def test_no_required_sections_passes(self):
        result = check_interpretation(self.TEXT, InterpretationExpectations())

        assert result.status == "pass"
