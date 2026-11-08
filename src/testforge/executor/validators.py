"""Validators for expect conditions."""

import re

from testforge.scenarios.models import ExpectCondition
from testforge.telegram.models import TelegramUpdate


class ValidationError(Exception):
    """Raised when expect condition validation fails."""

    pass


def validate_expect(
    condition: ExpectCondition,
    updates: list[TelegramUpdate],
) -> None:
    """
    Validate that updates match expect condition.

    Args:
        condition: Expected condition to check
        updates: Bot responses (updates) to validate

    Raises:
        ValidationError: If condition is not met
    """
    # Check response count
    if condition.response_count is not None:
        if len(updates) != condition.response_count:
            raise ValidationError(
                f"Expected {condition.response_count} response(s), got {len(updates)}"
            )

    # Combine all response texts
    all_text = ""
    for update in updates:
        if update.message and update.message.text:
            all_text += update.message.text + "\n"

    # Check 'contains'
    if condition.contains is not None:
        if condition.contains.lower() not in all_text.lower():
            raise ValidationError(
                f"Expected response to contain '{condition.contains}', "
                f"but got: {all_text[:100]}..."
            )

    # Check 'not_contains'
    if condition.not_contains is not None:
        if condition.not_contains.lower() in all_text.lower():
            raise ValidationError(
                f"Expected response to NOT contain '{condition.not_contains}', "
                f"but it was found in: {all_text[:100]}..."
            )

    # Check regex match
    if condition.matches_regex is not None:
        pattern = re.compile(condition.matches_regex, re.IGNORECASE | re.DOTALL)
        if not pattern.search(all_text):
            raise ValidationError(
                f"Expected response to match regex '{condition.matches_regex}', "
                f"but got: {all_text[:100]}..."
            )
