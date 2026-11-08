"""Judge evaluation models."""

from typing import Literal

from pydantic import BaseModel, Field


class JudgeCriteria(BaseModel):
    """Criteria for LLM judge evaluation."""

    correctness: bool = Field(
        default=True,
        description="Evaluate factual correctness",
    )
    helpfulness: bool = Field(
        default=True,
        description="Evaluate helpfulness to user",
    )
    safety: bool = Field(
        default=True,
        description="Evaluate safety and appropriateness",
    )
    language_quality: bool = Field(
        default=True,
        description="Evaluate language quality (grammar, clarity)",
    )
    relevance: bool = Field(
        default=True,
        description="Evaluate relevance to user query",
    )


class JudgeVerdict(BaseModel):
    """LLM judge evaluation verdict."""

    passed: bool = Field(description="Whether response passes evaluation")
    
    # Scores (0-10 scale)
    correctness_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Factual correctness score (0-10)",
    )
    helpfulness_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Helpfulness score (0-10)",
    )
    safety_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Safety score (0-10)",
    )
    language_quality_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Language quality score (0-10)",
    )
    relevance_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Relevance score (0-10)",
    )
    
    overall_score: float = Field(
        ge=0,
        le=10,
        description="Overall score (average of enabled criteria)",
    )
    
    # Reasoning
    reasoning: str = Field(description="Judge's reasoning for the verdict")
    
    # Metadata
    evaluation_cost_usd: float = Field(
        ge=0,
        description="Cost of LLM evaluation in USD",
    )
    evaluation_tokens: int = Field(
        ge=0,
        description="Total tokens used for evaluation",
    )
    model_used: str = Field(description="LLM model used for judging")
