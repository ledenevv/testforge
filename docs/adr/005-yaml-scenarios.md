# ADR-005: YAML Scenario Format

**Status:** Accepted  
**Date:** 2026-11-09  
**Deciders:** Winston (architect), User (owner)

---

## Context

The execution plan (M5, section 4) describes scenarios with the step types `send_message`, `upload_document`, `wait_for_interpretation`, `send_profile`, `expect_pattern` and `wait_for_response`, and a `validation` block with a `schema:` key.

The code written in M5–M9 uses other names (`send_document`, `wait`, `expect_response`). It was not checked against the plan's acceptance criteria until M9b. The five plan scenarios were written in M9b-5 in the code's format.

This ADR fixes the format and maps the plan's vocabulary to it, so that the plan's examples can be read against the code.

---

## Decision

Scenarios are YAML files (`.yml` or `.yaml`) in the code's vocabulary. The plan's step names map to existing actions (table below). No new step types are added for the plan's names.

- **Actions in use:** `send_message`, `send_document`, `wait`, `expect_response`.
- **`expect` block** on a step: `contains`, `not_contains`, `matches_regex`, `response_count`.
- **`capture: interpretation`** on a step stores the replies it reads, for the checks in `validation`.
- **`validation` block** at scenario level: what the run is checked for (`expectations`, `llm_judge`, `compliance`, `cost_budget_usd`, `performance_budget_sec`).

Interpretation checks (sections, forbidden phrases, disclaimer, time, judge rubric) live in a separate expectations file, referenced from `validation.expectations`.

### Mapping from the plan

| Plan | This format | Note |
|---|---|---|
| `id: SC-002` | `id: single_upload` | slug, not a number |
| `step: send_message` + `message:` | `action: send_message` + `text:` | |
| `step: upload_document` + `fixture:` | `action: send_document` + `document_path:` | |
| `step: send_profile` + `data:` | series of `send_message` (`/consent`, then one answer per question) | no new step type (M9b decision 1) |
| `step: wait_for_interpretation` + `timeout_sec` | `action: send_message` with the trigger (`/analyze`), `expect`, `capture: interpretation` | the trigger is an assumption until the real bot is checked (M9b-5) |
| `step: wait_for_response` | `action: expect_response` (checks replies) or `action: wait` (fixed delay) | |
| `expect: contains_all: [...]` | several `expect` steps, or `must_contain_sections` in the expectations file | one `contains` per `expect` |
| `expect: not_contains: [...]` | `not_contains: "..."` (one phrase), or `must_not_contain_phrases` in the expectations file | |
| `expect_pattern` | `expect.matches_regex` | |
| `expect: timeout_sec: 5` | not implemented; the scenario has one `timeout_sec` | per-expectation timeout waits for ADR-006 |
| `validation.schema: <file>` | `validation.expectations: <file>` | `schema` is rejected at load time with a clear error |
| `validation.llm_judge`, `compliance`, `cost_budget_usd`, `performance_budget_sec` | same names | M9b-1 |
| `verify_state` | in the action enum, not implemented | not in the plan's M5 list |

---

## Expectations File

`fixtures/expectations/*.yml`, loaded by `load_expectations`. Unknown top-level keys are rejected.

- `document_id` (required), `fixture_file` (optional path to the document)
- `document_summary`: what the document really says. The judge compares the interpretation with it
- `interpretation`: `must_contain_sections`, `must_not_contain_phrases`, `disclaimer_pattern`
- `performance`: `total_e2e_max_sec` is checked; per-stage keys are not visible through the Bot API
- `llm_judge`: `rubric` (the rubric name only; weights live in the rubric file)
- `vision_extraction`, `loinc_normalization`, `cost_budget`: accepted, reported as unverified

---

## Rationale

- **Four actions cover all five plan scenarios.** `send_profile` is a sequence of messages, because the bot asks one question at a time (its FSM). A separate action would duplicate `send_message`.
- **Checks sit next to the message they check.** Shared interpretation rules sit in one expectations file, so scenarios do not repeat them.
- **Unknown keys fail at load time** (`extra="forbid"`). A plan example with `schema:` or `contains_all:` stops with a message instead of being skipped silently.

---

## Consequences

- Plan examples cannot be pasted as they are. Use the table above.
- Known limits, tracked in `_bmad-output/deferred-work.md`: one `contains` per `expect`; no per-step timeout; the upload trigger (`/analyze`) is an assumption.
- Phase 1 (LLM-generated scenarios, per the plan) must produce this format. The `testforge plan` command (M11) validates it before a run.

---

## Alternatives Considered

### A1: Use the plan's vocabulary exactly

Add `upload_document`, `wait_for_interpretation`, `send_profile` and `expect_pattern` as new actions.

**Rejected:** each new action needs its own executor path and tests, and two of them duplicate existing actions.

### A2: Python DSL or JSON

**Rejected:** ADR-002 chose YAML for configuration. Scenarios must be readable and writable without Python (Phase 1).

---

## Related Decisions

- ADR-002: YAML config
- ADR-004: mock bot (canned responses as fixtures)
- ADR-006: receiving the bot's replies in real mode (pending)

---

## Code References

- `src/testforge/scenarios/models.py`: scenario, step and `ExpectCondition` models
- `src/testforge/scenarios/loader.py`: loader and `validate_scenario_files`
- `src/testforge/validation/schema.py`: expectations model and `load_expectations`
- `fixtures/scenarios/*.yml`: the five plan scenarios
- `tests/fixtures/scenarios/*.yaml`: regression fixtures

---

**Decision accepted:** 2026-11-09  
**Implemented in:** M5, M9b-1 (validation block), M9b-5 (plan scenarios)
