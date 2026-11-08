"""Unit tests for validators."""

import pytest

from testforge.executor.validators import ValidationError, validate_expect
from testforge.scenarios.models import ExpectCondition
from testforge.telegram.models import TelegramMessage, TelegramUpdate, TelegramUser


class TestValidators:
    """Test expect condition validators."""

    @pytest.fixture
    def bot_user(self):
        """Bot user fixture."""
        return TelegramUser(
            id=999999,
            is_bot=True,
            first_name="TestBot",
        )

    def _make_update(self, text: str, bot_user: TelegramUser) -> TelegramUpdate:
        """Helper to create TelegramUpdate."""
        return TelegramUpdate(
            update_id=1,
            message=TelegramMessage(
                message_id=1,
                **{"from": bot_user},
                chat_id=12345,
                text=text,
            ),
        )

    def test_validate_contains_success(self, bot_user):
        """Validate 'contains' should pass when text is present."""
        condition = ExpectCondition(contains="hello")
        updates = [self._make_update("Hello world!", bot_user)]

        # Should not raise
        validate_expect(condition, updates)

    def test_validate_contains_case_insensitive(self, bot_user):
        """Validate 'contains' should be case-insensitive."""
        condition = ExpectCondition(contains="HELLO")
        updates = [self._make_update("hello world!", bot_user)]

        # Should not raise (case-insensitive)
        validate_expect(condition, updates)

    def test_validate_contains_failure(self, bot_user):
        """Validate 'contains' should fail when text is missing."""
        condition = ExpectCondition(contains="missing")
        updates = [self._make_update("Hello world!", bot_user)]

        with pytest.raises(ValidationError, match="Expected response to contain"):
            validate_expect(condition, updates)

    def test_validate_not_contains_success(self, bot_user):
        """Validate 'not_contains' should pass when text is absent."""
        condition = ExpectCondition(not_contains="missing")
        updates = [self._make_update("Hello world!", bot_user)]

        # Should not raise
        validate_expect(condition, updates)

    def test_validate_not_contains_failure(self, bot_user):
        """Validate 'not_contains' should fail when text is present."""
        condition = ExpectCondition(not_contains="hello")
        updates = [self._make_update("Hello world!", bot_user)]

        with pytest.raises(ValidationError, match="Expected response to NOT contain"):
            validate_expect(condition, updates)

    def test_validate_response_count_success(self, bot_user):
        """Validate 'response_count' should pass when count matches."""
        condition = ExpectCondition(response_count=2)
        updates = [
            self._make_update("First", bot_user),
            self._make_update("Second", bot_user),
        ]

        # Should not raise
        validate_expect(condition, updates)

    def test_validate_response_count_failure(self, bot_user):
        """Validate 'response_count' should fail when count differs."""
        condition = ExpectCondition(response_count=1)
        updates = [
            self._make_update("First", bot_user),
            self._make_update("Second", bot_user),
        ]

        with pytest.raises(ValidationError, match="Expected 1 response"):
            validate_expect(condition, updates)

    def test_validate_regex_success(self, bot_user):
        """Validate 'matches_regex' should pass when pattern matches."""
        condition = ExpectCondition(matches_regex=r"hello.*world")
        updates = [self._make_update("Hello wonderful world!", bot_user)]

        # Should not raise
        validate_expect(condition, updates)

    def test_validate_regex_case_insensitive(self, bot_user):
        """Validate 'matches_regex' should be case-insensitive."""
        condition = ExpectCondition(matches_regex=r"HELLO.*WORLD")
        updates = [self._make_update("hello wonderful world!", bot_user)]

        # Should not raise (regex is case-insensitive)
        validate_expect(condition, updates)

    def test_validate_regex_failure(self, bot_user):
        """Validate 'matches_regex' should fail when pattern doesn't match."""
        condition = ExpectCondition(matches_regex=r"missing.*pattern")
        updates = [self._make_update("Hello world!", bot_user)]

        with pytest.raises(ValidationError, match="Expected response to match regex"):
            validate_expect(condition, updates)

    def test_validate_multiple_conditions(self, bot_user):
        """Validate multiple conditions together."""
        condition = ExpectCondition(
            contains="hello",
            not_contains="goodbye",
            response_count=1,
        )
        updates = [self._make_update("Hello world!", bot_user)]

        # All conditions should pass
        validate_expect(condition, updates)

    def test_validate_multiple_updates_combined(self, bot_user):
        """Validate should check all updates combined."""
        condition = ExpectCondition(contains="second")
        updates = [
            self._make_update("First message", bot_user),
            self._make_update("Second message", bot_user),
        ]

        # Should find 'second' in combined text
        validate_expect(condition, updates)

    def test_validate_empty_updates(self):
        """Validate with no updates."""
        condition = ExpectCondition(response_count=0)
        updates = []

        # Should pass when expecting 0 responses
        validate_expect(condition, updates)

    def test_validate_empty_condition(self, bot_user):
        """Validate with empty condition (all fields None)."""
        condition = ExpectCondition()
        updates = [self._make_update("Any text", bot_user)]

        # Should pass (no conditions to check)
        validate_expect(condition, updates)

    def test_validate_russian_text(self, bot_user):
        """Validate should work with Russian text."""
        condition = ExpectCondition(contains="привет")
        updates = [self._make_update("Привет, мир!", bot_user)]

        # Should pass
        validate_expect(condition, updates)

    def test_validate_multiline_text(self, bot_user):
        """Validate should work with multiline responses."""
        condition = ExpectCondition(contains="line 2")
        updates = [self._make_update("Line 1\nLine 2\nLine 3", bot_user)]

        # Should find text across lines
        validate_expect(condition, updates)
