"""The five plan scenarios: they load, their files exist, and they pass on the mock bot (M9b-5)."""

import json
from pathlib import Path

import pytest

from testforge.config import LLMConfig
from testforge.executor import ScenarioExecutor
from testforge.providers import MockProvider
from testforge.providers.base import LLMResponse
from testforge.reporting import RunStore
from testforge.scenarios import load_scenarios_from_directory, validate_scenario_files
from testforge.telegram import MockTelegramBot
from testforge.validation import RunVerifier

PLAN_IDS = ["batch_upload", "conversation_qa", "measurement", "onboarding", "single_upload"]
RUBRICS = str(Path(__file__).resolve().parents[2] / "fixtures" / "rubrics")
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


class JudgeStub(MockProvider):
    """Judge with a fixed reply and a known cost."""

    def __init__(self):
        super().__init__(LLMConfig(provider="mock", api_key="", model="judge-model"))

    async def complete(self, prompt, **kwargs):
        return LLMResponse(
            text=JUDGE_REPLY,
            tokens_in=5000,
            tokens_out=800,
            cost_usd=0.023,
            duration_sec=4.0,
            model="judge-model",
            provider="mock",
        )


@pytest.fixture(scope="module")
def scenarios():
    return {s.id: s for s in load_scenarios_from_directory("fixtures/scenarios")}


def _bot():
    return MockTelegramBot(responses_dir="fixtures/mock_responses")


class TestPlanScenarioFiles:
    def test_exactly_the_five_plan_scenarios_are_present(self, scenarios):
        assert sorted(scenarios) == PLAN_IDS

    @pytest.mark.parametrize("name", PLAN_IDS)
    def test_every_referenced_file_exists(self, scenarios, name):
        assert validate_scenario_files(scenarios[name]) == []

    def test_budgets_are_positive_and_add_up(self, scenarios):
        budgets = [
            s.validation.cost_budget_usd
            for s in scenarios.values()
            if s.validation.cost_budget_usd is not None
        ]

        assert all(budget > 0 for budget in budgets)
        assert sum(budgets) == pytest.approx(0.20 + 0.20 + 0.05)


class TestPlanScenariosOnMock:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", PLAN_IDS)
    async def test_scenario_passes_on_the_mock_bot(self, scenarios, name):
        result = await ScenarioExecutor(bot=_bot()).run(scenarios[name])

        assert result.passed is True, result.error
        assert result.steps_failed == 0

    @pytest.mark.asyncio
    async def test_batch_interpretation_covers_all_three_documents(self, scenarios):
        result = await ScenarioExecutor(bot=_bot()).run(scenarios["batch_upload"])

        interpretation = result.trace.captures["interpretation"]
        assert "Гемоглобин" in interpretation
        assert "ТТГ" in interpretation
        assert "АЛТ" in interpretation

    @pytest.mark.asyncio
    async def test_measurement_stores_the_reading(self, scenarios):
        bot = _bot()

        await ScenarioExecutor(bot=bot).run(scenarios["measurement"])

        assert bot.measurements == [{"systolic": 120, "diastolic": 80}]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", ["single_upload", "batch_upload"])
    async def test_upload_scenarios_verify_end_to_end_with_the_judge(
        self, scenarios, name, tmp_path
    ):
        scenario = scenarios[name]
        store = RunStore(tmp_path / "runs")
        run_dir = store.save_run(await ScenarioExecutor(bot=_bot()).run(scenario))

        verification = await RunVerifier(store, provider=JudgeStub(), rubrics_dir=RUBRICS).verify(
            run_dir, scenario
        )

        assert verification.status == "pass"
        assert {check.name: check.status for check in verification.checks} == {
            "schema": "pass",
            "compliance": "pass",
            "cost": "pass",
            "performance": "pass",
            "llm_judge": "pass",
        }
        assert verification.judge.weighted_score == pytest.approx(8.67)
