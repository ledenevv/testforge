"""Base LLM provider interface."""

import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Response from LLM provider."""

    text: str = Field(description="Generated text")
    tokens_in: int = Field(ge=0, description="Input tokens consumed")
    tokens_out: int = Field(ge=0, description="Output tokens generated")
    cost_usd: float = Field(ge=0.0, description="Cost in USD")
    duration_sec: float = Field(ge=0.0, description="Request duration in seconds")
    model: str = Field(description="Model used for generation")
    provider: str = Field(description="Provider name")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider-specific metadata",
    )


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_sec: int | None = None,
    ) -> LLMResponse:
        """
        Generate text completion.

        Args:
            prompt: Input prompt text
            max_tokens: Maximum tokens to generate (overrides config)
            temperature: Sampling temperature (overrides config)
            timeout_sec: Request timeout (overrides config)

        Returns:
            LLMResponse with generated text and metadata

        Raises:
            TimeoutError: If request exceeds timeout
            ValueError: If prompt is invalid
            RuntimeError: If provider API fails
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens in

        Returns:
            Number of tokens
        """
        pass

    @abstractmethod
    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """
        Calculate cost for token usage.

        Args:
            tokens_in: Input tokens
            tokens_out: Output tokens

        Returns:
            Cost in USD
        """
        pass

    def _measure_time(self):
        """Context manager to measure request duration."""

        class _Timer:
            def __init__(self):
                self.start = 0.0
                self.duration = 0.0

            def __enter__(self):
                self.start = time.perf_counter()
                return self

            def __exit__(self, *args):
                self.duration = time.perf_counter() - self.start

        return _Timer()
