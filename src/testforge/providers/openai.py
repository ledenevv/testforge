"""OpenAI LLM provider (GPT models)."""

import asyncio
from typing import Any

try:
    from openai import AsyncOpenAI
except ImportError as e:
    raise ImportError(
        "The 'openai' package is required for OpenAIProvider. "
        "Install it with: pip install openai"
    ) from e

from testforge.config import LLMConfig
from testforge.providers.base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""

    # Pricing per 1M tokens (as of 2026-11-08)
    # Source: https://openai.com/pricing
    PRICING = {
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        # Fallback
        "default": {"input": 10.0, "output": 30.0},
    }

    def __init__(self, config: LLMConfig):
        """
        Initialize OpenAI provider.

        Args:
            config: LLM configuration (must have provider="openai")
        """
        if config.provider != "openai":
            raise ValueError(
                f"Invalid provider: {config.provider}. Expected 'openai'."
            )

        self.config = config
        self.client = AsyncOpenAI(api_key=config.api_key)

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_sec: int | None = None,
    ) -> LLMResponse:
        """Generate completion with GPT."""
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
                        self.client.chat.completions.create(
                            model=self.config.model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            messages=[{"role": "user", "content": prompt}],
                        ),
                        timeout=timeout_sec,
                    )

                # Extract text from choices
                if not response.choices:
                    raise RuntimeError(
                        "OpenAI returned empty choices array. "
                        "This may indicate content filtering or API issue."
                    )
                text = response.choices[0].message.content or ""

                # Count tokens
                tokens_in = response.usage.prompt_tokens
                tokens_out = response.usage.completion_tokens

                # Calculate cost
                cost_usd = self.calculate_cost(tokens_in, tokens_out)

                return LLMResponse(
                    text=text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    duration_sec=timer.duration,
                    model=self.config.model,
                    provider="openai",
                    metadata={
                        "response_id": response.id,
                        "finish_reason": response.choices[0].finish_reason,
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
                    f"OpenAI API error (attempt {attempt + 1}/{retries + 1}): {e}"
                )
                if attempt < retries:
                    await asyncio.sleep(min(2**attempt, 30))  # Exponential backoff, capped at 30s
                continue

        raise last_error or RuntimeError("All retries failed")

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count using tiktoken.

        Note: This is a stub in Phase 0. Full implementation would use:
        import tiktoken
        enc = tiktoken.encoding_for_model(self.config.model)
        return len(enc.encode(text))
        """
        # Rough approximation for now
        return len(text) // 4

    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Calculate cost based on OpenAI pricing."""
        model_name = self.config.model.lower()
        
        # Try exact match first
        pricing = self.PRICING.get(model_name)
        
        # If no exact match, try substring matching (ordered by specificity)
        if not pricing:
            # Check most specific first to avoid substring collisions
            if "gpt-4-turbo" in model_name or "gpt-4o" in model_name:
                pricing = self.PRICING["gpt-4-turbo"]
            elif "gpt-4" in model_name:
                pricing = self.PRICING["gpt-4"]
            elif "gpt-3.5" in model_name:
                pricing = self.PRICING["gpt-3.5-turbo"]
            else:
                pricing = self.PRICING["default"]

        cost_in = (tokens_in / 1_000_000) * pricing["input"]
        cost_out = (tokens_out / 1_000_000) * pricing["output"]

        return cost_in + cost_out
