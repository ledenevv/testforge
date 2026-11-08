"""Expectations files: what a document's interpretation must contain (plan section 4.2)."""

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from testforge.validation.models import CheckResult


class ExpectationsError(Exception):
    """Raised when an expectations file cannot be read or is invalid."""

    pass


class InterpretationExpectations(BaseModel):
    """What the bot's interpretation must contain. Checked through the Bot API."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: str | None = Field(
        default=None,
        alias="schema",
        description="Name of the interpretation schema. Accepted, not checked yet",
    )
    must_contain_sections: list[str] = Field(
        default_factory=list,
        description="Section headings that must appear (case-insensitive)",
    )
    must_not_contain_phrases: list[str] = Field(
        default_factory=list,
        description="Phrases forbidden for this document, on top of the default list",
    )
    disclaimer_pattern: str | None = Field(
        default=None,
        description="Regex the disclaimer must match. Default: the plan's pattern",
    )

    @field_validator("disclaimer_pattern")
    @classmethod
    def pattern_must_compile(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as e:
                raise ValueError(f"invalid disclaimer_pattern {value!r}: {e}") from e
        return value


class PerformanceExpectations(BaseModel):
    """Time limits for a document. Only the end-to-end limit can be checked through the Bot API."""

    model_config = ConfigDict(extra="forbid")

    total_e2e_max_sec: float | None = Field(default=None, gt=0)
    upload_to_extraction_start_max_sec: float | None = Field(default=None, gt=0)
    extraction_duration_max_sec: float | None = Field(default=None, gt=0)
    interpretation_duration_max_sec: float | None = Field(default=None, gt=0)


class LlmJudgeExpectations(BaseModel):
    """Which rubric the judge scores this document against. Weights live in the rubric file."""

    model_config = ConfigDict(extra="forbid")

    rubric: str = Field(min_length=1, description="Rubric id, looked up in fixtures/rubrics")


class Expectations(BaseModel):
    """
    Expected results for one document.

    Sections the Bot API cannot show (vision, LOINC, pipeline cost, per-stage time)
    are accepted, so plan-format files load, and are reported as unverified.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    fixture_file: str | None = None
    document_summary: str | None = Field(
        default=None,
        description="What the document really says (values, dates, source). The judge checks the interpretation against it",
    )
    vision_extraction: dict[str, Any] | None = None
    loinc_normalization: dict[str, Any] | None = None
    interpretation: InterpretationExpectations | None = None
    llm_judge: LlmJudgeExpectations | None = None
    cost_budget: dict[str, Any] | None = None
    performance: PerformanceExpectations | None = None


def load_expectations(path: str | Path) -> Expectations:
    """
    Load and validate an expectations YAML file.

    Raises:
        ExpectationsError: If the file is missing or unreadable, is not a mapping,
            or fails validation (for example an unknown section name)
    """
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise ExpectationsError(f"cannot read {path}: {e}") from e
    except yaml.YAMLError as e:
        raise ExpectationsError(f"invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict):
        raise ExpectationsError(f"expectations must be a mapping: {path}")

    try:
        return Expectations.model_validate(raw)
    except ValidationError as e:
        raise ExpectationsError(f"invalid expectations {path}: {e}") from e


def unverified_sections(expectations: Expectations) -> list[str]:
    """Parts of the file that this version cannot check, each with the reason."""
    notes: list[str] = []
    if expectations.vision_extraction is not None:
        notes.append("vision_extraction: not visible through the Bot API")
    if expectations.loinc_normalization is not None:
        notes.append("loinc_normalization: not visible through the Bot API")
    if expectations.cost_budget is not None:
        notes.append("cost_budget: bot pipeline cost is not measured")

    interpretation = expectations.interpretation
    if interpretation is not None and interpretation.schema_name is not None:
        notes.append("interpretation.schema: no schema registry yet")

    performance = expectations.performance
    if performance is not None:
        for field_name in (
            "upload_to_extraction_start_max_sec",
            "extraction_duration_max_sec",
            "interpretation_duration_max_sec",
        ):
            if getattr(performance, field_name) is not None:
                notes.append(
                    f"performance.{field_name}: per-stage limit, not visible through the Bot API"
                )
    return notes


def check_interpretation(text: str, expectations: InterpretationExpectations) -> CheckResult:
    """Check that every required section heading appears in the interpretation."""
    lowered = text.lower()
    missing = [s for s in expectations.must_contain_sections if s.lower() not in lowered]
    return CheckResult(
        name="schema",
        status="fail" if missing else "pass",
        messages=[f"required section missing: {s!r}" for s in missing]
        or ["all required sections present"],
        details={"required": expectations.must_contain_sections, "missing": missing},
    )
