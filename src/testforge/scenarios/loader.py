"""Scenario loader from YAML files."""

import os
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template
from pydantic import ValidationError

from testforge.scenarios.models import Scenario


class ScenarioLoadError(Exception):
    """Raised when scenario fails to load."""

    pass


def _substitute_env_vars(data: Any) -> Any:
    """
    Recursively substitute environment variables in data.

    Supports ${VAR_NAME} syntax, same as config loader.
    """
    if isinstance(data, str):
        # Simple ${VAR} substitution
        if "${" in data:
            for key, value in os.environ.items():
                data = data.replace(f"${{{key}}}", value)
        return data
    elif isinstance(data, dict):
        return {k: _substitute_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_substitute_env_vars(item) for item in data]
    else:
        return data


def _render_template(text: str, variables: dict[str, Any]) -> str:
    """
    Render Jinja2 template with variables.

    Args:
        text: Template text
        variables: Template variables

    Returns:
        Rendered text
    """
    if "{{" not in text and "{%" not in text:
        # No template syntax, return as-is
        return text

    template = Template(text)
    return template.render(**variables)


def _render_scenario_templates(data: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively render Jinja2 templates in scenario data.

    Args:
        data: Scenario data dict
        variables: Template variables

    Returns:
        Rendered data
    """
    if isinstance(data, str):
        return _render_template(data, variables)
    elif isinstance(data, dict):
        return {k: _render_scenario_templates(v, variables) for k, v in data.items()}
    elif isinstance(data, list):
        return [_render_scenario_templates(item, variables) for item in data]
    else:
        return data


def load_scenario(path: str | Path, variables: dict[str, Any] | None = None) -> Scenario:
    """
    Load scenario from YAML file.

    Args:
        path: Path to YAML scenario file
        variables: Optional variables for template rendering (overrides scenario.variables)

    Returns:
        Parsed Scenario object

    Raises:
        ScenarioLoadError: If file doesn't exist, YAML is invalid, or validation fails
    """
    path = Path(path)

    # Check file exists
    if not path.exists():
        raise ScenarioLoadError(f"Scenario file not found: {path}")

    # Read YAML
    try:
        with open(path, encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ScenarioLoadError(f"Invalid YAML in {path}: {e}")

    if not raw_data:
        raise ScenarioLoadError(f"Empty scenario file: {path}")

    # Extract scenario data (handle both root-level and "scenario:" wrapper)
    if "scenario" in raw_data:
        scenario_data = raw_data["scenario"]
    else:
        scenario_data = raw_data

    # Substitute environment variables
    scenario_data = _substitute_env_vars(scenario_data)

    # Merge variables (file variables + passed variables)
    file_variables = scenario_data.get("variables", {})
    if variables:
        file_variables.update(variables)

    # Render Jinja2 templates
    if file_variables:
        scenario_data = _render_scenario_templates(scenario_data, file_variables)

    # Parse into Pydantic model
    try:
        scenario = Scenario(**scenario_data)
    except ValidationError as e:
        raise ScenarioLoadError(f"Validation error in {path}: {e}")

    return scenario


def load_scenarios_from_directory(
    directory: str | Path,
    pattern: str = "*.yaml",
    variables: dict[str, Any] | None = None,
) -> list[Scenario]:
    """
    Load all scenarios from a directory.

    Args:
        directory: Directory containing scenario files
        pattern: Glob pattern for scenario files (default: *.yaml)
        variables: Optional variables for template rendering

    Returns:
        List of loaded scenarios

    Raises:
        ScenarioLoadError: If directory doesn't exist or any scenario fails to load
    """
    directory = Path(directory)

    if not directory.exists():
        raise ScenarioLoadError(f"Scenario directory not found: {directory}")

    if not directory.is_dir():
        raise ScenarioLoadError(f"Not a directory: {directory}")

    scenarios = []
    errors = []

    for scenario_file in sorted(directory.glob(pattern)):
        try:
            scenario = load_scenario(scenario_file, variables=variables)
            scenarios.append(scenario)
        except ScenarioLoadError as e:
            errors.append(f"{scenario_file.name}: {e}")

    if errors:
        raise ScenarioLoadError(
            f"Failed to load {len(errors)} scenario(s):\n" + "\n".join(errors)
        )

    return scenarios
