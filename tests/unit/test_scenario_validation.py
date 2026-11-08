"""Unit tests for the plan fields, capture rule and file checks of scenarios (M9b-1)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from testforge.scenarios import (
    ActionType,
    ExpectCondition,
    Scenario,
    ScenarioLoadError,
    Step,
    ValidationSpec,
    load_scenario,
    load_scenarios_from_directory,
    validate_scenario_files,
)


def _scenario(**overrides):
    data = {
        "id": "s",
        "description": "d",
        "steps": [{"action": "wait", "duration_sec": 1}],
    }
    data.update(overrides)
    return Scenario(**data)


class TestPlanFields:
    def test_existing_scenarios_stay_valid_with_defaults(self):
        scenario = _scenario()

        assert scenario.title is None
        assert scenario.priority == "P1"
        assert scenario.validation == ValidationSpec()

    def test_title_and_priority_accepted(self):
        scenario = _scenario(title="Загрузка анализа", priority="P0")

        assert scenario.title == "Загрузка анализа"
        assert scenario.priority == "P0"

    @pytest.mark.parametrize("priority", ["P3", "high", "p0"])
    def test_unknown_priority_rejected(self, priority):
        with pytest.raises(ValidationError):
            _scenario(priority=priority)

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            _scenario(title="")


class TestValidationBlock:
    def test_full_block_accepted(self):
        spec = ValidationSpec(
            expectations="fixtures/expectations/lab_report_001.yml",
            llm_judge=True,
            compliance=True,
            cost_budget_usd=0.20,
            performance_budget_sec=120,
        )

        assert spec.cost_budget_usd == 0.20
        assert spec.performance_budget_sec == 120

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("cost_budget_usd", 0),
            ("cost_budget_usd", -0.1),
            ("performance_budget_sec", 0),
            ("performance_budget_sec", -5),
        ],
    )
    def test_budgets_must_be_positive(self, field, value):
        with pytest.raises(ValidationError, match=field):
            ValidationSpec(**{field: value})

    def test_small_positive_budget_accepted(self):
        assert ValidationSpec(cost_budget_usd=0.001).cost_budget_usd == 0.001

    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError, match="expectation"):
            ValidationSpec.model_validate({"expectation": "x.yml"})

    def test_plan_example_key_schema_is_rejected(self):
        """The plan's first example used `schema:`; it is named `expectations` now."""
        with pytest.raises(ValidationError, match="schema"):
            ValidationSpec.model_validate({"schema": "x.yml"})

    def test_unknown_key_rejected_inside_scenario(self):
        with pytest.raises(ValidationError):
            _scenario(validation={"cost_budget": 0.2})

    def test_block_loads_from_yml_file(self, tmp_path):
        path = tmp_path / "s.yml"
        path.write_text(
            "id: s\n"
            "description: d\n"
            "title: Загрузка анализа\n"
            "priority: P0\n"
            "validation:\n"
            "  expectations: fixtures/expectations/lab_report_001.yml\n"
            "  llm_judge: true\n"
            "  compliance: true\n"
            "  cost_budget_usd: 0.2\n"
            "  performance_budget_sec: 120\n"
            "steps:\n"
            "  - action: wait\n"
            "    duration_sec: 1\n",
            encoding="utf-8",
        )

        scenario = load_scenario(path)

        assert scenario.priority == "P0"
        assert scenario.validation.llm_judge is True
        assert scenario.validation.cost_budget_usd == 0.2
        assert scenario.validation.expectations == "fixtures/expectations/lab_report_001.yml"


class TestCapture:
    def test_capture_defaults_to_none(self):
        assert Step(action=ActionType.WAIT, duration_sec=1).capture is None

    def test_capture_on_expect_response_accepted(self):
        step = Step(
            action=ActionType.EXPECT_RESPONSE,
            expect=ExpectCondition(contains="Резюме"),
            capture="interpretation",
        )

        assert step.capture == "interpretation"

    def test_capture_on_upload_with_expect_accepted(self):
        step = Step(
            action=ActionType.SEND_DOCUMENT,
            document_path="a.pdf",
            expect=ExpectCondition(response_count=1),
            capture="interpretation",
        )

        assert step.capture == "interpretation"

    def test_capture_on_send_without_expect_rejected(self):
        """Without an expectation the step never reads replies, so nothing would be captured."""
        with pytest.raises(ValidationError, match="capture"):
            Step(action=ActionType.SEND_MESSAGE, text="/start", capture="interpretation")

    @pytest.mark.parametrize(
        "step",
        [
            lambda: Step(action=ActionType.WAIT, duration_sec=1, capture="interpretation"),
            lambda: Step(action=ActionType.VERIFY_STATE, capture="interpretation"),
        ],
    )
    def test_capture_on_steps_without_replies_rejected(self, step):
        with pytest.raises(ValidationError, match="capture"):
            step()

    def test_unknown_capture_target_rejected(self):
        with pytest.raises(ValidationError):
            Step(
                action=ActionType.EXPECT_RESPONSE,
                expect=ExpectCondition(contains="x"),
                capture="response",
            )


class TestValidateScenarioFiles:
    @pytest.fixture
    def project(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "report.pdf").write_text("pdf", encoding="utf-8")
        (tmp_path / "expectations.yml").write_text("document_id: x\n", encoding="utf-8")
        return tmp_path

    @staticmethod
    def _upload(path):
        return Step(action=ActionType.SEND_DOCUMENT, document_path=path)

    def test_everything_present_has_no_problems(self, project):
        scenario = _scenario(
            steps=[self._upload("docs/report.pdf")],
            validation={"expectations": "expectations.yml"},
        )

        assert validate_scenario_files(scenario, base_dir=project) == []

    def test_missing_document_reported_with_step_number(self, project):
        scenario = _scenario(
            steps=[
                Step(action=ActionType.WAIT, duration_sec=1),
                self._upload("docs/missing.pdf"),
            ]
        )

        assert validate_scenario_files(scenario, base_dir=project) == [
            "step 2: document not found: docs/missing.pdf"
        ]

    def test_missing_expectations_reported(self, project):
        scenario = _scenario(validation={"expectations": "nope.yml"})

        assert validate_scenario_files(scenario, base_dir=project) == [
            "validation.expectations not found: nope.yml"
        ]

    def test_no_expectations_configured_is_not_a_problem(self, project):
        assert validate_scenario_files(_scenario(), base_dir=project) == []

    def test_directory_is_not_accepted_as_document(self, project):
        scenario = _scenario(steps=[self._upload("docs")])

        assert validate_scenario_files(scenario, base_dir=project) == [
            "step 1: document not found: docs"
        ]

    def test_absolute_path_is_used_as_is(self, project):
        absolute = str(project / "docs" / "report.pdf")
        scenario = _scenario(steps=[self._upload(absolute)])

        assert validate_scenario_files(scenario, base_dir=project / "does_not_matter") == []

    def test_defaults_to_current_directory(self, project, monkeypatch):
        monkeypatch.chdir(project)
        scenario = _scenario(steps=[self._upload("docs/report.pdf")])

        assert validate_scenario_files(scenario) == []

    def test_loading_does_not_check_files(self, tmp_path):
        """Loading behaves as before: a missing file is only reported by the explicit check."""
        path = tmp_path / "s.yml"
        path.write_text(
            "id: s\ndescription: d\nsteps:\n"
            "  - action: send_document\n    document_path: nowhere.pdf\n",
            encoding="utf-8",
        )

        assert load_scenario(path).steps[0].document_path == "nowhere.pdf"


class TestDirectoryLoading:
    @staticmethod
    def _write(path, scenario_id):
        path.write_text(
            f"id: {scenario_id}\ndescription: d\nsteps:\n  - action: wait\n    duration_sec: 1\n",
            encoding="utf-8",
        )

    def test_loads_both_yml_and_yaml(self, tmp_path):
        self._write(tmp_path / "a.yml", "from_yml")
        self._write(tmp_path / "b.yaml", "from_yaml")

        ids = sorted(s.id for s in load_scenarios_from_directory(tmp_path))

        assert ids == ["from_yaml", "from_yml"]

    def test_other_extensions_are_ignored(self, tmp_path):
        self._write(tmp_path / "a.yml", "kept")
        self._write(tmp_path / "notes.txt", "ignored")
        self._write(tmp_path / "data.json", "ignored")

        assert [s.id for s in load_scenarios_from_directory(tmp_path)] == ["kept"]

    def test_explicit_pattern_overrides_default(self, tmp_path):
        self._write(tmp_path / "a.yml", "kept_yml")
        self._write(tmp_path / "b.yaml", "skipped_yaml")

        ids = [s.id for s in load_scenarios_from_directory(tmp_path, pattern="*.yml")]

        assert ids == ["kept_yml"]

    def test_duplicate_id_across_extensions_rejected(self, tmp_path):
        self._write(tmp_path / "a.yml", "same")
        self._write(tmp_path / "a2.yaml", "same")

        with pytest.raises(ScenarioLoadError, match="Duplicate scenario id 'same'"):
            load_scenarios_from_directory(tmp_path)
