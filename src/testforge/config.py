"""Configuration models and loader."""

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class CostLimits(BaseModel):
    """Cost budget limits."""

    per_scenario_max_usd: float = Field(
        default=0.20,
        gt=0,
        description="Maximum cost per scenario in USD",
    )
    per_run_max_usd: float = Field(
        default=0.50,
        gt=0,
        description="Maximum cost per run in USD",
    )
    alert_threshold_usd: float = Field(
        default=0.40,
        gt=0,
        description="Warn if cost exceeds this threshold",
    )

    @model_validator(mode="after")
    def validate_thresholds(self) -> "CostLimits":
        """Validate budget logic consistency."""
        if self.alert_threshold_usd >= self.per_run_max_usd:
            raise ValueError(
                f"alert_threshold_usd ({self.alert_threshold_usd}) must be less than "
                f"per_run_max_usd ({self.per_run_max_usd})"
            )
        if self.per_scenario_max_usd > self.per_run_max_usd:
            raise ValueError(
                f"per_scenario_max_usd ({self.per_scenario_max_usd}) cannot exceed "
                f"per_run_max_usd ({self.per_run_max_usd})"
            )
        return self


class BotTarget(BaseModel):
    """Telegram bot target configuration."""

    name: str = Field(description="Bot name (for display)")
    token: str = Field(description="Bot token from BotFather (use env var)")
    test_user_id: int = Field(description="Test user Telegram ID")

    @field_validator("token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        """Validate bot token format (basic check)."""
        # Allow env var placeholders (will be validated after substitution)
        if v.startswith("${"):
            return v
        
        # Allow empty string (will be caught by real mode validator if needed)
        if not v:
            return v
        
        # Check for whitespace-only (actual mistake)
        if not v.strip():
            raise ValueError("Bot token cannot be whitespace-only")
        
        # Basic format: 1234567890:ABCdef...
        if not re.match(r"^\d+:[A-Za-z0-9_-]+$", v):
            raise ValueError(
                "Invalid bot token format. Expected: <bot_id>:<token_string>"
            )
        return v


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: Literal["anthropic", "openai", "mock"] = Field(
        description="LLM provider name"
    )
    api_key: str = Field(description="API key (use env var)")
    model: str = Field(
        default="claude-sonnet-4-6",
        description="Model identifier",
    )
    temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Maximum tokens in response",
    )
    timeout_sec: int = Field(
        default=30,
        gt=0,
        description="Request timeout in seconds",
    )
    retries: int = Field(
        default=3,
        ge=0,
        description="Number of retries on failure",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str, info) -> str:
        """Validate API key format (provider-specific)."""
        provider = info.data.get("provider")
        if provider == "mock":
            return v  # Mock mode doesn't need real API key
        
        # Check for whitespace-only or empty
        if not v or not v.strip():
            raise ValueError("API key cannot be empty or whitespace-only")
        
        if v.startswith("${"):
            # Env var not substituted yet
            return v
        
        # Provider-specific validation (prefix only for flexibility in tests)
        if provider == "anthropic":
            if not v.startswith("sk-ant-"):
                raise ValueError("Anthropic API key should start with 'sk-ant-'")
        elif provider == "openai":
            if not v.startswith("sk-"):
                raise ValueError("OpenAI API key should start with 'sk-'")
        
        # Generic length check (lenient for test keys)
        if len(v) < 10:
            raise ValueError(f"API key seems too short for {provider} provider")
        
        return v


class ForgeConfig(BaseModel):
    """Main TestForge configuration."""

    mode: Literal["mock", "real"] = Field(
        default="mock",
        description="Execution mode: mock (in-memory) or real (Telegram API)",
    )
    bot: BotTarget = Field(description="Telegram bot configuration")
    llm: LLMConfig = Field(description="LLM provider configuration")
    cost_limits: CostLimits = Field(
        default_factory=CostLimits,
        description="Cost budget limits",
    )
    scenarios_dir: str = Field(
        default="fixtures/scenarios",
        description="Directory containing test scenarios",
    )
    fixtures_dir: str = Field(
        default="fixtures/documents",
        description="Directory containing test fixtures (PDFs)",
    )
    expectations_dir: str = Field(
        default="fixtures/expectations",
        description="Directory containing validation expectations",
    )
    baseline_file: str = Field(
        default="runs/baseline.yml",
        description="Baseline metrics file path",
    )

    @model_validator(mode="after")
    def validate_real_mode_requirements(self) -> "ForgeConfig":
        """Validate that real mode has proper bot token."""
        if self.mode == "real":
            if self.bot.token.startswith("${") or not self.bot.token:
                raise ValueError(
                    "Real mode requires TESTFORGE_BOT_TOKEN environment variable to be set"
                )
        return self
    
    @model_validator(mode="after")
    def validate_directory_paths(self) -> "ForgeConfig":
        """Warn if configured directories don't exist."""
        import logging
        logger = logging.getLogger(__name__)
        
        for attr in ["scenarios_dir", "fixtures_dir", "expectations_dir"]:
            path_str = getattr(self, attr)
            path = Path(path_str)
            if not path.exists():
                logger.warning(
                    f"Configuration: {attr} does not exist: {path_str}. "
                    "This may cause runtime errors when loading fixtures."
                )
        return self


def substitute_env_vars(data: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively substitute environment variables in config.

    Supports ${VAR_NAME} syntax.
    """

    def substitute(value: Any) -> Any:
        if isinstance(value, str):
            # Find all ${VAR_NAME} patterns (case-insensitive)
            pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}"
            matches = re.findall(pattern, value)
            for var_name in matches:
                env_value = os.getenv(var_name, "")
                value = value.replace(f"${{{var_name}}}", env_value)
            return value
        elif isinstance(value, dict):
            return {k: substitute(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [substitute(item) for item in value]
        else:
            return value

    return substitute(data)


def load_config(path: str | Path) -> ForgeConfig:
    """
    Load and validate configuration from YAML file.

    Args:
        path: Path to YAML config file

    Returns:
        Validated ForgeConfig instance

    Raises:
        FileNotFoundError: If config file not found
        ValueError: If config is invalid
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)

    if not raw_data:
        raise ValueError(f"Config file is empty: {config_path}")

    # Substitute environment variables
    data = substitute_env_vars(raw_data)

    # Validate with Pydantic
    try:
        config = ForgeConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid config: {e}") from e

    return config


def save_config(config: ForgeConfig, path: str | Path) -> None:
    """
    Save configuration to YAML file.

    Args:
        config: ForgeConfig instance
        path: Path to save YAML file
    """
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict, excluding defaults
    data = config.model_dump(mode="json", exclude_defaults=False)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
