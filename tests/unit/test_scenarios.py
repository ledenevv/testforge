"""Unit tests for scenario loading and validation."""

from pathlib import Path

import pytest

from testforge.scenarios import (
    ActionType,
    ExpectCondition,
    Scenario,
    ScenarioLoadError,
    Step,
    load_scenario,
    load_scenarios_from_directory,
)


class TestScenarioModels:
    """Test Scenario Pydantic models."""

    def test_valid_scenario(self):
        """Valid scenario should validate."""
        scenario = Scenario(
            id="test_scenario",
            description="Test scenario",
            steps=[
                Step(
                    action=ActionType.SEND_MESSAGE,
                    text="/start",
                    expect=ExpectCondition(contains="hello"),
                )
            ],
        )
        assert scenario.id == "test_scenario"
        assert len(scenario.steps) == 1
        assert scenario.mode == "mock"  # default

    def test_scenario_id_validation(self):
        """Scenario ID must be lowercase with underscores."""
        # Valid IDs
        Scenario(id="valid_id", description="test", steps=[Step(action=ActionType.WAIT)])
        Scenario(id="test123", description="test", steps=[Step(action=ActionType.WAIT)])

        # Invalid IDs (should raise)
        with pytest.raises(ValueError):
            Scenario(
                id="Invalid-ID",  # Uppercase and dash
                description="test",
                steps=[Step(action=ActionType.WAIT)],
            )

    def test_scenario_requires_steps(self):
        """Scenario must have at least one step."""
        with pytest.raises(ValueError):
            Scenario(
                id="empty",
                description="Empty scenario",
                steps=[],  # Empty!
            )

    def test_step_with_expect(self):
        """Step can have expect condition."""
        step = Step(
            action=ActionType.SEND_MESSAGE,
            text="/start",
            expect=ExpectCondition(
                contains="hello",
                response_count=1,
            ),
        )
        assert step.expect.contains == "hello"
        assert step.expect.response_count == 1

    def test_step_critical_default_true(self):
        """Step critical flag should default to True."""
        step = Step(action=ActionType.WAIT)
        assert step.critical is True

    def test_expect_condition_all_optional(self):
        """All fields in ExpectCondition should be optional."""
        expect = ExpectCondition()
        assert expect.contains is None
        assert expect.not_contains is None
        assert expect.response_count is None


class TestScenarioLoader:
    """Test scenario loading from YAML files."""

    @pytest.fixture
    def fixtures_dir(self):
        """Path to fixtures/scenarios directory."""
        return Path("fixtures/scenarios")

    def test_load_profile_setup_scenario(self, fixtures_dir):
        """Load profile_setup.yaml scenario."""
        scenario = load_scenario(fixtures_dir / "profile_setup.yaml")

        assert scenario.id == "profile_setup"
        assert "profile" in scenario.tags
        assert scenario.mode == "mock"
        assert len(scenario.steps) == 6  # 6 steps in profile flow

        # Check first step
        first_step = scenario.steps[0]
        assert first_step.action == ActionType.SEND_MESSAGE
        assert first_step.text == "/consent"
        assert first_step.expect.contains == "пол"

    def test_load_document_upload_scenario(self, fixtures_dir):
        """Load document_upload.yaml scenario."""
        scenario = load_scenario(fixtures_dir / "document_upload.yaml")

        assert scenario.id == "document_upload"
        assert "document" in scenario.tags
        assert len(scenario.steps) == 4

        # Check document upload step
        upload_step = scenario.steps[0]
        assert upload_step.action == ActionType.SEND_DOCUMENT
        assert "sample_lab_report.pdf" in upload_step.document_path

    def test_load_smoke_test_scenario(self, fixtures_dir):
        """Load smoke_test.yaml scenario."""
        scenario = load_scenario(fixtures_dir / "smoke_test.yaml")

        assert scenario.id == "smoke_test"
        assert "smoke" in scenario.tags
        assert scenario.timeout_sec == 15
        assert len(scenario.steps) == 3

    def test_load_multi_step_scenario(self, fixtures_dir):
        """Load multi_step.yaml scenario."""
        scenario = load_scenario(fixtures_dir / "multi_step.yaml")

        assert scenario.id == "multi_step"
        assert "e2e" in scenario.tags
        assert len(scenario.steps) == 11  # Full flow
        assert scenario.timeout_sec == 90

    def test_load_nonexistent_file(self):
        """Loading nonexistent file should raise ScenarioLoadError."""
        with pytest.raises(ScenarioLoadError, match="not found"):
            load_scenario("nonexistent_scenario.yaml")

    def test_load_invalid_yaml(self, tmp_path):
        """Invalid YAML should raise ScenarioLoadError."""
        invalid_file = tmp_path / "invalid.yaml"
        invalid_file.write_text("{ invalid yaml content [")

        with pytest.raises(ScenarioLoadError, match="Invalid YAML"):
            load_scenario(invalid_file)

    def test_load_empty_yaml(self, tmp_path):
        """Empty YAML file should raise ScenarioLoadError."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")

        with pytest.raises(ScenarioLoadError, match="Empty"):
            load_scenario(empty_file)

    def test_load_scenario_missing_required_fields(self, tmp_path):
        """Scenario missing required fields should fail validation."""
        invalid = tmp_path / "invalid_scenario.yaml"
        invalid.write_text(
            """
scenario:
  id: missing_fields
  # Missing description and steps!
"""
        )

        with pytest.raises(ScenarioLoadError, match="Validation error"):
            load_scenario(invalid)

    def test_template_rendering(self, fixtures_dir):
        """Jinja2 templates should be rendered."""
        scenario = load_scenario(fixtures_dir / "multi_step.yaml")

        # Variables defined in YAML
        assert scenario.variables["user_sex"] == "f"

        # Templates should be rendered in steps
        sex_step = scenario.steps[2]  # Third step uses {{ user_sex }}
        assert sex_step.text == "f"  # Template rendered

    def test_template_override_with_passed_variables(self, fixtures_dir):
        """Passed variables should override file variables."""
        scenario = load_scenario(
            fixtures_dir / "multi_step.yaml",
            variables={"user_sex": "m", "user_year": "2000"},
        )

        # Passed variables should override
        sex_step = scenario.steps[2]
        assert sex_step.text == "m"  # Overridden

        year_step = scenario.steps[3]
        assert year_step.text == "2000"  # Overridden

    def test_load_scenarios_from_directory(self, fixtures_dir):
        """Load all scenarios from directory."""
        scenarios = load_scenarios_from_directory(fixtures_dir)

        ids = sorted(s.id for s in scenarios)
        assert ids == [
            "document_upload",
            "env_var_test",
            "multi_step",
            "profile_setup",
            "smoke_test",
        ]

    def test_load_scenarios_from_nonexistent_directory(self):
        """Loading from nonexistent directory should raise error."""
        with pytest.raises(ScenarioLoadError, match="not found"):
            load_scenarios_from_directory("nonexistent_directory")

    def test_load_scenarios_with_pattern(self, fixtures_dir):
        """Load scenarios matching a pattern."""
        # Load only smoke tests
        scenarios = load_scenarios_from_directory(fixtures_dir, pattern="smoke*.yaml")

        assert len(scenarios) == 1
        assert scenarios[0].id == "smoke_test"

    def test_scenario_with_both_root_and_wrapper(self, tmp_path):
        """Scenario can be at root level or under 'scenario:' key."""
        # Root level
        root_file = tmp_path / "root.yaml"
        root_file.write_text(
            """
id: root_scenario
description: Root level
steps:
  - action: send_message
    text: test
"""
        )
        root_scenario = load_scenario(root_file)
        assert root_scenario.id == "root_scenario"

        # Wrapped
        wrapped_file = tmp_path / "wrapped.yaml"
        wrapped_file.write_text(
            """
scenario:
  id: wrapped_scenario
  description: Wrapped
  steps:
    - action: send_message
      text: test
"""
        )
        wrapped_scenario = load_scenario(wrapped_file)
        assert wrapped_scenario.id == "wrapped_scenario"


def _write_scenario(path, body: str):
    path.write_text(body, encoding="utf-8")
    return path


class TestScenarioStrictness:
    """Typos and invalid input must fail loudly, not silently change behavior."""

    def test_unknown_step_field_rejected(self):
        """A misspelled `expect` must not silently produce a step with no checks."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="expects"):
            Step(action=ActionType.SEND_MESSAGE, text="hi", expects={"contains": "x"})

    def test_unknown_expect_field_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ExpectCondition(contain="x")

    def test_unknown_scenario_field_rejected(self, tmp_path):
        path = _write_scenario(
            tmp_path / "typo.yaml",
            "id: typo\ndescription: d\ntimeout: 5\nsteps:\n  - action: wait\n    duration_sec: 1\n",
        )
        with pytest.raises(ScenarioLoadError, match="timeout"):
            load_scenario(path)

    def test_invalid_regex_rejected_at_load(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Invalid regex"):
            ExpectCondition(matches_regex="(unclosed")


class TestScenarioLoaderRobustness:
    """Loader edge cases."""

    @pytest.fixture
    def fixtures_dir(self):
        return Path("fixtures/scenarios")

    def test_env_vars_substituted(self, monkeypatch, fixtures_dir):
        monkeypatch.setenv("TEST_USER_NAME", "alice")
        monkeypatch.setenv("TEST_ENV", "ci")

        scenario = load_scenario(fixtures_dir / "env_var_test.yaml")

        assert scenario.variables["test_user_name"] == "alice"
        assert scenario.variables["test_message"] == "Hello from ci"

    def test_unset_env_var_becomes_empty_like_config_loader(self, monkeypatch, fixtures_dir):
        monkeypatch.delenv("TEST_USER_NAME", raising=False)
        monkeypatch.delenv("TEST_ENV", raising=False)

        scenario = load_scenario(fixtures_dir / "env_var_test.yaml")

        assert scenario.variables["test_user_name"] == ""
        assert scenario.variables["test_message"] == "Hello from "

    def test_mixed_case_env_var_substituted(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MyVar", "value")
        path = _write_scenario(
            tmp_path / "s.yaml",
            "id: s\ndescription: d\nsteps:\n  - action: send_message\n    text: '${MyVar}'\n",
        )
        assert load_scenario(path).steps[0].text == "value"

    def test_env_value_is_not_rendered_as_template(self, monkeypatch, tmp_path):
        """An env value containing Jinja syntax stays literal."""
        monkeypatch.setenv("SECRET", "{{ 7 * 7 }}")
        # A variables block is required here: it is what triggers template rendering
        path = _write_scenario(
            tmp_path / "s.yaml",
            "id: s\ndescription: d\nvariables:\n  unrelated: x\nsteps:\n"
            "  - action: send_message\n    text: '${SECRET}'\n",
        )
        assert load_scenario(path).steps[0].text == "{{ 7 * 7 }}"

    def test_undefined_template_variable_rejected(self, tmp_path):
        """A mistyped variable fails instead of rendering as an empty string."""
        path = _write_scenario(
            tmp_path / "s.yaml",
            "id: s\ndescription: d\nvariables:\n  name: bob\nsteps:\n"
            "  - action: send_message\n    text: '{{ nmae }}'\n",
        )
        with pytest.raises(ScenarioLoadError, match="nmae"):
            load_scenario(path)

    def test_undefined_template_variable_rejected_without_variables_block(self, tmp_path):
        path = _write_scenario(
            tmp_path / "s.yaml",
            "id: s\ndescription: d\nsteps:\n  - action: send_message\n    text: '{{ missing }}'\n",
        )
        with pytest.raises(ScenarioLoadError, match="missing"):
            load_scenario(path)

    def test_unsafe_template_expression_rejected(self, tmp_path):
        path = _write_scenario(
            tmp_path / "s.yaml",
            "id: s\ndescription: d\nsteps:\n  - action: send_message\n"
            "    text: \"{{ ''.__class__.__mro__ }}\"\n",
        )
        with pytest.raises(ScenarioLoadError):
            load_scenario(path)

    def test_passed_variables_are_kept_on_scenario(self, tmp_path):
        path = _write_scenario(
            tmp_path / "s.yaml",
            "id: s\ndescription: d\nsteps:\n  - action: send_message\n    text: '{{ greeting }}'\n",
        )
        scenario = load_scenario(path, variables={"greeting": "hello"})

        assert scenario.steps[0].text == "hello"
        assert scenario.variables == {"greeting": "hello"}

    def test_null_variables_block_tolerated(self, tmp_path):
        path = _write_scenario(
            tmp_path / "s.yaml",
            "id: s\ndescription: d\nvariables:\nsteps:\n  - action: send_message\n    text: hi\n",
        )
        assert load_scenario(path, variables={"a": "b"}).variables == {"a": "b"}

    @pytest.mark.parametrize(
        "body",
        ["- just\n- a list\n", "scenario: not-a-mapping\n", "variables: [1, 2]\nid: s\n"],
    )
    def test_wrong_shape_raises_load_error(self, tmp_path, body):
        path = _write_scenario(tmp_path / "bad.yaml", body)
        with pytest.raises(ScenarioLoadError):
            load_scenario(path)

    def test_directory_instead_of_file_raises_load_error(self, tmp_path):
        with pytest.raises(ScenarioLoadError, match="Cannot read"):
            load_scenario(tmp_path)

    def test_duplicate_ids_in_directory_rejected(self, tmp_path):
        body = "id: same\ndescription: d\nsteps:\n  - action: wait\n    duration_sec: 1\n"
        _write_scenario(tmp_path / "a.yaml", body)
        _write_scenario(tmp_path / "b.yaml", body)

        with pytest.raises(ScenarioLoadError, match="Duplicate scenario id 'same'"):
            load_scenarios_from_directory(tmp_path)


class TestScenarioResult:
    """Test ScenarioResult model."""

    def test_valid_result(self):
        """Valid result should validate."""
        from testforge.scenarios import ScenarioResult

        result = ScenarioResult(
            scenario_id="test",
            passed=True,
            duration_sec=5.5,
            steps_executed=3,
            steps_passed=3,
            steps_failed=0,
        )
        assert result.passed is True
        assert result.duration_sec == 5.5
        assert result.error is None

    def test_failed_result(self):
        """Failed result should include error details."""
        from testforge.scenarios import ScenarioResult

        result = ScenarioResult(
            scenario_id="test",
            passed=False,
            duration_sec=2.0,
            steps_executed=2,
            steps_passed=1,
            steps_failed=1,
            error="Expected text not found",
            failed_step_index=1,
        )
        assert result.passed is False
        assert result.error is not None
        assert result.failed_step_index == 1
