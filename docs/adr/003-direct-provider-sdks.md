# ADR-003: Direct Provider SDKs vs. LiteLLM

**Status:** Accepted  
**Date:** 2026-11-08  
**Deciders:** Winston (architect)

---

## Context

TestForge needs to call LLM providers (Anthropic Claude, OpenAI GPT) for LLM-as-judge evaluation. Two architectural approaches:

### Option A: Direct Provider SDKs

Use official SDKs directly:
- `anthropic` package for Claude
- `openai` package for GPT

### Option B: LiteLLM

Use [LiteLLM](https://github.com/BerriAI/litellm) — unified interface for 100+ providers:
```python
from litellm import acompletion

response = await acompletion(
    model="claude-sonnet-4",
    messages=[{"role": "user", "content": prompt}],
)
```

---

## Decision

**We choose Option A: Direct Provider SDKs.**

---

## Rationale

### Why Direct SDKs Win

**1. Simplicity (Phase 0 constraint)**

Phase 0 uses only 2 providers:
- Anthropic (Claude Sonnet 4) — for LLM-as-judge
- Mock provider — for tests without API calls

LiteLLM's value proposition is **multi-provider support**. With only 2 providers (one mock), it's overhead.

**2. Fewer dependencies**

```toml
# Direct approach
anthropic = ">=0.39"
openai = ">=1.60"  # Future, not used in Phase 0

# LiteLLM approach
litellm = ">=1.30"
  # Brings: anthropic, openai, cohere, replicate, ...
  # Dozens of transitive dependencies
```

TestForge is a **testing tool** — we want minimal surface area for breakage.

**3. Better error messages**

When an API call fails:
- **Direct SDK:** Clear error from Anthropic API (`AuthenticationError`, `RateLimitError`)
- **LiteLLM:** Wrapped error, sometimes loses detail (`litellm.exceptions.APIError`)

For debugging test failures, direct errors help.

**4. Easier to mock for tests**

```python
# Direct SDK (simple)
class MockProvider(LLMProvider):
    async def complete(self, prompt: str) -> LLMResponse:
        return LLMResponse(text="Mocked", ...)

# LiteLLM (need to mock litellm.acompletion, trickier)
```

**5. Control over retry logic**

We implement exponential backoff ourselves:
```python
for attempt in range(retries + 1):
    try:
        response = await client.messages.create(...)
    except Exception:
        await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

LiteLLM has built-in retries, but they're harder to customize for TestForge's budget tracking needs.

**6. Cost tracking accuracy**

Token counts come from provider APIs:
- **Anthropic:** `response.usage.input_tokens`, `response.usage.output_tokens`
- **OpenAI:** `response.usage.prompt_tokens`, `response.usage.completion_tokens`

LiteLLM wraps these, but TestForge needs exact counts for budget validation. Direct access is clearer.

---

### Why NOT LiteLLM (for Phase 0)

**LiteLLM is excellent for:**
- Applications supporting **dozens of providers** (e.g., chatbot with user-chosen backend)
- **Production apps** where provider switching is a business requirement
- **Abstracting away provider differences** (function calling, streaming)

**TestForge doesn't need this:**
- Phase 0: **1 provider** (Anthropic) + 1 mock
- Provider choice is **configuration**, not runtime user decision
- No function calling, no streaming (simple prompt → text completion)

---

## Implementation

**Provider abstraction (`src/testforge/providers/base.py`):**
```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, ...) -> LLMResponse:
        """Generate text completion."""

    @abstractmethod
    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Calculate cost for token usage."""
```

**Anthropic implementation (`src/testforge/providers/anthropic.py`):**
```python
from anthropic import AsyncAnthropic

class AnthropicProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        self.client = AsyncAnthropic(api_key=config.api_key)

    async def complete(self, prompt: str, ...) -> LLMResponse:
        response = await self.client.messages.create(...)
        return LLMResponse(
            text=response.content[0].text,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=self.calculate_cost(...),
            ...
        )
```

**Cost calculation (provider-specific pricing):**
```python
PRICING = {
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},  # per 1M tokens
    "claude-opus-4": {"input": 15.0, "output": 75.0},
}
```

---

## Consequences

### Positive

- **Lightweight:** Only 2 direct dependencies (anthropic, openai)
- **Testable:** `MockProvider` is trivial to implement
- **Debuggable:** Clear error messages from native SDKs
- **Predictable:** No wrapper magic, direct API calls

### Negative

- **Adding provider 3+:** Manual work (copy-paste AnthropicProvider, adjust API calls)
  - **Mitigation:** Phase 0 uses only Anthropic. If Phase 2 adds 5+ providers, reconsider.
- **No streaming support:** Direct SDKs require manual streaming setup
  - **Mitigation:** TestForge doesn't stream (batch completion only)

### Future Re-evaluation

**Switch to LiteLLM if:**
- Phase 2+ adds **5+ providers** (Cohere, Replicate, Gemini API, etc.)
- User wants to **choose provider at runtime** (config: `provider: auto-cheapest`)
- Streaming becomes a requirement

**Current threshold:** Stay direct until 3rd real provider needed.

---

## Alternatives Considered

### A1: Hybrid (LiteLLM for some, direct for others)

Use LiteLLM for "exotic" providers (Cohere, HuggingFace), direct SDKs for Anthropic/OpenAI.

**Rejected because:**
- Two abstraction layers = confusing
- Testing becomes harder (two mock strategies)

### A2: Custom wrapper over LiteLLM

Wrap LiteLLM in our `LLMProvider` interface.

**Rejected because:**
- Adds a layer of indirection
- Still need LiteLLM dependency (defeats simplicity goal)

---

## Related Decisions

- **ADR-002:** YAML config (providers configured in YAML, not hardcoded)
- **Future ADR:** If we add LiteLLM later, document migration path

---

## Code References

- `src/testforge/providers/base.py` — abstract interface
- `src/testforge/providers/anthropic.py` — Claude implementation
- `src/testforge/providers/openai.py` — GPT implementation (stub in Phase 0)
- `src/testforge/providers/mock.py` — testing implementation
- `tests/unit/test_providers.py` — unit tests (26 tests, all pass)

---

**Decision accepted:** 2026-11-08  
**Implemented in:** M3 (LLM Provider Abstraction)
