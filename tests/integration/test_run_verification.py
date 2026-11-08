"""End to end: run the mock bot, save the run, verify it (M9b-3)."""

import json

import pytest

from testforge.executor import ScenarioExecutor
from testforge.reporting import RunStore
from testforge.scenarios import ActionType, ExpectCondition, Scenario, Step
from testforge.telegram import MockTelegramBot
from testforge.validation import RunVerifier

EXPECTATIONS = """\
document_id: lab_report_001
interpretation:
  must_contain_sections:
    - "Резюме"
    - "Ключевые моменты"
    - "Что обсудить с врачом"
  must_not_contain_phrases:
    - "назначаю"
performance:
  total_e2e_max_sec: 120
"""


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
                action=ActionType.EXPECT_RESPONSE,
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
    async def test_mock_interpretation_passes_every_check(self, tmp_path, document, expectations):
        bot = MockTelegramBot(responses_dir="fixtures/mock_responses")
        scenario = _scenario(document, expectations)
        result = await ScenarioExecutor(bot=bot).run(scenario)
        store = RunStore(tmp_path / "runs")
        run_dir = store.save_run(result, now=None)

        verification = RunVerifier(store).verify(run_dir, scenario)

        statuses = {check.name: check.status for check in verification.checks}
        assert statuses == {
            "schema": "pass",
            "compliance": "pass",
            "cost": "pass",
            "performance": "pass",
            "llm_judge": "skipped",
        }
        assert verification.status == "pass"

    @pytest.mark.asyncio
    async def test_verification_json_is_saved_next_to_the_trace(
        self, tmp_path, document, expectations
    ):
        bot = MockTelegramBot(responses_dir="fixtures/mock_responses")
        scenario = _scenario(document, expectations)
        store = RunStore(tmp_path / "runs")
        run_dir = store.save_run(await ScenarioExecutor(bot=bot).run(scenario))
        verifier = RunVerifier(store)

        path = verifier.write(run_dir, verifier.verify(run_dir, scenario))

        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["status"] == "pass"
        assert saved["scenario_id"] == "single_upload"

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
        result = await ScenarioExecutor(bot=bot).run(scenario)
        store = RunStore(tmp_path / "runs")
        run_dir = store.save_run(result)

        verification = RunVerifier(store).verify(run_dir, scenario)

        schema = next(check for check in verification.checks if check.name == "schema")
        assert schema.status == "fail"
        assert verification.status == "fail"
