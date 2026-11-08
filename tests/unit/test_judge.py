"""Unit tests for the rubric judge: weighted score, pass rule, reply validation (M9b-4).

Carries over the hardening from the chunk 4 review: every score validated, booleans
rejected, JSON found inside prose, provider errors wrapped, no spend on bad input.
"""

import json
from pathlib import Path

import pytest
from testforge.config import LLMConfig
from testforge.judge import JudgeEvaluationError, LLMJudge, load_rubric
from testforge.judge.rubric import Rubric
from testforge.providers import MockProvider
from testforge.providers.base import LLMResponse

ROOT = Path(__file__).resolve().parents[2]
RUBRIC_FILE = ROOT / "fixtures" / "rubrics" / "interpretation_quality_v1.yml"
DOCUMENT = "Биохимия крови, 2026-10-15: АЛТ 25 Ед/л, АСТ 22 Ед/л. Все значения в норме."
INTERPRETATION = (
    "📊 **Резюме**\n\nВаши анализы в норме.\n\n"
    "⚠️ Это информационный разбор. Не заменяет консультацию врача."
)


def _config():
    return LLMConfig(provider="mock", api_key="", model="mock-judge")


def _rubric():
    return load_rubric(RUBRIC_FILE)


def _judge_text(overrides=None, *, drop=(), overall="Разбор понятный и корректный.", reasoning="Обосновано."):
    """A reply that scores the shipped rubric: 8.2 / 8.8 / 8.0 / 10.0 by default."""
    values = {
        "clarity": 8.2,
        "medical_appropriateness": 8.8,
        "russian_grammar": 8.0,
        "disclaimer_compliance": 10.0,
    }
    values.update(overrides or {})
    data = {
        name: {"score": score, "reasoning": reasoning}
        for name, score in values.items()
        if name not in drop
    }
    data["overall_assessment"] = overall
    return json.dumps(data, ensure_ascii=False)


async def _judge(text, rubric=None):
    provider = MockProvider(_config(), responses={"default": text})
    return await LLMJudge(provider).evaluate(rubric or _rubric(), DOCUMENT, INTERPRETATION)


class RecordingProvider(MockProvider):
    """MockProvider that keeps every prompt and keyword argument it received."""

    def __init__(self, text):
        super().__init__(_config(), responses={"default": text})
        self.prompts = []
        self.kwargs = []

    async def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        return await super().complete(prompt, **kwargs)


class FixedCostProvider(MockProvider):
    """Returns fixed tokens, cost and model, so the verdict's cost fields can be checked."""

    async def complete(self, prompt, **kwargs):
        return LLMResponse(
            text=_judge_text(),
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.0123,
            duration_sec=0.2,
            model="judge-model-x",
            provider="mock",
        )


def _small_rubric(template="{{ bot_interpretation }}"):
    return Rubric.model_validate(
        {
            "rubric_id": "small",
            "overall_pass_threshold": 7.0,
            "dimensions": [
                {
                    "id": "clarity",
                    "name": "Ясность",
                    "description": "Понятно ли написано?",
                    "weight": 1.0,
                    "min_score": 7.0,
                }
            ],
            "prompt_template": template,
        }
    )


class TestWeightedScore:
    @pytest.mark.asyncio
    async def test_plan_example_gives_8_67(self):
        verdict = await _judge(_judge_text())

        assert verdict.weighted_score == pytest.approx(8.67)

    @pytest.mark.asyncio
    async def test_each_dimension_keeps_its_rules(self):
        verdict = await _judge(_judge_text())

        rules = {d.id: (d.weight, d.min_score, d.critical) for d in verdict.dimensions}
        assert rules == {
            "clarity": (0.25, 7.0, False),
            "medical_appropriateness": (0.40, 8.0, True),
            "russian_grammar": (0.20, 7.0, False),
            "disclaimer_compliance": (0.15, 9.0, True),
        }

    @pytest.mark.asyncio
    async def test_reasoning_and_assessment_are_returned(self):
        verdict = await _judge(_judge_text(reasoning="Понятно."))

        assert verdict.dimensions[0].reasoning == "Понятно."
        assert verdict.overall_assessment == "Разбор понятный и корректный."

    @pytest.mark.asyncio
    async def test_all_good_passes_without_warnings(self):
        verdict = await _judge(_judge_text())

        assert verdict.passed is True
        assert verdict.failed_critical == []
        assert verdict.warnings == []


class TestPassRule:
    @pytest.mark.asyncio
    async def test_critical_medical_below_minimum_fails_despite_high_average(self):
        verdict = await _judge(
            _judge_text(
                {
                    "clarity": 10,
                    "russian_grammar": 10,
                    "disclaimer_compliance": 10,
                    "medical_appropriateness": 7.9,
                }
            )
        )

        assert verdict.weighted_score > 7.5
        assert verdict.passed is False
        assert verdict.failed_critical == ["medical_appropriateness"]

    @pytest.mark.asyncio
    async def test_critical_disclaimer_below_minimum_fails(self):
        verdict = await _judge(_judge_text({"disclaimer_compliance": 8.5}))

        assert verdict.passed is False
        assert verdict.failed_critical == ["disclaimer_compliance"]

    @pytest.mark.asyncio
    async def test_non_critical_below_minimum_only_warns(self):
        verdict = await _judge(_judge_text({"clarity": 6.0}))

        assert verdict.passed is True
        assert verdict.failed_critical == []
        assert any(warning.startswith("clarity:") for warning in verdict.warnings)

    @pytest.mark.asyncio
    async def test_average_below_threshold_fails_without_a_critical_failure(self):
        verdict = await _judge(
            _judge_text(
                {
                    "clarity": 6.0,
                    "russian_grammar": 6.0,
                    "medical_appropriateness": 8.0,
                    "disclaimer_compliance": 9.0,
                }
            )
        )

        assert verdict.weighted_score == pytest.approx(7.25)
        assert verdict.passed is False
        assert verdict.failed_critical == []

    @pytest.mark.asyncio
    async def test_score_equal_to_threshold_passes(self):
        verdict = await _judge(
            _judge_text(
                {
                    "clarity": 7.0,
                    "russian_grammar": 6.0,
                    "medical_appropriateness": 8.0,
                    "disclaimer_compliance": 9.0,
                }
            )
        )

        assert verdict.weighted_score == pytest.approx(7.5)
        assert verdict.passed is True


class TestReplyValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad", ["8", None, True, False, [8], 11, -1, 10.01, float("nan"), float("inf")]
    )
    async def test_invalid_score_is_rejected(self, bad):
        with pytest.raises(JudgeEvaluationError, match="clarity.score"):
            await _judge(_judge_text({"clarity": bad}))

    @pytest.mark.asyncio
    async def test_missing_dimension_entry_is_rejected(self):
        with pytest.raises(JudgeEvaluationError, match="missing entry for dimension 'disclaimer_compliance'"):
            await _judge(_judge_text(drop=("disclaimer_compliance",)))

    @pytest.mark.asyncio
    async def test_missing_overall_assessment_is_rejected(self):
        data = json.loads(_judge_text())
        del data["overall_assessment"]

        with pytest.raises(JudgeEvaluationError, match="overall_assessment"):
            await _judge(json.dumps(data))

    @pytest.mark.asyncio
    async def test_reasoning_must_be_a_string(self):
        with pytest.raises(JudgeEvaluationError, match="clarity.reasoning"):
            await _judge(_judge_text(reasoning=None))

    @pytest.mark.asyncio
    async def test_dimension_entry_must_be_an_object(self):
        data = json.loads(_judge_text())
        data["clarity"] = 8.2

        with pytest.raises(JudgeEvaluationError, match="must be an object"):
            await _judge(json.dumps(data))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("text", ["[1, 2]", '"my reasoning is sound"', "42", "null"])
    async def test_non_object_json_is_rejected(self, text):
        with pytest.raises(JudgeEvaluationError, match="must be an object"):
            await _judge(text)

    @pytest.mark.asyncio
    async def test_text_without_json_is_a_parse_error(self):
        with pytest.raises(JudgeEvaluationError, match="Failed to parse"):
            await _judge("Оценка: всё хорошо.")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "wrap",
        [
            "Here is my evaluation:\n```json\n{body}\n```",
            "```json\n{body}\n```\nHope this helps!",
            "Sure! {body} Let me know if you need more.",
        ],
    )
    async def test_json_with_prose_around_it_is_accepted(self, wrap):
        verdict = await _judge(wrap.format(body=_judge_text()))

        assert verdict.weighted_score == pytest.approx(8.67)

    @pytest.mark.asyncio
    async def test_provider_failure_is_wrapped(self):
        class Failing(MockProvider):
            async def complete(self, prompt, **kwargs):
                raise RuntimeError("network down")

        with pytest.raises(JudgeEvaluationError, match="LLM call failed: network down"):
            await LLMJudge(Failing(_config())).evaluate(_rubric(), DOCUMENT, INTERPRETATION)

    @pytest.mark.asyncio
    async def test_template_with_unknown_variable_is_wrapped(self):
        rubric = _small_rubric(template="{{ documnt_summary }}")

        with pytest.raises(JudgeEvaluationError, match="cannot render the prompt"):
            await _judge(_judge_text(), rubric=rubric)


class TestPromptSent:
    @pytest.mark.asyncio
    async def test_summary_and_interpretation_are_sent_inside_tags(self):
        provider = RecordingProvider(_judge_text())

        await LLMJudge(provider).evaluate(_rubric(), DOCUMENT, INTERPRETATION)

        prompt = provider.prompts[0]
        assert f"<document_summary>\n{DOCUMENT}\n</document_summary>" in prompt
        assert f"<bot_interpretation>\n{INTERPRETATION}\n</bot_interpretation>" in prompt

    @pytest.mark.asyncio
    async def test_prompt_tells_the_judge_tagged_text_is_data(self):
        provider = RecordingProvider(_judge_text())

        await LLMJudge(provider).evaluate(_rubric(), DOCUMENT, INTERPRETATION)

        assert "данные для оценки" in provider.prompts[0]

    @pytest.mark.asyncio
    async def test_every_dimension_is_listed_with_its_weight(self):
        provider = RecordingProvider(_judge_text())
        rubric = _rubric()

        await LLMJudge(provider).evaluate(rubric, DOCUMENT, INTERPRETATION)

        prompt = provider.prompts[0]
        for dimension in rubric.dimensions:
            assert dimension.name in prompt
            assert f"вес {dimension.weight}" in prompt

    @pytest.mark.asyncio
    async def test_json_example_uses_the_dimension_ids(self):
        provider = RecordingProvider(_judge_text())
        rubric = _rubric()

        await LLMJudge(provider).evaluate(rubric, DOCUMENT, INTERPRETATION)

        prompt = provider.prompts[0]
        for dimension in rubric.dimensions:
            assert f'"{dimension.id}": {{"score"' in prompt

    @pytest.mark.asyncio
    async def test_braces_and_template_syntax_in_the_text_stay_literal(self):
        provider = RecordingProvider(_judge_text())
        interpretation = 'JSON {"a": 1} and {{x}} and {% raw %}'

        await LLMJudge(provider).evaluate(_rubric(), DOCUMENT, interpretation)

        assert interpretation in provider.prompts[0]

    @pytest.mark.asyncio
    async def test_temperature_defaults_to_zero(self):
        provider = RecordingProvider(_judge_text())

        await LLMJudge(provider).evaluate(_rubric(), DOCUMENT, INTERPRETATION)

        assert provider.kwargs[0]["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_temperature_can_be_set(self):
        provider = RecordingProvider(_judge_text())

        await LLMJudge(provider, temperature=0.3).evaluate(_rubric(), DOCUMENT, INTERPRETATION)

        assert provider.kwargs[0]["temperature"] == 0.3


class TestVerdictMetadata:
    @pytest.mark.asyncio
    async def test_cost_tokens_model_and_duration_come_from_the_response(self):
        verdict = await LLMJudge(FixedCostProvider(_config())).evaluate(
            _rubric(), DOCUMENT, INTERPRETATION
        )

        assert verdict.tokens_in == 100
        assert verdict.tokens_out == 50
        assert verdict.cost_usd == 0.0123
        assert verdict.duration_sec == 0.2
        assert verdict.model_used == "judge-model-x"

    @pytest.mark.asyncio
    async def test_rubric_id_version_and_threshold_are_recorded(self):
        verdict = await _judge(_judge_text())

        assert verdict.rubric_id == "interpretation_quality_v1"
        assert verdict.rubric_version == "1.0"
        assert verdict.threshold == 7.5
