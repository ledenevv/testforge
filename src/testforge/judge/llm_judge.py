"""LLM-as-Judge evaluator."""

import json
import math
import re
from typing import Any

from testforge.judge.models import JudgeCriteria, JudgeVerdict
from testforge.judge.prompts import CRITERIA, build_judge_prompt, build_system_prompt
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

        Raises:
            ValueError: If passing_threshold is outside 0-10
        """
        if not 0 <= passing_threshold <= 10:
            raise ValueError(f"passing_threshold must be within 0-10, got {passing_threshold}")

        self.provider = provider
        self.criteria = criteria or JudgeCriteria()
        self.passing_threshold = passing_threshold

    def _enabled_criteria(self) -> list[str]:
        """Names of the criteria that are switched on, in canonical order."""
        return [name for name in CRITERIA if getattr(self.criteria, name)]

    async def evaluate(
        self,
        user_query: str,
        bot_response: str,
        context: str | None = None,
    ) -> JudgeVerdict:
        """
        Evaluate bot response.

        Every enabled criterion must be scored by the judge model; a missing,
        non-numeric or out-of-range score fails the evaluation rather than being
        skipped, so a response can never pass on fewer criteria than configured.

        Args:
            user_query: User's original query
            bot_response: Bot's response to evaluate
            context: Optional context (e.g., lab report data)

        Returns:
            JudgeVerdict with scores and reasoning

        Raises:
            JudgeEvaluationError: If evaluation fails
        """
        enabled = self._enabled_criteria()
        if not enabled:
            # Checked before the call so no paid request is made for nothing
            raise JudgeEvaluationError("No criteria enabled for evaluation")

        user_prompt = build_judge_prompt(
            user_query=user_query,
            bot_response=bot_response,
            context=context,
            enabled_criteria=enabled,
        )
        full_prompt = f"{build_system_prompt(enabled)}\n\n{user_prompt}"

        try:
            response = await self.provider.complete(
                prompt=full_prompt,
                temperature=0.3,  # Lower temperature for consistency
            )
        except Exception as e:
            raise JudgeEvaluationError(f"LLM call failed: {e}") from e

        try:
            data = self._parse_llm_response(response.text, enabled)
        except Exception as e:
            raise JudgeEvaluationError(f"Failed to parse LLM response: {e}") from e

        scores = {name: data[f"{name}_score"] if name in enabled else None for name in CRITERIA}
        overall_score = sum(scores[name] for name in enabled) / len(enabled)

        return JudgeVerdict(
            passed=overall_score >= self.passing_threshold,
            correctness_score=scores["correctness"],
            helpfulness_score=scores["helpfulness"],
            safety_score=scores["safety"],
            language_quality_score=scores["language_quality"],
            relevance_score=scores["relevance"],
            overall_score=overall_score,
            reasoning=data["reasoning"],
            evaluation_cost_usd=response.cost_usd,
            evaluation_tokens=response.tokens_in + response.tokens_out,
            model_used=response.model,
        )

    @staticmethod
    def _extract_json(text: str) -> Any:
        """
        Parse the first JSON value found in the model output.

        Tries the whole text first, then a fenced code block anywhere in it,
        then the outermost {...} span, so prose around the JSON is tolerated.

        Raises:
            ValueError: If no candidate parses as JSON
        """
        text = text.strip()
        candidates = [text]

        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            candidates.append(fenced.group(1))

        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])

        first_error: json.JSONDecodeError | None = None
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                first_error = first_error or e

        raise ValueError(f"Invalid JSON response: {first_error}")

    def _parse_llm_response(self, text: str, enabled: list[str]) -> dict[str, Any]:
        """
        Parse and validate the judge model's JSON output.

        Args:
            text: LLM response text
            enabled: Criteria whose scores must be present

        Returns:
            Parsed dict with validated scores and reasoning

        Raises:
            ValueError: If the response is not a valid verdict
        """
        data = self._extract_json(text)

        if not isinstance(data, dict):
            raise ValueError("Response JSON must be an object")

        if "reasoning" not in data:
            raise ValueError("Response missing 'reasoning' field")
        if not isinstance(data["reasoning"], str):
            raise ValueError("'reasoning' must be a string")

        for name in enabled:
            key = f"{name}_score"
            if key not in data:
                raise ValueError(f"Response missing score for enabled criterion '{name}'")

            value = data[key]
            # bool is an int subclass: reject it so `true` is not scored as 1
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 10
            ):
                raise ValueError(f"'{key}' must be a number between 0 and 10, got {value!r}")

        return data
