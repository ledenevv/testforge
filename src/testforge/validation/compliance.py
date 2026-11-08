"""Compliance checks on the bot's interpretation: disclaimer, forbidden phrases, language."""

import re

from testforge.validation.models import CheckResult

DEFAULT_DISCLAIMER_PATTERN = r"Это информационный разбор.*не заменяет консультацию врача"

# Phrases the bot must not use. Taken from the plan: the ask-toby medical-disclaimer
# skill was not reachable when this was written.
FORBIDDEN_PHRASES = (
    "диагноз",
    "диагностирую",
    "назначаю",
    "рекомендую лечение",
    "рекомендую принимать",
)

# The plan requires more than 80% Cyrillic letters
MIN_CYRILLIC_SHARE = 0.8


def cyrillic_share(text: str) -> float:
    """Share of letters that are Cyrillic. Digits, punctuation and emoji are not counted."""
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    cyrillic = sum(1 for char in letters if "\u0400" <= char <= "\u04ff")
    return cyrillic / len(letters)


def check_compliance(
    text: str,
    disclaimer_pattern: str | None = None,
    extra_forbidden: list[str] | None = None,
) -> CheckResult:
    """
    Check the disclaimer, forbidden phrases and language of an interpretation.

    Args:
        text: Interpretation text the bot sent
        disclaimer_pattern: Regex the disclaimer must match (default: the plan's pattern)
        extra_forbidden: Phrases forbidden for this document, on top of the default list

    Returns:
        CheckResult named 'compliance'
    """
    pattern = disclaimer_pattern or DEFAULT_DISCLAIMER_PATTERN
    messages: list[str] = []

    if not re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        messages.append(f"disclaimer missing (expected pattern: {pattern})")

    lowered = text.lower()
    forbidden = list(dict.fromkeys([*FORBIDDEN_PHRASES, *(extra_forbidden or [])]))
    found = [phrase for phrase in forbidden if phrase.lower() in lowered]
    messages.extend(f"forbidden phrase present: {phrase!r}" for phrase in found)

    share = cyrillic_share(text)
    if share <= MIN_CYRILLIC_SHARE:
        messages.append(
            f"Russian text expected: {share:.0%} of letters are Cyrillic, need more than 80%"
        )

    return CheckResult(
        name="compliance",
        status="fail" if messages else "pass",
        messages=messages or ["disclaimer present, no forbidden phrases, Russian text"],
        details={
            "cyrillic_share": round(share, 4),
            "forbidden_found": found,
            "disclaimer_pattern": pattern,
        },
    )
