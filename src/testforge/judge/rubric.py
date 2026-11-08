"""Rubrics: the weighted dimensions a bot interpretation is scored on (M9b-4)."""

from pathlib import Path

import yaml
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

RUBRICS_DIR = "fixtures/rubrics"
WEIGHT_TOLERANCE = 0.001

# Sandboxed and strict, like the scenario loader: the template ships in the rubric
# file, and a mistyped variable must fail instead of rendering as empty text.
_ENV = SandboxedEnvironment(undefined=StrictUndefined)


class RubricError(Exception):
    """Raised when a rubric cannot be found, read, or is invalid."""

    pass


class Dimension(BaseModel):
    """One scored dimension of a rubric."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=r"^[a-z][a-z_]*$",
        description="Machine name, used as the key in the judge's JSON reply",
    )
    name: str = Field(min_length=1, description="Name shown in reports")
    description: str = Field(min_length=1, description="What the judge should check")
    weight: float = Field(gt=0, le=1, description="Share of the overall score")
    min_score: float = Field(ge=0, le=10, description="Lowest acceptable score")
    critical: bool = Field(
        default=False,
        description="If true, a score below min_score fails the run",
    )


class Rubric(BaseModel):
    """Weighted dimensions and the rule that turns their scores into pass or fail."""

    model_config = ConfigDict(extra="forbid")

    rubric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", description="Rubric id, also its file name")
    version: str = Field(default="1.0", description="Rubric version, recorded in every verdict")
    overall_pass_threshold: float = Field(
        ge=0,
        le=10,
        description="Minimum weighted score to pass",
    )
    dimensions: list[Dimension] = Field(min_length=1)
    prompt_template: str = Field(min_length=1, description="Jinja2 template for the user prompt")

    @field_validator("prompt_template")
    @classmethod
    def template_must_compile(cls, value: str) -> str:
        try:
            _ENV.from_string(value)
        except TemplateError as e:
            raise ValueError(f"prompt_template does not compile: {e}") from e
        return value

    @model_validator(mode="after")
    def dimensions_must_be_consistent(self) -> "Rubric":
        ids = [dimension.id for dimension in self.dimensions]
        if len(set(ids)) != len(ids):
            raise ValueError("dimension ids must be unique")
        total = sum(dimension.weight for dimension in self.dimensions)
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError(f"dimension weights must sum to 1.0, got {total:.3f}")
        return self


def load_rubric(path: str | Path) -> Rubric:
    """
    Load and validate a rubric YAML file.

    Raises:
        RubricError: If the file is missing or unreadable, is not a mapping,
            or fails validation (weights, ids, template)
    """
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise RubricError(f"cannot read {path}: {e}") from e
    except yaml.YAMLError as e:
        raise RubricError(f"invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict):
        raise RubricError(f"rubric must be a mapping: {path}")

    try:
        return Rubric.model_validate(raw)
    except ValidationError as e:
        raise RubricError(f"invalid rubric {path}: {e}") from e


def find_rubric(rubric_id: str, rubrics_dir: str | Path = RUBRICS_DIR) -> Path | None:
    """Path of the rubric file for an id (.yml or .yaml), or None if there is none."""
    for suffix in (".yml", ".yaml"):
        candidate = Path(rubrics_dir) / f"{rubric_id}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def render_user_prompt(rubric: Rubric, document_summary: str, bot_interpretation: str) -> str:
    """
    Fill the rubric's template with the document and the interpretation.

    The texts are inserted as values. They are never parsed as template source,
    so braces or Jinja syntax inside them cannot change the prompt.

    Raises:
        jinja2.TemplateError: If the template uses a variable the renderer does not provide
    """
    return _ENV.from_string(rubric.prompt_template).render(
        document_summary=document_summary,
        bot_interpretation=bot_interpretation,
        dimensions=[
            {
                "id": dimension.id,
                "name": dimension.name,
                "description": dimension.description,
                "weight": dimension.weight,
                "min_score": dimension.min_score,
            }
            for dimension in rubric.dimensions
        ],
    )
