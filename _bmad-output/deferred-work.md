# Deferred work

## Deferred from: code review (2026-11-08) - Chunk 1: Config + Providers

- Hardcoded provider pricing tables will go stale (`providers/anthropic.py`, `openai.py`). Easy to update; wrong cost would be noticed.
- No rate-limit-specific handling (429 / Retry-After); the generic retry loop covers it for now.
- No structured logging of requests, retries and errors in providers.
- No model-name validation; an invalid model fails at the first API call with a clear provider error.
- Retry and timeout behaviour of `AnthropicProvider` / `OpenAIProvider` is not unit-tested (needs a mocked SDK client and a patched `asyncio.sleep`). TODOs are in `tests/unit/test_providers.py`.

## Deferred from: code review (2026-11-08) - Chunk 2: Telegram bots

- `MockTelegramBot.message_counter` / `update_counter` are unbounded ints (Python ints do not overflow; only matters if IDs are ever compared to Telegram's 32/64-bit range).
- `RealTelegramBot.send_document` always sends `application/octet-stream` instead of guessing the MIME type.
- No 429 / rate-limit handling in `RealTelegramBot._api_request`.
- No structured logging in either bot.
- `MockTelegramBot._load_responses` silently skips fixture files with invalid JSON (bare `except Exception`).
- Tests assert exact Russian strings, so they break on wording changes.

## Deferred from: code review (2026-11-08) - Chunk 3: Scenarios, Executor, Verifier

- **Real-bot polling.** Every step handler calls `bot.get_updates()` once after an optional `delay_sec`. With `RealTelegramBot` the first long-poll may return only the acknowledgement and miss the interpretation. The plan (M6) asks for polling until a pattern matches or a timeout expires. That needs a per-expectation timeout (`ExpectCondition.timeout_sec`) and a staging bot to validate against. Do it together with first real-mode runs.
- `Scenario.retry_on_failure` / `max_retries` are parsed but not applied by the executor (descriptions now say "Reserved").
- `Scenario.mode` is informational; the executor runs against whichever bot it is given. Bot selection belongs to the CLI (M11).
- Per-action required fields (`send_message` needs `text`, `wait` needs `duration_sec > 0`) are enforced only when the step runs, not when the scenario loads.
- `load_scenarios_from_directory` defaults to `*.yaml` and skips `.yml`; the plan's examples use `.yml`. Settle the extension when the CLI is built.
- The "delay, get_updates, log, validate" sequence is repeated in three step handlers.
- `verify_conversation_flow` inspects only messages the test user sent, not bot replies. Checking replies requires the executor to record them (see ExecutionTrace below).
- `TelegramMessage` has no `caption`, so a bot reply that is only a caption cannot be validated.
- `ExpectCondition(contains="")` passes vacuously.
- Validation error messages always end with `...` after a 100-character excerpt.
- `fixtures/test_data/sample_lab_report.pdf` is a one-line fake and `test_multi_step_scenario` writes it into the working tree if missing. Replace with real synthetic PDFs (plan section 4).

## Deferred from: code review (2026-11-08) - Chunk 4: LLM judge

- No retry when the judge model returns malformed output; provider retries cover transport failures only. One bad reply fails that evaluation.
- System and user prompts are concatenated into one string because `LLMProvider.complete` has no system-role parameter. Fixing it needs a provider API extension.
- Judge temperature is hard-coded to 0.3.
- `JudgeVerdict` keeps no raw model response and no threshold, so a verdict cannot be audited after the fact. This belongs with the detailed-report work below.
- Trailing whitespace in `judge/models.py` and `tests/unit/test_judge.py`.
- Not reproduced and not changed: a claim that the float mean can land just under the threshold. An exhaustive check of 0.1-step and half-point scores for the five-criterion mean found no affected case.

## Plan divergence found in review (M5-M7, M9) - needs a decision

Review of Chunks 3 and 4 against `TESTFORGE_EXECUTION_PLAN.md` found that M5-M7 were built as a generic scenario runner plus assertion helpers, and M9 as a generic five-criterion judge, not as the plan describes. None of this is a defect in the code that exists; it is work the plan lists that does not exist yet.

| Plan item | State |
|-----------|-------|
| M5 `Scenario` fields `title`, `validation`, `cost_budget`, `performance_budget` | Absent (`description`, `timeout_sec`, `tags`, `variables`, `mode` exist) |
| M5 step types `upload_document`, `wait_for_response`, `expect_pattern` | Implemented as `send_document`, `wait`, `expect_response` (+ `verify_state`, unimplemented) |
| M5 fixture-exists and budget > 0 validation | Absent |
| M5 five scenarios: onboarding, single_upload, batch_upload, conversation_qa, measurement | Not authored; fixtures are smoke_test, profile_setup, document_upload, multi_step, env_var_test |
| M6 `ExecutionTrace` (messages, responses, timings, cost per step) | Absent; `ScenarioResult` has counts and logs only |
| M6 trace saved to `/runs/<id>/trace.json` | Absent; no `run_id`, nothing written to disk |
| M7 schema validation (extract structured data, validate against expectations YAML) | Absent |
| M7 compliance (disclaimer regex, forbidden phrases, Cyrillic > 80%) | Absent |
| M7 cost verification (actual vs budget) | Absent |
| M7 performance verification (latency vs budget, per-stage) | Only `verify_duration_within` on total duration |
| M7 findings saved to `/runs/<id>/verification.json` | Absent |
| CLI `testforge plan` / `run` / `verify` | Absent (M11) |
| M9 rubric YAML (`fixtures/rubrics/interpretation_quality_v1.yml`) and loader | Absent; `JudgeCriteria` is five booleans |
| M9 dimensions clarity / medical_appropriateness / russian_grammar / disclaimer_compliance with weights 0.25 / 0.40 / 0.20 / 0.15 | Built instead: correctness, helpfulness, safety, language_quality, relevance, unweighted mean |
| M9 per-dimension `min_score` and CRITICAL dimensions (medical_appropriateness 8.0, disclaimer_compliance 9.0) | Absent; a single overall threshold (default 7.0, plan says 7.5) |
| M9 per-dimension `{score, reasoning}` plus `overall_assessment` in the model's JSON | Flat `<name>_score` keys and one `reasoning` string |
| M9 Jinja2 prompt template, Russian system prompt, document summary as input | `str.format`, English prompt, `user_query` / `bot_response` / `context` |
| M9 Claude Sonnet 4 via `AnthropicProvider`, ADR-007 | Any `LLMProvider`; no default model, no ADR-007 |
| M9 `/runs/<id>/judge_detailed.md` | Absent |

Several of these (trace, budgets, baselines, reports) are consumed by M10 and M11, so they cannot be cleanly skipped. Decide whether to fold them into M10/M11 or add a milestone before M10.
