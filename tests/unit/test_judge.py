"""Unit tests for LLM Judge."""

import pytest

from testforge.config import LLMConfig
from testforge.judge import JudgeCriteria, JudgeVerdict, LLMJudge
from testforge.judge.llm_judge import JudgeEvaluationError
from testforge.providers import MockProvider


def create_mock_provider(response_json: str) -> MockProvider:
    """Create mock provider with custom response."""
    config = LLMConfig(provider="mock", api_key="", model="mock-judge")
    return MockProvider(config, responses={"default": response_json})


class TestJudgeModels:
    """Test Judge models."""

    def test_judge_criteria_defaults(self):
        """JudgeCriteria should have all criteria enabled by default."""
        criteria = JudgeCriteria()
        assert criteria.correctness is True
        assert criteria.helpfulness is True
        assert criteria.safety is True
        assert criteria.language_quality is True
        assert criteria.relevance is True

    def test_judge_criteria_custom(self):
        """JudgeCriteria can disable specific criteria."""
        criteria = JudgeCriteria(
            correctness=True,
            helpfulness=False,
            safety=True,
            language_quality=False,
            relevance=True,
        )
        assert criteria.correctness is True
        assert criteria.helpfulness is False

    def test_judge_verdict_scores_optional(self):
        """JudgeVerdict scores can be None for disabled criteria."""
        verdict = JudgeVerdict(
            passed=True,
            correctness_score=8.5,
            helpfulness_score=None,  # Disabled
            safety_score=9.0,
            language_quality_score=None,  # Disabled
            relevance_score=8.0,
            overall_score=8.5,
            reasoning="Good response",
            evaluation_cost_usd=0.001,
            evaluation_tokens=500,
            model_used="test-model",
        )
        assert verdict.correctness_score == 8.5
        assert verdict.helpfulness_score is None

    def test_judge_verdict_score_validation(self):
        """JudgeVerdict scores must be in 0-10 range."""
        with pytest.raises(ValueError):
            JudgeVerdict(
                passed=True,
                correctness_score=11.0,  # Invalid!
                overall_score=8.0,
                reasoning="Test",
                evaluation_cost_usd=0.0,
                evaluation_tokens=100,
                model_used="test",
            )


class TestLLMJudge:
    """Test LLMJudge."""

    @pytest.mark.asyncio
    async def test_evaluate_success(self):
        """Evaluate should return verdict with scores."""
        mock_response = """{
            "correctness_score": 8.5,
            "helpfulness_score": 9.0,
            "safety_score": 9.5,
            "language_quality_score": 8.0,
            "relevance_score": 8.5,
            "reasoning": "The response is accurate and helpful."
        }"""
        
        provider = create_mock_provider(mock_response)
        judge = LLMJudge(provider=provider)

        verdict = await judge.evaluate(
            user_query="Что означают мои анализы?",
            bot_response="Ваши анализы в норме.",
        )

        assert verdict.passed is True
        assert verdict.correctness_score == 8.5
        assert verdict.helpfulness_score == 9.0
        assert verdict.overall_score > 0
        assert "accurate" in verdict.reasoning

    @pytest.mark.asyncio
    async def test_evaluate_with_context(self):
        """Evaluate should accept context."""
        mock_response = """{
            "correctness_score": 7.0,
            "helpfulness_score": 7.5,
            "safety_score": 8.0,
            "language_quality_score": 7.0,
            "relevance_score": 7.5,
            "reasoning": "Context helps evaluation."
        }"""
        
        provider = create_mock_provider(mock_response)
        judge = LLMJudge(provider=provider)

        verdict = await judge.evaluate(
            user_query="Analyze my results",
            bot_response="Your glucose is normal",
            context="Lab report: Glucose 5.0 mmol/L",
        )

        assert verdict.passed is True
        assert verdict.overall_score >= 7.0

    @pytest.mark.asyncio
    async def test_evaluate_failing_response(self):
        """Evaluate should fail low-quality responses."""
        mock_response = """{
            "correctness_score": 3.0,
            "helpfulness_score": 2.0,
            "safety_score": 4.0,
            "language_quality_score": 3.5,
            "relevance_score": 2.5,
            "reasoning": "Response is inaccurate and unhelpful."
        }"""
        
        provider = create_mock_provider(mock_response)
        judge = LLMJudge(provider=provider)

        verdict = await judge.evaluate(
            user_query="Test",
            bot_response="Bad response",
        )

        assert verdict.passed is False  # Overall score < 7.0 threshold
        assert verdict.overall_score < 7.0

    @pytest.mark.asyncio
    async def test_evaluate_custom_threshold(self):
        """Judge should support custom passing threshold."""
        mock_response = """{
            "correctness_score": 7.5,
            "helpfulness_score": 7.5,
            "safety_score": 7.5,
            "language_quality_score": 7.5,
            "relevance_score": 7.5,
            "reasoning": "Acceptable but not great."
        }"""
        
        provider = create_mock_provider(mock_response)
        judge = LLMJudge(provider=provider, passing_threshold=8.0)

        verdict = await judge.evaluate(
            user_query="Test",
            bot_response="Response",
        )

        # Overall = 7.5, threshold = 8.0 → fail
        assert verdict.passed is False
        assert verdict.overall_score == 7.5

    @pytest.mark.asyncio
    async def test_evaluate_selective_criteria(self):
        """Judge should evaluate only enabled criteria."""
        mock_response = """{
            "correctness_score": 8.0,
            "helpfulness_score": 5.0,
            "safety_score": 9.0,
            "language_quality_score": 3.0,
            "relevance_score": 4.0,
            "reasoning": "Only correctness and safety matter."
        }"""
        
        provider = create_mock_provider(mock_response)
        criteria = JudgeCriteria(
            correctness=True,
            helpfulness=False,
            safety=True,
            language_quality=False,
            relevance=False,
        )
        judge = LLMJudge(provider=provider, criteria=criteria)

        verdict = await judge.evaluate(
            user_query="Test",
            bot_response="Response",
        )

        # Only correctness and safety enabled
        assert verdict.correctness_score == 8.0
        assert verdict.helpfulness_score is None  # Disabled
        assert verdict.safety_score == 9.0
        assert verdict.language_quality_score is None  # Disabled
        assert verdict.relevance_score is None  # Disabled

        # Overall = (8.0 + 9.0) / 2 = 8.5
        assert verdict.overall_score == 8.5

    @pytest.mark.asyncio
    async def test_evaluate_cost_tracking(self):
        """Evaluate should track LLM cost."""
        mock_response = """{
            "correctness_score": 8.0,
            "helpfulness_score": 8.0,
            "safety_score": 8.0,
            "language_quality_score": 8.0,
            "relevance_score": 8.0,
            "reasoning": "Good."
        }"""
        
        provider = create_mock_provider(mock_response)
        judge = LLMJudge(provider=provider)

        verdict = await judge.evaluate(
            user_query="Test",
            bot_response="Response",
        )

        assert verdict.evaluation_cost_usd >= 0
        assert verdict.evaluation_tokens > 0
        assert verdict.model_used == "mock-judge"

    @pytest.mark.asyncio
    async def test_evaluate_json_in_markdown(self):
        """Evaluate should handle JSON wrapped in markdown."""
        mock_response = """```json
{
    "correctness_score": 8.0,
    "helpfulness_score": 8.0,
    "safety_score": 8.0,
    "language_quality_score": 8.0,
    "relevance_score": 8.0,
    "reasoning": "JSON in markdown."
}
```"""
        
        provider = create_mock_provider(mock_response)
        judge = LLMJudge(provider=provider)

        verdict = await judge.evaluate(
            user_query="Test",
            bot_response="Response",
        )

        assert verdict.overall_score == 8.0

    @pytest.mark.asyncio
    async def test_evaluate_invalid_json(self):
        """Evaluate should raise on invalid JSON."""
        provider = create_mock_provider("This is not JSON!")
        judge = LLMJudge(provider=provider)

        with pytest.raises(JudgeEvaluationError, match="Failed to parse"):
            await judge.evaluate(
                user_query="Test",
                bot_response="Response",
            )

    @pytest.mark.asyncio
    async def test_evaluate_missing_reasoning(self):
        """Evaluate should raise if reasoning is missing."""
        mock_response = """{
            "correctness_score": 8.0,
            "helpfulness_score": 8.0,
            "safety_score": 8.0,
            "language_quality_score": 8.0,
            "relevance_score": 8.0
        }"""
        
        provider = create_mock_provider(mock_response)
        judge = LLMJudge(provider=provider)

        with pytest.raises(JudgeEvaluationError, match="reasoning"):
            await judge.evaluate(
                user_query="Test",
                bot_response="Response",
            )

    @pytest.mark.asyncio
    async def test_evaluate_no_criteria_enabled(self):
        """Judge should raise if no criteria enabled."""
        mock_response = """{
            "reasoning": "Test"
        }"""
        
        provider = create_mock_provider(mock_response)
        criteria = JudgeCriteria(
            correctness=False,
            helpfulness=False,
            safety=False,
            language_quality=False,
            relevance=False,
        )
        judge = LLMJudge(provider=provider, criteria=criteria)

        with pytest.raises(JudgeEvaluationError, match="No criteria enabled"):
            await judge.evaluate(
                user_query="Test",
                bot_response="Response",
            )
