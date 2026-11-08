"""Results of scoring one interpretation against a rubric."""

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    """The judge's score for one dimension, with the rubric's rules copied in."""

    id: str
    name: str
    weight: float
    min_score: float
    critical: bool
    score: float = Field(ge=0, le=10)
    reasoning: str

    @property
    def below_minimum(self) -> bool:
        return self.score < self.min_score


class JudgeVerdict(BaseModel):
    """Verdict on one interpretation: per-dimension scores and the pass rule's result."""

    rubric_id: str
    rubric_version: str
    passed: bool = Field(description="Weighted score at or above threshold and no critical failure")
    weighted_score: float = Field(ge=0, le=10)
    threshold: float = Field(ge=0, le=10)
    dimensions: list[DimensionScore]
    failed_critical: list[str] = Field(
        default_factory=list,
        description="Critical dimensions scored below their minimum",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-critical dimensions below their minimum. These do not fail the run",
    )
    overall_assessment: str
    model_used: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: float = Field(ge=0, description="Cost of the judge call")
    duration_sec: float = Field(ge=0)
