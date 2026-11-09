"""Unit tests for mock bot flows: /analyze, batch uploads, blood pressure, answers (M9b-5)."""

import pytest

from testforge.telegram import MockTelegramBot
from testforge.validation.compliance import check_compliance

RESPONSES = "fixtures/mock_responses"
QUESTIONS = ["Что такое АЛТ?", "Нужно ли мне лечиться?", "Можно ли есть яйца?"]


@pytest.fixture
def bot():
    return MockTelegramBot(responses_dir=RESPONSES)


def _texts(updates):
    return [update.message.text for update in updates]


def _pdf(tmp_path, name):
    path = tmp_path / name
    path.write_text("fake", encoding="utf-8")
    return path


class TestUploadAndAnalyze:
    @pytest.mark.asyncio
    async def test_upload_is_only_acknowledged(self, bot, tmp_path):
        await bot.send_document(_pdf(tmp_path, "a.pdf"))
        texts = _texts(await bot.get_updates())

        assert len(texts) == 1
        assert "Документ получен" in texts[0]
        assert "Резюме" not in texts[0]

    @pytest.mark.asyncio
    async def test_analyze_after_one_upload_gives_the_single_interpretation(self, bot, tmp_path):
        await bot.send_document(_pdf(tmp_path, "a.pdf"))
        await bot.get_updates()
        await bot.send_message("/analyze")
        texts = _texts(await bot.get_updates())

        assert len(texts) == 1
        assert "Резюме" in texts[0]
        assert "Гемоглобин" not in texts[0]

    @pytest.mark.asyncio
    async def test_analyze_after_several_uploads_gives_one_batch_interpretation(
        self, bot, tmp_path
    ):
        for name in ["a.pdf", "b.pdf", "c.pdf"]:
            await bot.send_document(_pdf(tmp_path, name))
        await bot.get_updates()  # three acknowledgements
        await bot.send_message("/analyze")
        texts = _texts(await bot.get_updates())

        assert len(texts) == 1
        assert "Гемоглобин" in texts[0]

    @pytest.mark.asyncio
    async def test_analyze_without_uploads_asks_for_a_document(self, bot):
        await bot.send_message("/analyze")

        assert _texts(await bot.get_updates()) == ["Сначала отправьте документ с анализами."]

    @pytest.mark.asyncio
    async def test_uploads_are_used_once(self, bot, tmp_path):
        await bot.send_document(_pdf(tmp_path, "a.pdf"))
        await bot.send_message("/analyze")
        await bot.get_updates()
        await bot.send_message("/analyze")

        assert _texts(await bot.get_updates()) == ["Сначала отправьте документ с анализами."]


class TestBloodPressure:
    @pytest.mark.asyncio
    async def test_measure_prompt_comes_from_the_fixture(self, bot):
        await bot.send_message("/measure")

        assert _texts(await bot.get_updates()) == ["Укажите давление в формате 120/80:"]

    @pytest.mark.asyncio
    async def test_valid_reading_is_recorded(self, bot):
        await bot.send_message("/measure")
        await bot.get_updates()
        await bot.send_message("120/80")

        assert _texts(await bot.get_updates()) == ["Записал: 120/80 мм рт. ст. Спасибо!"]
        assert bot.measurements == [{"systolic": 120, "diastolic": 80}]
        assert bot.state == "idle"

    @pytest.mark.asyncio
    async def test_non_numeric_answer_asks_again_and_keeps_waiting(self, bot):
        await bot.send_message("/measure")
        await bot.get_updates()
        await bot.send_message("абв")
        texts = _texts(await bot.get_updates())

        assert "Укажите давление" in texts[0]
        assert bot.state == "measure_bp"
        assert bot.measurements == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reading", ["300/80", "80/120", "120/120", "20/10"])
    async def test_implausible_reading_is_rejected(self, bot, reading):
        await bot.send_message("/measure")
        await bot.get_updates()
        await bot.send_message(reading)
        texts = _texts(await bot.get_updates())

        assert texts[0].startswith(f"Проверьте значение {reading}")
        assert bot.measurements == []


class TestAnswersAndInterpretations:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("question", QUESTIONS)
    async def test_answer_passes_the_compliance_rules(self, bot, question):
        await bot.send_message(question)
        answer = _texts(await bot.get_updates())[0]

        assert check_compliance(answer).status == "pass"

    @pytest.mark.asyncio
    async def test_interpretations_pass_the_compliance_rules(self, bot, tmp_path):
        await bot.send_document(_pdf(tmp_path, "single.pdf"))
        await bot.get_updates()
        await bot.send_message("/analyze")
        single = _texts(await bot.get_updates())[0]

        for name in ["one.pdf", "two.pdf", "three.pdf"]:
            await bot.send_document(_pdf(tmp_path, name))
        await bot.get_updates()
        await bot.send_message("/analyze")
        batch = _texts(await bot.get_updates())[0]

        assert check_compliance(single).status == "pass"
        assert check_compliance(batch).status == "pass"


class TestReset:
    @pytest.mark.asyncio
    async def test_reset_forgets_uploads_and_readings(self, bot, tmp_path):
        await bot.send_document(_pdf(tmp_path, "a.pdf"))
        await bot.send_message("/measure")
        await bot.send_message("120/80")

        bot.reset()

        assert bot.pending_documents == []
        assert bot.measurements == []
