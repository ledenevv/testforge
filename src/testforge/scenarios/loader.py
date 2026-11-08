"""Scenario loader from YAML files."""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment
from pydantic import ValidationError

from testforge.scenarios.models import Scenario

_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Sandboxed + strict: env values are substituted before rendering and must not
# be able to execute code, and a mistyped variable must fail instead of
# silently rendering as an empty string.
_JINJA_ENV = SandboxedEnvironment(undefined=StrictUndefined)


class ScenarioLoadError(Exception):
    """Raised when scenario fails to load."""

    pass


def _substitute_env_vars(data: Any) -> Any:
    """
    Recursively substitute environment variables in data.

    Supports ${VAR_NAME} syntax with the same rules as the config loader:
    unset variables become an empty string.
    """
    if isinstance(data, str):
        return _ENV_VAR_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), data)
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

    try:
        return _JINJA_ENV.from_string(text).render(**variables)
    except TemplateError as e:
        raise ScenarioLoadError(f"Template error in {text[:60]!r}: {e}") from e


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
        raise ScenarioLoadError(f"Invalid YAML in {path}: {e}") from e
    except (OSError, UnicodeDecodeError) as e:
        raise ScenarioLoadError(f"Cannot read {path}: {e}") from e

    if not raw_data:
        raise ScenarioLoadError(f"Empty scenario file: {path}")

    if not isinstance(raw_data, dict):
        raise ScenarioLoadError(f"Scenario file must contain a mapping: {path}")

    # Extract scenario data (handle both root-level and "scenario:" wrapper)
    scenario_data = raw_data.get("scenario", raw_data)
    if not isinstance(scenario_data, dict):
        raise ScenarioLoadError(f"'scenario' must be a mapping in {path}")

    # Merge variables (file variables + passed variables)
    file_variables = scenario_data.get("variables") or {}
    if not isinstance(file_variables, dict):
        raise ScenarioLoadError(f"'variables' must be a mapping in {path}")
    merged_variables = {**file_variables, **(variables or {})}
    if merged_variables:
        scenario_data["variables"] = merged_variables

    # Render Jinja2 templates first, then substitute environment variables, so
    # environment values are never interpreted as templates.
    try:
        scenario_data = _render_scenario_templates(scenario_data, merged_variables)
    except ScenarioLoadError as e:
        raise ScenarioLoadError(f"{path}: {e}") from e
    scenario_data = _substitute_env_vars(scenario_data)

    # Parse into Pydantic model
    try:
        scenario = Scenario(**scenario_data)
    except ValidationError as e:
        raise ScenarioLoadError(f"Validation error in {path}: {e}") from e

    return scenario


SCENARIO_PATTERNS = ("*.yml", "*.yaml")


def load_scenarios_from_directory(
    directory: str | Path,
    pattern: str | None = None,
    variables: dict[str, Any] | None = None,
) -> list[Scenario]:
    """
    Load all scenarios from a directory.

    Args:
        directory: Directory containing scenario files
        pattern: Glob pattern for scenario files. Defaults to both *.yml and *.yaml.
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

    patterns = [pattern] if pattern else list(SCENARIO_PATTERNS)
    scenario_files = sorted({f for p in patterns for f in directory.glob(p)})

    for scenario_file in scenario_files:
        try:
            scenario = load_scenario(scenario_file, variables=variables)
            scenarios.append(scenario)
        except ScenarioLoadError as e:
            errors.append(f"{scenario_file.name}: {e}")

    if errors:
        raise ScenarioLoadError(
            f"Failed to load {len(errors)} scenario(s):\n" + "\n".join(errors)
        )

    seen: set[str] = set()
    for scenario in scenarios:
        if scenario.id in seen:
            raise ScenarioLoadError(f"Duplicate scenario id '{scenario.id}' in {directory}")
        seen.add(scenario.id)

    return scenarios


def validate_scenario_files(scenario: Scenario, base_dir: str | Path | None = None) -> list[str]:
    """
    Check that the files a scenario refers to exist.

    Checked: every step's document_path and validation.expectations. Relative
    paths are resolved against base_dir. The default is the current directory,
    which is also where the executor opens documents, so the check and the run
    look at the same files.

    Loading does not run this check; call it separately before a run.

    Args:
        scenario: Scenario to check
        base_dir: Directory that relative paths are resolved against

    Returns:
        One message per missing file. An empty list means everything is present.
    """
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    problems: list[str] = []

    for index, step in enumerate(scenario.steps, start=1):
        if step.document_path and not (root / step.document_path).is_file():
            problems.append(f"step {index}: document not found: {step.document_path}")

    expectations = scenario.validation.expectations
    if expectations and not (root / expectations).is_file():
        problems.append(f"validation.expectations not found: {expectations}")

    return problems
