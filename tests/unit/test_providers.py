"""Unit tests for LLM providers."""

import inspect
from types import SimpleNamespace

import pytest
from anthropic.resources.messages import AsyncMessages

from testforge.config import LLMConfig
from testforge.providers import (
    AnthropicProvider,
    LLMResponse,
    MockProvider,
    OpenAIProvider,
)


class TestLLMResponse:
    """Test LLMResponse model."""

    def test_valid_response(self):
        """Valid response should validate."""
        response = LLMResponse(
            text="Hello world",
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.001,
            duration_sec=1.5,
            model="test-model",
            provider="test",
        )
        assert response.text == "Hello world"
        assert response.tokens_in == 10
        assert response.cost_usd == 0.001

    def test_negative_tokens_rejected(self):
        """Negative token counts should be rejected."""
        with pytest.raises(ValueError):
            LLMResponse(
                text="test",
                tokens_in=-1,
                tokens_out=5,
                cost_usd=0.001,
                duration_sec=1.0,
                model="test",
                provider="test",
            )

    def test_metadata_optional(self):
        """Metadata should be optional."""
        response = LLMResponse(
            text="test",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.001,
            duration_sec=1.0,
            model="test",
            provider="test",
        )
        assert response.metadata == {}


class TestMockProvider:
    """Test MockProvider."""

    @pytest.fixture
    def config(self):
        """Mock provider config."""
        return LLMConfig(
            provider="mock",
            api_key="not-needed",
            model="mock-model",
        )

    @pytest.mark.asyncio
    async def test_default_responses(self, config):
        """Mock provider should return default responses."""
        provider = MockProvider(config)
        response = await provider.complete("hello")

        assert "mock" in response.text.lower()
        assert response.tokens_in > 0
        assert response.tokens_out > 0
        assert response.cost_usd >= 0
        assert response.provider == "mock"

    @pytest.mark.asyncio
    async def test_custom_responses(self, config):
        """Mock provider should support custom responses."""
        custom = {"test prompt": "test response"}
        provider = MockProvider(config, responses=custom)

        response = await provider.complete("test prompt")
        assert response.text == "test response"

    @pytest.mark.asyncio
    async def test_russian_default_response(self, config):
        """Mock provider should handle Russian."""
        provider = MockProvider(config)
        response = await provider.complete("Привет")

        assert "Привет" in response.text or "тестовый" in response.text.lower()

    @pytest.mark.asyncio
    async def test_partial_match(self, config):
        """Mock provider should match substrings."""
        provider = MockProvider(config)
        provider.add_response("greeting", "Hello there!")

        response = await provider.complete("Say a greeting please")
        assert "Hello there!" in response.text

    @pytest.mark.asyncio
    async def test_empty_prompt_rejected(self, config):
        """Empty prompt should raise error."""
        provider = MockProvider(config)

        with pytest.raises(ValueError, match="empty"):
            await provider.complete("")

    def test_count_tokens(self, config):
        """Token counting should be consistent."""
        provider = MockProvider(config)
        tokens = provider.count_tokens("Hello world this is a test")
        assert tokens > 0
        assert tokens < 100  # Reasonable upper bound

    def test_calculate_cost(self, config):
        """Cost calculation should work."""
        provider = MockProvider(config)
        cost = provider.calculate_cost(1000, 500)
        assert cost >= 0
        assert cost < 0.01  # Mock is very cheap

    def test_call_count(self, config):
        """Call count should increment."""
        provider = MockProvider(config)
        assert provider.call_count == 0

    @pytest.mark.asyncio
    async def test_call_count_increments(self, config):
        """Call count should increment on each call."""
        provider = MockProvider(config)
        await provider.complete("test1")
        assert provider.call_count == 1

        await provider.complete("test2")
        assert provider.call_count == 2

        provider.reset_call_count()
        assert provider.call_count == 0

    def test_invalid_provider_rejected(self):
        """Wrong provider name should fail."""
        config = LLMConfig(
            provider="anthropic",  # Wrong!
            api_key="sk-ant-test-key-long-enough",
            model="test",
        )
        with pytest.raises(ValueError, match="Expected 'mock'"):
            MockProvider(config)

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self):
        """Prompt matching should be case-insensitive."""
        config = LLMConfig(provider="mock", api_key="", model="test")
        provider = MockProvider(config)
        
        # Add response with lowercase key
        provider.add_response("hello world", "Matched!")
        
        # Test various case variations
        response1 = await provider.complete("hello world")  # Exact
        assert response1.text == "Matched!"
        
        response2 = await provider.complete("HELLO WORLD")  # Uppercase
        assert response2.text == "Matched!"
        
        response3 = await provider.complete("Hello World")  # Title case
        assert response3.text == "Matched!"


class TestAnthropicProvider:
    """Test AnthropicProvider."""

    @pytest.fixture
    def config(self):
        """Anthropic provider config."""
        return LLMConfig(
            provider="anthropic",
            api_key="sk-ant-test-key",
            model="claude-sonnet-4",
            temperature=0.3,
            max_tokens=1000,
        )

    def test_initialization(self, config):
        """Provider should initialize with valid config."""
        provider = AnthropicProvider(config)
        assert provider.config.model == "claude-sonnet-4"
        assert provider.config.provider == "anthropic"

    def test_invalid_provider_rejected(self):
        """Wrong provider name should fail."""
        config = LLMConfig(
            provider="openai",  # Wrong!
            api_key="sk-test-key-long-enough",
            model="test",
        )
        with pytest.raises(ValueError, match="Expected 'anthropic'"):
            AnthropicProvider(config)

    def test_token_counting(self, config):
        """Token counting should give reasonable estimates."""
        provider = AnthropicProvider(config)
        tokens = provider.count_tokens("Hello world")
        assert tokens > 0
        assert tokens < 100

    def test_cost_calculation_sonnet(self, config):
        """Cost should be calculated correctly for Claude Sonnet."""
        provider = AnthropicProvider(config)
        # Sonnet: $3/1M input, $15/1M output
        cost = provider.calculate_cost(1_000_000, 1_000_000)
        assert abs(cost - 18.0) < 0.01  # $3 + $15 = $18

    def test_cost_calculation_opus(self):
        """Cost should be calculated correctly for Claude Opus."""
        config = LLMConfig(
            provider="anthropic",
            api_key="sk-ant-test-key-long",
            model="claude-opus-4",
        )
        provider = AnthropicProvider(config)
        # Opus: $15/1M input, $75/1M output
        cost = provider.calculate_cost(1_000_000, 1_000_000)
        assert abs(cost - 90.0) < 0.01  # $15 + $75 = $90

    def test_cost_calculation_haiku(self):
        """Cost should be calculated correctly for Claude Haiku."""
        config = LLMConfig(
            provider="anthropic",
            api_key="sk-ant-test-key-long",
            model="claude-haiku-4",
        )
        provider = AnthropicProvider(config)
        # Haiku: $0.25/1M input, $1.25/1M output
        cost = provider.calculate_cost(1_000_000, 1_000_000)
        assert abs(cost - 1.5) < 0.01  # $0.25 + $1.25 = $1.5

    def test_cost_calculation_unknown_model(self):
        """Unknown model should use default pricing."""
        config = LLMConfig(
            provider="anthropic",
            api_key="sk-ant-test-key-long",
            model="claude-future-5",
        )
        provider = AnthropicProvider(config)
        # Default: $3/1M input, $15/1M output (same as Sonnet)
        cost = provider.calculate_cost(1_000_000, 1_000_000)
        assert abs(cost - 18.0) < 0.01

    @pytest.mark.asyncio
    async def test_empty_prompt_rejected(self, config):
        """Empty or whitespace-only prompts should be rejected."""
        provider = AnthropicProvider(config)
        
        # Empty string
        with pytest.raises(ValueError, match="empty or whitespace"):
            await provider.complete("")
        
        # Whitespace-only
        with pytest.raises(ValueError, match="empty or whitespace"):
            await provider.complete("   ")

    # TODO: Add comprehensive retry/timeout tests
    # - Mock API to fail N times, verify retry count
    # - Verify exponential backoff timing (2^attempt, capped at 30s)
    # - Verify hung requests timeout after timeout_sec
    # - Verify final error is raised after exhausting retries
    # These tests require monkeypatching asyncio.sleep and mocking the Anthropic client

    @pytest.mark.asyncio
    async def test_request_arguments_are_accepted_by_the_sdk(self, config):
        """Every argument sent to messages.create() must exist in the installed SDK.

        Regression: SDK 1.0+ removed temperature, so passing it raised TypeError.
        """
        sent: dict = {}

        async def create(**kwargs):
            sent.update(kwargs)
            return SimpleNamespace(
                id="msg_test",
                stop_reason="end_turn",
                content=[SimpleNamespace(text="Ответ")],
                usage=SimpleNamespace(input_tokens=10, output_tokens=2),
            )

        provider = AnthropicProvider(config)
        provider.client = SimpleNamespace(messages=SimpleNamespace(create=create))

        result = await provider.complete("Опиши анализ")

        assert result.text == "Ответ"
        inspect.signature(AsyncMessages.create).bind_partial(None, **sent)


class TestOpenAIProvider:
    """Test OpenAIProvider."""

    @pytest.fixture
    def config(self):
        """OpenAI provider config."""
        return LLMConfig(
            provider="openai",
            api_key="sk-test-key",
            model="gpt-4-turbo",
            temperature=0.5,
            max_tokens=2000,
        )

    def test_initialization(self, config):
        """Provider should initialize with valid config."""
        provider = OpenAIProvider(config)
        assert provider.config.model == "gpt-4-turbo"
        assert provider.config.provider == "openai"

    def test_invalid_provider_rejected(self):
        """Wrong provider name should fail."""
        config = LLMConfig(
            provider="anthropic",  # Wrong!
            api_key="sk-ant-test-key-long",
            model="test",
        )
        with pytest.raises(ValueError, match="Expected 'openai'"):
            OpenAIProvider(config)

    def test_token_counting(self, config):
        """Token counting should give reasonable estimates."""
        provider = OpenAIProvider(config)
        tokens = provider.count_tokens("Hello world")
        assert tokens > 0
        assert tokens < 100

    def test_cost_calculation_gpt4(self, config):
        """Cost should be calculated correctly for GPT-4."""
        config.model = "gpt-4"
        provider = OpenAIProvider(config)
        # GPT-4: $30/1M input, $60/1M output
        cost = provider.calculate_cost(1_000_000, 1_000_000)
        assert abs(cost - 90.0) < 0.01  # $30 + $60 = $90

    def test_cost_calculation_gpt4_turbo(self, config):
        """Cost should be calculated correctly for GPT-4 Turbo."""
        provider = OpenAIProvider(config)
        # GPT-4 Turbo: $10/1M input, $30/1M output
        cost = provider.calculate_cost(1_000_000, 1_000_000)
        assert abs(cost - 40.0) < 0.01  # $10 + $30 = $40

    def test_cost_calculation_gpt35(self):
        """Cost should be calculated correctly for GPT-3.5."""
        config = LLMConfig(
            provider="openai",
            api_key="sk-test-key-long",
            model="gpt-3.5-turbo",
        )
        provider = OpenAIProvider(config)
        # GPT-3.5: $0.5/1M input, $1.5/1M output
        cost = provider.calculate_cost(1_000_000, 1_000_000)
        assert abs(cost - 2.0) < 0.01  # $0.5 + $1.5 = $2

    @pytest.mark.asyncio
    async def test_empty_prompt_rejected(self, config):
        """Empty or whitespace-only prompts should be rejected."""
        provider = OpenAIProvider(config)
        
        # Empty string
        with pytest.raises(ValueError, match="empty or whitespace"):
            await provider.complete("")
        
        # Whitespace-only
        with pytest.raises(ValueError, match="empty or whitespace"):
            await provider.complete("   ")

    # TODO: Add comprehensive retry/timeout tests
    # - Mock API to fail N times, verify retry count
    # - Verify exponential backoff timing (2^attempt, capped at 30s)
    # - Verify hung requests timeout after timeout_sec
    # - Verify final error is raised after exhausting retries
    # These tests require monkeypatching asyncio.sleep and mocking the OpenAI client


# Integration tests with real APIs are in tests/integration/
# They require valid API keys and are not run in CI by default
