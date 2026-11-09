"""End to end: run the mock bot, save the run, verify it, judge included (M9b-3, M9b-4)."""

import json
from pathlib import Path

import pytest

from testforge.config import LLMConfig
from testforge.executor import ScenarioExecutor
from testforge.providers import MockProvider
from testforge.providers.base import LLMResponse
from testforge.reporting import RunStore
from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step
from testforge.telegram import MockTelegramBot
from testforge.validation import RunVerifier

RUBRICS = str(Path(__file__).resolve().parents[2] / "fixtures" / "rubrics")
EXPECTATIONS = """\
document_id: lab_report_001
document_summary: "Биохимия крови, 2026-10-15: АЛТ 25 Ед/л, АСТ 22 Ед/л. Все значения в норме."
interpretation:
  must_contain_sections:
    - "Резюме"
    - "Ключевые моменты"
    - "Что обсудить с врачом"
  must_not_contain_phrases:
    - "назначаю"
performance:
  total_e2e_max_sec: 120
llm_judge:
  rubric: interpretation_quality_v1
"""
JUDGE_REPLY = json.dumps(
    {
        "clarity": {"score": 8.2, "reasoning": "Структурировано."},
        "medical_appropriateness": {"score": 8.8, "reasoning": "Показатели верны."},
        "russian_grammar": {"score": 8.0, "reasoning": "Грамматика верная."},
        "disclaimer_compliance": {"score": 10.0, "reasoning": "Дисклеймер есть."},
        "overall_assessment": "Разбор понятный и корректный.",
    },
    ensure_ascii=False,
)


class FixedCostJudge(MockProvider):
    """Judge stand-in with a known cost, so the recorded spend can be checked exactly."""

    def __init__(self):
        super().__init__(LLMConfig(provider="mock", api_key="", model="judge-model"))

    async def complete(self, prompt, **kwargs):
        return LLMResponse(
            text=JUDGE_REPLY,
            tokens_in=5000,
            tokens_out=800,
            cost_usd=0.0230,
            duration_sec=4.1,
            model="judge-model",
            provider="mock",
        )


@pytest.fixture
def document(tmp_path):
    path = tmp_path / "lab_report_001.pdf"
    path.write_text("fake", encoding="utf-8")
    return path


@pytest.fixture
def expectations(tmp_path):
    path = tmp_path / "lab_report_001.yml"
    path.write_text(EXPECTATIONS, encoding="utf-8")
    return path


def _scenario(document, expectations, **validation):
    return Scenario(
        id="single_upload",
        description="Upload one report and keep the interpretation",
        steps=[
            Step(action=ActionType.SEND_DOCUMENT, document_path=str(document)),
            Step(
                action=ActionType.SEND_MESSAGE,
                text="/analyze",
                expect=ExpectCondition(contains="Резюме"),
                capture="interpretation",
            ),
        ],
        validation={
            "expectations": str(expectations),
            "compliance": True,
            "cost_budget_usd": 0.20,
            "performance_budget_sec": 120,
            **validation,
        },
    )


class TestMockRunVerification:
    @pytest.mark.asyncio
    async def test_mock_interpretation_passes_every_check_including_the_judge(
        self, tmp_path, document, expectations
    ):
        bot = MockTelegramBot(responses_dir="fixtures/mock_responses")
        scenario = _scenario(document, expectations, llm_judge=True)
        store = RunStore(tmp_path / "runs")
        run_dir = store.save_run(await ScenarioExecutor(bot=bot).run(scenario))

        verification = await RunVerifier(
            store,
            provider=FixedCostJudge(),
            rubrics_dir=RUBRICS,
        ).verify(run_dir, scenario)

        statuses = {check.name: check.status for check in verification.checks}
        assert statuses == {
            "schema": "pass",
            "compliance": "pass",
            "cost": "pass",
            "performance": "pass",
            "llm_judge": "pass",
        }
        assert verification.status == "pass"
        assert verification.judge.weighted_score == pytest.approx(8.67)

    @pytest.mark.asyncio
    async def test_judge_spend_and_report_are_saved_with_the_run(
        self, tmp_path, document, expectations
    ):
        bot = MockTelegramBot(responses_dir="fixtures/mock_responses")
        scenario = _scenario(document, expectations, llm_judge=True)
        store = RunStore(tmp_path / "runs")
        run_dir = store.save_run(await ScenarioExecutor(bot=bot).run(scenario))

        await RunVerifier(store, provider=FixedCostJudge(), rubrics_dir=RUBRICS).verify(
            run_dir, scenario
        )

        cost = json.loads((run_dir / "cost.json").read_text(encoding="utf-8"))
        assert cost["total_cost_usd"] == pytest.approx(0.0230)
        assert cost["calls"][0]["tokens_in"] == 5000
        assert cost["budget_used"] == pytest.approx(0.0230 / 0.20)
        report = (run_dir / "judge_detailed.md").read_text(encoding="utf-8")
        assert "**Overall: 8.67/10 — PASS (threshold 7.5)**" in report
        saved = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
        assert saved["status"] == "pass"

    @pytest.mark.asyncio
    async def test_section_the_bot_does_not_write_fails_the_run(self, tmp_path, document):
        strict = tmp_path / "strict.yml"
        strict.write_text(
            'document_id: lab_report_001\n'
            "interpretation:\n"
            '  must_contain_sections:\n    - "Противопоказания"\n',
            encoding="utf-8",
        )
        bot = MockTelegramBot(responses_dir="fixtures/mock_responses")
        scenario = _scenario(document, strict)
        store = RunStore(tmp_path / "runs")
        run_dir = store.save_run(await ScenarioExecutor(bot=bot).run(scenario))

        verification = await RunVerifier(store).verify(run_dir, scenario)

        schema = next(check for check in verification.checks if check.name == "schema")
        assert schema.status == "fail"
        assert verification.status == "fail"
