"""LLM-as-Judge evaluator."""

import json
import re
from typing import Any

from testforge.judge.models import JudgeCriteria, JudgeVerdict
from testforge.judge.prompts import SYSTEM_PROMPT, build_judge_prompt
from testforge.providers.base import LLMProvider


class JudgeEvaluationError(Exception):
    """Raised when judge evaluation fails."""

    pass


class LLMJudge:
    """
    LLM-as-Judge evaluator.

    Uses LLM to evaluate quality of bot responses.
    """

    def __init__(
        self,
        provider: LLMProvider,
        criteria: JudgeCriteria | None = None,
        passing_threshold: float = 7.0,
    ):
        """
        Initialize LLM judge.

        Args:
            provider: LLM provider for evaluation
            criteria: Evaluation criteria (defaults to all enabled)
            passing_threshold: Minimum overall score to pass (0-10)
        """
        self.provider = provider
        self.criteria = criteria or JudgeCriteria()
        self.passing_threshold = passing_threshold

    async def evaluate(
        self,
        user_query: str,
        bot_response: str,
        context: str | None = None,
    ) -> JudgeVerdict:
        """
        Evaluate bot response.

        Args:
            user_query: User's original query
            bot_response: Bot's response to evaluate
            context: Optional context (e.g., lab report data)

        Returns:
            JudgeVerdict with scores and reasoning

        Raises:
            JudgeEvaluationError: If evaluation fails
        """
        # Build enabled criteria list
        enabled_criteria = []
        if self.criteria.correctness:
            enabled_criteria.append("correctness")
        if self.criteria.helpfulness:
            enabled_criteria.append("helpfulness")
        if self.criteria.safety:
            enabled_criteria.append("safety")
        if self.criteria.language_quality:
            enabled_criteria.append("language_quality")
        if self.criteria.relevance:
            enabled_criteria.append("relevance")

        # Build prompt
        user_prompt = build_judge_prompt(
            user_query=user_query,
            bot_response=bot_response,
            context=context,
            enabled_criteria=enabled_criteria,
        )

        # Combine system + user prompt
        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

        # Call LLM
        try:
            response = await self.provider.complete(
                prompt=full_prompt,
                temperature=0.3,  # Lower temperature for consistency
            )
        except Exception as e:
            raise JudgeEvaluationError(f"LLM call failed: {e}") from e

        # Parse JSON response
        try:
            scores = self._parse_llm_response(response.text)
        except Exception as e:
            raise JudgeEvaluationError(f"Failed to parse LLM response: {e}") from e

        # Extract scores based on enabled criteria
        correctness_score = scores.get("correctness_score") if self.criteria.correctness else None
        helpfulness_score = scores.get("helpfulness_score") if self.criteria.helpfulness else None
        safety_score = scores.get("safety_score") if self.criteria.safety else None
        language_quality_score = scores.get("language_quality_score") if self.criteria.language_quality else None
        relevance_score = scores.get("relevance_score") if self.criteria.relevance else None

        # Calculate overall score (average of enabled criteria)
        enabled_scores = []
        if correctness_score is not None:
            enabled_scores.append(correctness_score)
        if helpfulness_score is not None:
            enabled_scores.append(helpfulness_score)
        if safety_score is not None:
            enabled_scores.append(safety_score)
        if language_quality_score is not None:
            enabled_scores.append(language_quality_score)
        if relevance_score is not None:
            enabled_scores.append(relevance_score)

        if not enabled_scores:
            raise JudgeEvaluationError("No criteria enabled for evaluation")

        overall_score = sum(enabled_scores) / len(enabled_scores)

        # Determine pass/fail
        passed = overall_score >= self.passing_threshold

        # Build verdict
        verdict = JudgeVerdict(
            passed=passed,
            correctness_score=correctness_score,
            helpfulness_score=helpfulness_score,
            safety_score=safety_score,
            language_quality_score=language_quality_score,
            relevance_score=relevance_score,
            overall_score=overall_score,
            reasoning=scores.get("reasoning", "No reasoning provided"),
            evaluation_cost_usd=response.cost_usd,
            evaluation_tokens=response.tokens_in + response.tokens_out,
            model_used=response.model,
        )

        return verdict

    def _parse_llm_response(self, text: str) -> dict[str, Any]:
        """
        Parse LLM response JSON.

        Args:
            text: LLM response text

        Returns:
            Parsed scores dict

        Raises:
            ValueError: If response is not valid JSON
        """
        # Try to extract JSON from response
        # LLM might wrap JSON in markdown code blocks
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            # Extract content between ``` blocks
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
            if match:
                text = match.group(1)

        # Parse JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}") from e

        # Validate required fields
        if "reasoning" not in data:
            raise ValueError("Response missing 'reasoning' field")

        return data
