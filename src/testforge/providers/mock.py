"""Mock LLM provider for testing."""

import asyncio
import hashlib
from typing import Any

from testforge.config import LLMConfig
from testforge.providers.base import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    """Mock LLM provider that returns canned responses."""

    def __init__(self, config: LLMConfig, responses: dict[str, str] | None = None):
        """
        Initialize mock provider.

        Args:
            config: LLM configuration (must have provider="mock")
            responses: Optional dict mapping prompt hash -> response text.
                      If None, uses default responses.
        """
        if config.provider != "mock":
            raise ValueError(
                f"Invalid provider: {config.provider}. Expected 'mock'."
            )

        self.config = config
        self.responses = responses or self._default_responses()
        self.call_count = 0

    def _default_responses(self) -> dict[str, str]:
        """Default canned responses for common prompts."""
        return {
            "hello": "Hello! I'm a mock LLM.",
            "привет": "Привет! Я тестовый LLM.",
            "test": "This is a test response.",
            "default": "Mock response for unknown prompt.",
        }

    def _prompt_to_key(self, prompt: str) -> str:
        """Convert prompt to lookup key (lowercase, trimmed)."""
        return prompt.lower().strip()

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_sec: int | None = None,
    ) -> LLMResponse:
        """Return canned response based on prompt."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty or whitespace-only")

        self.call_count += 1

        # Simulate network delay
        await asyncio.sleep(0.1)

        with self._measure_time() as timer:
            # Try to find matching response
            key = self._prompt_to_key(prompt)
            text = None

            # Exact match
            if key in self.responses:
                text = self.responses[key]
            # Partial match (for substring searches)
            else:
                for response_key, response_text in self.responses.items():
                    if response_key in key:
                        text = response_text
                        break

            # Fallback to default
            if text is None:
                text = self.responses.get("default", f"Mock echo: {prompt[:50]}...")

            # Simulate token counting
            tokens_in = self.count_tokens(prompt)
            tokens_out = self.count_tokens(text)

            # Mock cost (very cheap)
            cost_usd = self.calculate_cost(tokens_in, tokens_out)

        return LLMResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            duration_sec=timer.duration,
            model=self.config.model,
            provider="mock",
            metadata={
                "response_id": f"mock-{self.call_count}",
                "prompt_hash": hashlib.md5(prompt.encode()).hexdigest()[:8],
            },
        )

    def count_tokens(self, text: str) -> int:
        """Mock token counting (rough estimate)."""
        return len(text) // 4

    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Mock cost calculation (negligible)."""
        # Mock provider is free, but return small non-zero value for testing
        return (tokens_in + tokens_out) * 0.000001

    def add_response(self, prompt_key: str, response: str) -> None:
        """
        Add a canned response.

        Args:
            prompt_key: Key to match (case-insensitive, will be lowercased)
            response: Response text to return
        """
        self.responses[prompt_key.lower().strip()] = response

    def reset_call_count(self) -> None:
        """Reset call counter."""
        self.call_count = 0
