"""Unit tests for rubric files: weights, dimensions, template, lookup (M9b-4)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from testforge.judge import RubricError, find_rubric, load_rubric
from testforge.judge.rubric import Rubric

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "fixtures" / "rubrics" / "interpretation_quality_v1.yml"
TEMPLATE = "{{ bot_interpretation }}"


def _dims(*weights):
    names = ["alpha", "beta", "gamma", "delta"][: len(weights)]
    return [
        {"id": name, "name": name.title(), "description": "d", "weight": weight, "min_score": 7.0}
        for name, weight in zip(names, weights, strict=True)
    ]


def _rubric(**overrides):
    data = {
        "rubric_id": "test_rubric",
        "overall_pass_threshold": 7.5,
        "dimensions": _dims(0.5, 0.5),
        "prompt_template": TEMPLATE,
    }
    data.update(overrides)
    return data


class TestShippedRubric:
    def test_matches_the_plan_weights_minimums_and_threshold(self):
        rubric = load_rubric(SHIPPED)

        assert rubric.rubric_id == "interpretation_quality_v1"
        assert rubric.overall_pass_threshold == 7.5
        assert [
            (d.id, d.weight, d.min_score, d.critical) for d in rubric.dimensions
        ] == [
            ("clarity", 0.25, 7.0, False),
            ("medical_appropriateness", 0.40, 8.0, True),
            ("russian_grammar", 0.20, 7.0, False),
            ("disclaimer_compliance", 0.15, 9.0, True),
        ]

    def test_template_has_both_texts_in_their_tags(self):
        rubric = load_rubric(SHIPPED)

        assert "<document_summary>" in rubric.prompt_template
        assert "<bot_interpretation>" in rubric.prompt_template


class TestRubricValidation:
    def test_valid_rubric_is_accepted(self):
        assert Rubric.model_validate(_rubric()).rubric_id == "test_rubric"

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValidationError, match="sum to 1.0"):
            Rubric.model_validate(_rubric(dimensions=_dims(0.5, 0.4)))

    def test_weights_within_tolerance_are_accepted(self):
        Rubric.model_validate(_rubric(dimensions=_dims(0.333, 0.333, 0.334)))

    def test_weights_outside_tolerance_are_rejected(self):
        with pytest.raises(ValidationError, match="sum to 1.0"):
            Rubric.model_validate(_rubric(dimensions=_dims(0.33, 0.33, 0.33)))

    def test_duplicate_dimension_ids_are_rejected(self):
        dims = _dims(0.5, 0.5)
        dims[1]["id"] = "alpha"

        with pytest.raises(ValidationError, match="unique"):
            Rubric.model_validate(_rubric(dimensions=dims))

    def test_at_least_one_dimension_is_required(self):
        with pytest.raises(ValidationError):
            Rubric.model_validate(_rubric(dimensions=[]))

    def test_weight_must_be_positive(self):
        with pytest.raises(ValidationError):
            Rubric.model_validate(_rubric(dimensions=_dims(0.0, 1.0)))

    @pytest.mark.parametrize("bad_id", ["Clarity", "1st", "with-dash"])
    def test_dimension_id_must_be_a_plain_name(self, bad_id):
        dims = _dims(0.5, 0.5)
        dims[0]["id"] = bad_id

        with pytest.raises(ValidationError):
            Rubric.model_validate(_rubric(dimensions=dims))

    @pytest.mark.parametrize("field", ["min_score"])
    def test_minimum_must_be_within_zero_to_ten(self, field):
        dims = _dims(0.5, 0.5)
        dims[0][field] = 11

        with pytest.raises(ValidationError):
            Rubric.model_validate(_rubric(dimensions=dims))

    def test_threshold_must_be_within_zero_to_ten(self):
        with pytest.raises(ValidationError):
            Rubric.model_validate(_rubric(overall_pass_threshold=10.5))

    def test_unknown_key_is_rejected(self):
        with pytest.raises(ValidationError, match="model"):
            Rubric.model_validate(_rubric(model="claude-sonnet-4"))

    def test_template_must_compile(self):
        with pytest.raises(ValidationError, match="compile"):
            Rubric.model_validate(_rubric(prompt_template="{% for x in %}"))

    def test_template_is_required(self):
        data = _rubric()
        del data["prompt_template"]

        with pytest.raises(ValidationError):
            Rubric.model_validate(data)


class TestLoadingAndLookup:
    def test_missing_file_is_a_rubric_error(self, tmp_path):
        with pytest.raises(RubricError, match="cannot read"):
            load_rubric(tmp_path / "absent.yml")

    def test_malformed_yaml_is_a_rubric_error(self, tmp_path):
        path = tmp_path / "bad.yml"
        path.write_text("rubric_id: [unclosed", encoding="utf-8")

        with pytest.raises(RubricError, match="invalid YAML"):
            load_rubric(path)

    def test_top_level_list_is_a_rubric_error(self, tmp_path):
        path = tmp_path / "list.yml"
        path.write_text("- just\n- a list\n", encoding="utf-8")

        with pytest.raises(RubricError, match="mapping"):
            load_rubric(path)

    def test_find_rubric_by_id_in_the_rubrics_folder(self):
        assert find_rubric("interpretation_quality_v1", ROOT / "fixtures" / "rubrics") == SHIPPED

    def test_find_rubric_accepts_yaml_extension(self, tmp_path):
        (tmp_path / "other.yaml").write_text("x: 1\n", encoding="utf-8")

        assert find_rubric("other", tmp_path) == tmp_path / "other.yaml"

    def test_find_rubric_returns_none_when_missing(self, tmp_path):
        assert find_rubric("nope", tmp_path) is None
