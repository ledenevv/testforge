"""Unit tests for the compliance check: disclaimer, forbidden phrases, language (M9b-3)."""

import pytest

from testforge.validation.compliance import (
    DEFAULT_DISCLAIMER_PATTERN,
    FORBIDDEN_PHRASES,
    check_compliance,
    cyrillic_share,
)

GOOD = (
    "**Резюме**\n\nВаши анализы в целом в пределах нормы.\n\n"
    "⚠️ Это информационный разбор. Не заменяет консультацию врача."
)


class TestDisclaimer:
    def test_good_text_passes(self):
        result = check_compliance(GOOD)

        assert result.name == "compliance"
        assert result.status == "pass"

    def test_missing_disclaimer_fails(self):
        result = check_compliance(GOOD.replace("Не заменяет консультацию врача.", ""))

        assert result.status == "fail"
        assert any("disclaimer missing" in message for message in result.messages)

    def test_disclaimer_sentences_may_be_on_separate_lines(self):
        text = "Это информационный разбор.\n\nНе заменяет консультацию врача."

        assert check_compliance(text).status == "pass"

    def test_disclaimer_phrase_itself_must_be_on_one_line(self):
        text = "Это информационный разбор.\nНе заменяет\nконсультацию врача."

        assert check_compliance(text).status == "fail"

    def test_custom_pattern_replaces_the_default(self):
        assert check_compliance(GOOD, disclaimer_pattern=r"обратитесь к врачу").status == "fail"

        text = GOOD + " Обратитесь к врачу."
        assert check_compliance(text, disclaimer_pattern=r"обратитесь к врачу").status == "pass"

    def test_default_pattern_is_the_plan_pattern(self):
        assert DEFAULT_DISCLAIMER_PATTERN == (
            "Это информационный разбор.*не заменяет консультацию врача"
        )


class TestForbiddenPhrases:
    @pytest.mark.parametrize("phrase", FORBIDDEN_PHRASES)
    def test_each_default_phrase_is_caught(self, phrase):
        result = check_compliance(f"{GOOD} Здесь сказано: {phrase}.")

        assert result.status == "fail"
        assert result.details["forbidden_found"] == [phrase]

    def test_match_ignores_case(self):
        assert check_compliance(f"{GOOD} ДИАГНОЗ установлен.").status == "fail"

    def test_extra_phrases_for_the_document_are_forbidden(self):
        result = check_compliance(GOOD + " Пейте много воды.", extra_forbidden=["пейте много воды"])

        assert result.status == "fail"
        assert result.details["forbidden_found"] == ["пейте много воды"]

    def test_clean_text_has_nothing_forbidden(self):
        assert check_compliance(GOOD).details["forbidden_found"] == []


class TestLanguage:
    def test_share_ignores_digits_punctuation_and_emoji(self):
        assert cyrillic_share("АЛТ: 25 Ед/л ⚠️ !!!") == 1.0

    def test_latin_letters_lower_the_share(self):
        assert cyrillic_share("АЛТ ALT") == pytest.approx(3 / 6)

    def test_no_letters_means_zero_share(self):
        assert cyrillic_share("123 !!!") == 0.0

    def test_english_text_fails(self):
        result = check_compliance(
            "This is an informational review. Not a substitute for a doctor."
        )

        assert result.status == "fail"
        assert any("Russian text expected" in message for message in result.messages)

    def test_exactly_80_percent_is_not_enough(self):
        result = check_compliance("а" * 8 + "a" * 2)

        assert any("Russian text expected" in message for message in result.messages)

    def test_just_over_80_percent_is_enough(self):
        result = check_compliance("а" * 81 + "a" * 19)

        assert not any("Russian text expected" in message for message in result.messages)
