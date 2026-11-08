"""Unit tests for configuration module."""

import os
from pathlib import Path

import pytest

from testforge.config import (
    BotTarget,
    CostLimits,
    ForgeConfig,
    LLMConfig,
    load_config,
    substitute_env_vars,
)


class TestCostLimits:
    """Test CostLimits model."""

    def test_valid_cost_limits(self):
        """Valid cost limits should pass validation."""
        limits = CostLimits(
            per_scenario_max_usd=0.20,
            per_run_max_usd=0.50,
            alert_threshold_usd=0.40,
        )
        assert limits.per_scenario_max_usd == 0.20
        assert limits.per_run_max_usd == 0.50
        assert limits.alert_threshold_usd == 0.40

    def test_alert_threshold_must_be_less_than_max(self):
        """Alert threshold >= max should fail."""
        with pytest.raises(ValueError, match="must be less than"):
            CostLimits(
                per_scenario_max_usd=0.20,
                per_run_max_usd=0.50,
                alert_threshold_usd=0.50,  # Equal to max
            )

    def test_negative_values_rejected(self):
        """Negative cost values should be rejected."""
        with pytest.raises(ValueError):
            CostLimits(per_scenario_max_usd=-0.10)


class TestBotTarget:
    """Test BotTarget model."""

    def test_valid_bot_target(self):
        """Valid bot config should pass."""
        bot = BotTarget(
            name="test-bot",
            token="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz",
            test_user_id=12345678,
        )
        assert bot.name == "test-bot"
        assert bot.test_user_id == 12345678

    def test_env_var_token_allowed(self):
        """Env var placeholders should be allowed."""
        bot = BotTarget(
            name="test-bot",
            token="${TESTFORGE_BOT_TOKEN}",
            test_user_id=12345678,
        )
        assert bot.token == "${TESTFORGE_BOT_TOKEN}"

    def test_invalid_token_format_rejected(self):
        """Invalid token format should be rejected."""
        with pytest.raises(ValueError, match="Invalid bot token format"):
            BotTarget(
                name="test-bot",
                token="invalid-token",
                test_user_id=12345678,
            )


class TestLLMConfig:
    """Test LLMConfig model."""

    def test_valid_llm_config(self):
        """Valid LLM config should pass."""
        llm = LLMConfig(
            provider="anthropic",
            api_key="sk-ant-api03-test-key-12345",
            model="claude-sonnet-4",
            temperature=0.3,
            max_tokens=4096,
        )
        assert llm.provider == "anthropic"
        assert llm.model == "claude-sonnet-4"

    def test_mock_provider_allows_empty_api_key(self):
        """Mock provider doesn't need real API key."""
        llm = LLMConfig(
            provider="mock",
            api_key="",
            model="mock-model",
        )
        assert llm.provider == "mock"

    def test_temperature_range_validation(self):
        """Temperature must be in valid range."""
        with pytest.raises(ValueError):
            LLMConfig(
                provider="anthropic",
                api_key="test-key",
                temperature=3.0,  # Too high
            )


class TestEnvVarSubstitution:
    """Test environment variable substitution."""

    def test_substitute_single_var(self, monkeypatch):
        """Single env var should be substituted."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        data = {"key": "${TEST_VAR}"}
        result = substitute_env_vars(data)
        assert result["key"] == "test_value"

    def test_substitute_nested_vars(self, monkeypatch):
        """Nested env vars should be substituted."""
        monkeypatch.setenv("VAR1", "value1")
        monkeypatch.setenv("VAR2", "value2")
        data = {
            "level1": {
                "key1": "${VAR1}",
                "level2": {
                    "key2": "${VAR2}",
                },
            }
        }
        result = substitute_env_vars(data)
        assert result["level1"]["key1"] == "value1"
        assert result["level1"]["level2"]["key2"] == "value2"

    def test_missing_env_var_replaced_with_empty(self):
        """Missing env var should be replaced with empty string."""
        data = {"key": "${NONEXISTENT_VAR}"}
        result = substitute_env_vars(data)
        assert result["key"] == ""

    def test_list_substitution(self, monkeypatch):
        """Env vars in lists should be substituted."""
        monkeypatch.setenv("LIST_VAR", "item_value")
        data = {"items": ["${LIST_VAR}", "static"]}
        result = substitute_env_vars(data)
        assert result["items"] == ["item_value", "static"]


class TestLoadConfig:
    """Test config loading from YAML."""

    def test_load_valid_config(self, tmp_path, monkeypatch):
        """Valid config file should load successfully."""
        monkeypatch.setenv("TESTFORGE_BOT_TOKEN", "1234567890:ABCdefGHI")
        monkeypatch.setenv("TESTFORGE_LLM_API_KEY", "sk-test-key-12345")
        
        config_file = tmp_path / "test.yaml"
        config_file.write_text("""
mode: mock
bot:
  name: test-bot
  token: ${TESTFORGE_BOT_TOKEN}
  test_user_id: 12345678
llm:
  provider: mock
  api_key: ${TESTFORGE_LLM_API_KEY}
  model: mock-model
""")
        
        config = load_config(config_file)
        assert config.mode == "mock"
        assert config.bot.name == "test-bot"
        assert config.llm.provider == "mock"

    def test_load_nonexistent_file(self):
        """Loading nonexistent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    def test_load_empty_file(self, tmp_path):
        """Empty config file should raise ValueError."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        
        with pytest.raises(ValueError, match="empty"):
            load_config(config_file)

    def test_load_invalid_yaml(self, tmp_path):
        """Invalid YAML should raise error."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("mode: mock\nbot: [unclosed list")
        
        with pytest.raises(Exception):  # YAML parse error
            load_config(config_file)

    def test_real_mode_requires_bot_token(self, tmp_path):
        """Real mode without bot token should fail validation."""
        config_file = tmp_path / "real.yaml"
        config_file.write_text("""
mode: real
bot:
  name: test-bot
  token: ${TESTFORGE_BOT_TOKEN}
  test_user_id: 12345678
llm:
  provider: anthropic
  api_key: sk-ant-api03-test-key-longer-than-10-chars
  model: claude-sonnet-4
""")
        
        with pytest.raises(ValueError, match="TESTFORGE_BOT_TOKEN"):
            load_config(config_file)


class TestForgeConfig:
    """Test ForgeConfig model integration."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        config = ForgeConfig(
            mode="mock",
            bot=BotTarget(
                name="test",
                token="${TESTFORGE_BOT_TOKEN}",
                test_user_id=123,
            ),
            llm=LLMConfig(
                provider="mock",
                api_key="test",
                model="mock-model",
            ),
        )
        assert config.scenarios_dir == "fixtures/scenarios"
        assert config.baseline_file == "runs/baseline.yml"
        assert config.cost_limits.per_scenario_max_usd == 0.20
