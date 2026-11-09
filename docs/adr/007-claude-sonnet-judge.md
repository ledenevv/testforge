# ADR-007: Claude Sonnet 4 Family as the Judge

**Status:** Accepted  
**Date:** 2026-11-09  
**Deciders:** Winston (architect), User (owner)

---

## Context

The judge scores the bot's interpretation against a rubric (`fixtures/rubrics/interpretation_quality_v1.yml`): clarity, medical appropriateness, Russian grammar and disclaimer compliance.

The plan (M9) picks Claude Sonnet 4 for Russian-language quality and budget. The plan estimates $0.023 per judge call. The run budget is $0.10–0.50.

---

## Decision

- **Provider:** Claude, through `AnthropicProvider` (ADR-003).
- **Model:** the LLM config's `model`. Default `claude-sonnet-4-6`, the newest Sonnet 4.x ID in the installed SDK.
  - The plain alias `claude-sonnet-4` (used in the plan and in the earlier default) is not in the SDK's model list and was not checked against the API. The default was changed in M9b-6.
- **Sampling:** `temperature` is not sent. SDK 1.0 removed the parameter, and API version 2026-10-21 returns 400 for it. The judge uses the model's default sampling. The `temperature: 0.0` setting of `LLMJudge` applies only to providers that accept it (OpenAI).
- **Pricing:** `AnthropicProvider.PRICING`. Sonnet is $3 input and $15 output per million tokens, matched through the `sonnet` fallback.
- **Cost record:** each judge call is written to `cost.json` (M9b-2, M9b-4).

---

## Rationale

- Russian-language quality is the plan's reason for choosing Claude.
- Sonnet fits the run budget. Opus costs five times as much per token ($15 and $75).
- A fixed rubric with per-dimension scores and reasons gives comparable results across runs, and a basis for the M10 baseline.

---

## Consequences

- **Scores vary more between runs,** because sampling is not fixed. Before the M10 thresholds are set, measure the spread: run one scenario three times in the first live run and record the per-dimension spread in `verification.json`.
- **Rubric quality is unknown until calibration.** The plan asks for 5–10 manual evaluations to tune it (plan risk table). That comes after the first live run.
- **Changing the model** needs a config change and a check of the price table (the fallback matches by family name).

---

## Alternatives Considered

### A1: Claude Opus

Better judgement at five times the price. **Rejected** as the default; set it in config if needed.

### A2: OpenAI

Available through the same provider interface. Not the default, because the plan prefers Claude for Russian.

---

## Related Decisions

- ADR-003: direct provider SDKs
- M9b-4: rubric-based judge
- `_bmad-output/deferred-work.md`: judge calls, temperature, first live run

---

## Code References

- `src/testforge/providers/anthropic.py`: provider and pricing table
- `src/testforge/judge/llm_judge.py`: judge
- `src/testforge/config.py`: LLM config default
- `fixtures/rubrics/interpretation_quality_v1.yml`: rubric

---

**Decision accepted:** 2026-11-09  
**Implemented in:** M9 (judge), M9b-4 (rubric), M9b-6 (default model)
