# ADR-001: TestForge as External Tool (Not Integrated into ask-toby)

**Status:** Accepted  
**Date:** 2026-11-08  
**Deciders:** Winston (architect), User (owner)

---

## Context

We need to test ask-toby's multi-tier LLM pipeline (vision extraction → LOINC normalization → distillation → interpretation) to validate:
- Schema correctness (structured data outputs)
- Compliance (disclaimer, no forbidden medical phrases)
- Quality (Russian language, medical appropriateness)
- Cost (tokens/$ per pipeline stage)
- Performance (latency, E2E duration)

**Two architectural options:**

### Option A: Integrated Testing (inside ask-toby repo)

Add TestForge as a subdirectory or package within ask-toby's `tests/` directory.

**Pros:**
- Single repository
- Shared dependencies (pydantic, pytest)
- Access to ask-toby's internal modules (schemas, config)
- Easier CI integration (same GitHub Actions workflow)

**Cons:**
- **Violates ask-toby's architecture rules** (`import-linter` enforces layer separation; TestForge would need to import from multiple layers)
- Couples TestForge's release cycle to ask-toby's
- Pollutes ask-toby's dependency tree (Anthropic SDK for LLM-judge, Jinja2 for reports)
- Risk of accidental internal testing (calling ask-toby functions directly instead of Telegram API)
- ask-toby's strict quality gates (≤800 lines/file, mypy strict) may slow TestForge development

### Option B: External Black-Box Tool (separate repo)

TestForge lives in its own repository, tests ask-toby as a deployed service via Telegram Bot API.

**Pros:**
- **True E2E testing** — validates what real users experience (Telegram Bot API)
- Independent release cycle (TestForge v0.1.0 can test ask-toby v2.3.1)
- No risk of internal coupling (cannot accidentally import ask-toby modules)
- Can test **any** Telegram bot implementing similar patterns (reusable)
- Clean separation of concerns (ask-toby = product, TestForge = QA tool)
- Easier to evolve TestForge without ask-toby PR/review cycle

**Cons:**
- Duplicate schema definitions (TestForge expectations vs. ask-toby Pydantic models)
  - **Mitigation:** Schemas are reference-only, not runtime dependency
- Harder to debug failures (no direct access to ask-toby's internal state)
  - **Mitigation:** Comprehensive logging, execution traces, LLM-judge detailed reports
- Requires deployed staging bot for real-mode testing
  - **Mitigation:** Mock mode for development, real mode for final validation

---

## Decision

**We choose Option B: External Black-Box Tool.**

**Rationale:**

1. **Aligns with ask-toby's philosophy:** ask-toby's `CLAUDE.md` enforces strict layer separation. TestForge would violate this by importing from multiple layers (`db`, `services`, `llm`, `bot`).

2. **Reusability:** TestForge can test other Telegram bots (not just ask-toby). Example: testing a cloned fork of ask-toby with different LLM models.

3. **True E2E validation:** Tests what users see (Telegram Bot API responses), not internal function calls. Catches integration issues (API serialization, rate limits, network failures).

4. **Independent evolution:** ask-toby can refactor internals (e.g., migrate from Gemini to Claude) without breaking TestForge, as long as Telegram API contract remains stable.

5. **Clean CI integration:** ask-toby's CI runs its internal tests (pytest), TestForge CI runs E2E tests against staging bot. Failures are clearly attributed.

---

## Consequences

### Positive

- TestForge can be open-sourced independently (useful for Telegram bot testing community)
- No risk of accidental white-box testing (architectural boundaries enforced by repository separation)
- Faster development iteration (no ask-toby PR review cycle for TestForge changes)
- ask-toby's repository stays focused on product code (no QA tool bloat)

### Negative

- **Schema duplication:** TestForge's expectations YAMLs manually mirror ask-toby's Pydantic schemas
  - **Addressed:** Schemas are validation rules, not code dependencies; mismatches are caught by tests
- **Debugging harder:** Cannot set breakpoints in ask-toby code from TestForge
  - **Addressed:** Comprehensive logging in ask-toby (already exists), TestForge execution traces
- **Staging bot dependency:** Real-mode testing requires deployed bot
  - **Addressed:** Mock mode for 90% of development, real mode for final gate

### Neutral

- **Two repositories to maintain:** TestForge + ask-toby
  - **Acceptable:** Clean separation of responsibilities (product vs. QA tool)

---

## Alternatives Considered

### A1: Pytest Plugin (integrated but isolated)

Create TestForge as a pytest plugin installed in ask-toby's dev dependencies.

**Rejected because:**
- Still couples release cycles
- Pollutes ask-toby's `pyproject.toml`
- Plugin would need to import ask-toby modules → breaks layer separation

### A2: Monorepo with Separate Packages

ask-toby repo contains two packages: `ask_toby/` and `testforge/`.

**Rejected because:**
- ask-toby's CI/CD is tuned for single-package deployment (ops/deploy.sh)
- Increases repository complexity (two build systems, two release processes)
- Same cons as Option A (dependency pollution, layer violations)

---

## Related Decisions

- **ADR-002:** Config format (YAML chosen for consistency with ask-toby)
- **ADR-004:** Mock bot for Phase 0 (allows development without staging bot)
- **ADR-006:** Long polling vs. webhooks (polling chosen for simplicity)

---

## Notes

**When to reconsider:**

If ask-toby adds a stable **public Python SDK** (e.g., `ask_toby_client` package on PyPI), TestForge could use it for typed interactions. But SDK would still be black-box (HTTP/Telegram API wrapper), preserving E2E nature.

**Current status (Phase 0):**
- TestForge lives at `G:\testforge` (separate from ask-toby)
- Tests ask-toby via Telegram Bot API (black-box)
- Mock mode uses in-memory `MockTelegramBot` (no network)
- Real mode calls Telegram Bot API (when staging bot available)

---

**Decision accepted:** 2026-11-08  
**Implemented in:** M1 (Project Setup)
