"""Anthropic LLM provider (Claude models)."""

import asyncio
from typing import Any

try:
    from anthropic import AsyncAnthropic
except ImportError as e:
    raise ImportError(
        "The 'anthropic' package is required for AnthropicProvider. "
        "Install it with: pip install anthropic"
    ) from e

from testforge.config import LLMConfig
from testforge.providers.base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    # Pricing per 1M tokens (as of 2026-11-08)
    # Source: https://www.anthropic.com/pricing
    PRICING = {
        "claude-opus-4": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4": {"input": 3.0, "output": 15.0},
        "claude-haiku-4": {"input": 0.25, "output": 1.25},
        # Fallback for unknown models
        "default": {"input": 3.0, "output": 15.0},
    }

    def __init__(self, config: LLMConfig):
        """
        Initialize Anthropic provider.

        Args:
            config: LLM configuration (must have provider="anthropic")
        """
        if config.provider != "anthropic":
            raise ValueError(
                f"Invalid provider: {config.provider}. Expected 'anthropic'."
            )

        self.config = config
        self.client = AsyncAnthropic(api_key=config.api_key)

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_sec: int | None = None,
    ) -> LLMResponse:
        """Generate completion with Claude."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty or whitespace-only")

        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature
        timeout_sec = timeout_sec or self.config.timeout_sec
        retries = self.config.retries

        last_error = None
        for attempt in range(retries + 1):
            try:
                with self._measure_time() as timer:
                    response = await asyncio.wait_for(
                        self.client.messages.create(
                            model=self.config.model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            messages=[{"role": "user", "content": prompt}],
                        ),
                        timeout=timeout_sec,
                    )

                # Extract text from response (find first text block)
                text = ""
                if response.content:
                    for block in response.content:
                        if hasattr(block, 'text'):
                            text = block.text
                            break
                    if not text:
                        raise RuntimeError(
                            "No text content in Anthropic response. "
                            f"Response contained {len(response.content)} non-text blocks."
                        )

                # Count tokens (from API response)
                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens

                # Calculate cost
                cost_usd = self.calculate_cost(tokens_in, tokens_out)

                return LLMResponse(
                    text=text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    duration_sec=timer.duration,
                    model=self.config.model,
                    provider="anthropic",
                    metadata={
                        "response_id": response.id,
                        "stop_reason": response.stop_reason,
                    },
                )

            except asyncio.TimeoutError as e:
                last_error = TimeoutError(
                    f"Request timed out after {timeout_sec}s (attempt {attempt + 1}/{retries + 1})"
                )
                if attempt < retries:
                    await asyncio.sleep(min(2**attempt, 30))  # Exponential backoff, capped at 30s
                continue

            except Exception as e:
                last_error = RuntimeError(
                    f"Anthropic API error (attempt {attempt + 1}/{retries + 1}): {e}"
                )
                if attempt < retries:
                    await asyncio.sleep(min(2**attempt, 30))  # Exponential backoff, capped at 30s
                continue

        # All retries failed
        raise last_error or RuntimeError("All retries failed")

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Note: Anthropic doesn't provide a public tokenizer.
        This is a rough estimate (1 token ~= 4 chars for English/Russian).
        For accurate counts, use the API response after calling complete().
        """
        # Rough approximation
        return len(text) // 4

    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Calculate cost based on Anthropic pricing."""
        model_name = self.config.model.lower()
        
        # Try exact match first
        pricing = self.PRICING.get(model_name)
        
        # If no exact match, try substring matching (ordered by specificity)
        if not pricing:
            # Order matters: check most specific first
            if "opus" in model_name:
                pricing = self.PRICING["claude-opus-4"]
            elif "sonnet" in model_name:
                pricing = self.PRICING["claude-sonnet-4"]
            elif "haiku" in model_name:
                pricing = self.PRICING["claude-haiku-4"]
            else:
                pricing = self.PRICING["default"]

        # Calculate cost (pricing is per 1M tokens)
        cost_in = (tokens_in / 1_000_000) * pricing["input"]
        cost_out = (tokens_out / 1_000_000) * pricing["output"]

        return cost_in + cost_out
