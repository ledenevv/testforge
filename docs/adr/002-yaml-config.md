# ADR-002: YAML Configuration Format

**Status:** Accepted  
**Date:** 2026-11-08  
**Deciders:** Winston (architect)

---

## Context

TestForge needs a configuration file format for:
- Test execution mode (mock vs. real)
- Bot credentials (token, test user ID)
- LLM provider settings (API key, model, parameters)
- Cost budgets (per-scenario, per-run limits)
- Directory paths (scenarios, fixtures, expectations)

**Three common options:**

### Option A: YAML

**Pros:**
- Human-readable, widely used for config
- Native support for comments
- Clean nested structure (no repetitive brackets)
- Consistency with ask-toby (uses YAML for some configs)
- Python ecosystem has excellent YAML support (PyYAML)

**Cons:**
- Whitespace-sensitive (can cause issues if not careful)
- Less type-safe than JSON Schema (but Pydantic solves this)

### Option B: TOML

**Pros:**
- Type-safe (explicit types: strings, integers, booleans)
- Less error-prone than YAML (no indentation issues)
- Popular in Python ecosystem (pyproject.toml)

**Cons:**
- Verbose for deeply nested structures
- Repetitive section headers for nested configs
- Less familiar to non-Python users

### Option C: JSON

**Pros:**
- Strict schema validation (JSON Schema)
- Universal format (works everywhere)
- No ambiguity (explicit syntax)

**Cons:**
- **No comments** (critical limitation for config files)
- Verbose (lots of quotes, brackets)
- Not human-friendly for editing

---

## Decision

**We choose Option A: YAML.**

**Rationale:**

1. **Human-friendliness:** TestForge configs will be edited manually (setting API keys, adjusting budgets). YAML is the most readable format.

2. **Comments are essential:** Config files need inline documentation:
   ```yaml
   llm:
     provider: anthropic
     api_key: "${TESTFORGE_LLM_API_KEY}"  # Get from console.anthropic.com
     model: claude-sonnet-4  # Can switch to claude-opus-4 for higher quality
     temperature: 0.3  # Lower = more deterministic
   ```

3. **Consistency with ask-toby:** ask-toby uses YAML for some config (though Alembic uses TOML). Familiar to target audience.

4. **Pydantic provides type safety:** We get YAML's readability + Pydantic's validation:
   ```python
   class LLMConfig(BaseModel):
       provider: Literal["anthropic", "openai", "mock"]
       temperature: float = Field(ge=0.0, le=2.0)
   ```

5. **Environment variable substitution:** Easy to implement in YAML:
   ```yaml
   bot:
     token: "${TESTFORGE_BOT_TOKEN}"  # Replaced at load time
   ```

---

## Implementation

**Config loader (`src/testforge/config.py`):**
1. Load YAML with PyYAML
2. Substitute environment variables (`${VAR_NAME}` syntax)
3. Validate with Pydantic models
4. Return typed `ForgeConfig` instance

**Example config (`config/examples/mock-bot.yaml`):**
```yaml
mode: mock
bot:
  name: "ask-toby (mock)"
  token: "${TESTFORGE_BOT_TOKEN}"
  test_user_id: 12345678
llm:
  provider: anthropic
  api_key: "${TESTFORGE_LLM_API_KEY}"
  model: claude-sonnet-4
  temperature: 0.3
cost_limits:
  per_scenario_max_usd: 0.20
  per_run_max_usd: 0.50
```

---

## Consequences

### Positive

- Config files are easy to read and edit
- Comments guide users on what to set
- Pydantic catches typos and invalid values
- Environment variable substitution works smoothly

### Negative

- **Indentation errors possible** (but caught by YAML parser + Pydantic)
  - Mitigation: Example configs committed to repo, users copy and modify
- **YAML type ambiguity** (e.g., `yes` → `True`, `010` → `8` in octal)
  - Mitigation: Pydantic validates types, explicit quotes for strings

### Neutral

- One more dependency (PyYAML) — acceptable, it's standard library de facto

---

## Alternatives Considered

### A1: TOML for main config, YAML for scenarios

Use TOML for `testforge.toml` (typed, explicit), YAML for scenario files (readable, nested).

**Rejected because:**
- Two formats increase cognitive load
- Config file is small enough that YAML's readability > TOML's type safety

### A2: JSON with JSONC (JSON with Comments)

Use JSON5 or similar for comment support.

**Rejected because:**
- Non-standard (not all tools support JSONC)
- Still more verbose than YAML

---

## Related Decisions

- **ADR-001:** External tool (config must be standalone, not depend on ask-toby)
- **ADR-005:** YAML scenarios (consistent format across configs and scenarios)

---

## Notes

**When to reconsider:**

If TestForge grows to 1000+ line configs, TOML's explicit sections may scale better. But Phase 0 configs are ~30 lines — YAML is ideal.

**Edge cases handled:**

1. **Missing env vars:** `${NONEXISTENT}` → empty string (Pydantic fails if required field)
2. **Invalid YAML syntax:** PyYAML raises exception, caught by `load_config()`
3. **Type mismatches:** Pydantic validates (e.g., `temperature: "high"` fails)

---

**Decision accepted:** 2026-11-08  
**Implemented in:** M2 (Configuration System)
