"""Unit tests for Telegram models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from testforge.telegram import ProfileData


def _profile(**overrides):
    data = {"sex": "m", "birth_year": 1985, "height_cm": 180, "weight_kg": 75.0}
    data.update(overrides)
    return ProfileData(**data)


class TestProfileData:
    def test_valid_profile(self):
        profile = _profile()
        assert profile.birth_year == 1985

    def test_current_year_allowed(self):
        assert _profile(birth_year=datetime.now().year).birth_year == datetime.now().year

    def test_future_birth_year_rejected(self):
        with pytest.raises(ValidationError, match="future"):
            _profile(birth_year=datetime.now().year + 1)

    def test_too_old_birth_year_rejected(self):
        with pytest.raises(ValidationError):
            _profile(birth_year=1899)
