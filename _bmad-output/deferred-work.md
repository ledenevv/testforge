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

- **Real-bot polling.** Every step handler calls `bot.get_updates()` once after an optional `delay_sec`. With `RealTelegramBot` the first long-poll may return only the acknowledgement and miss the interpretation. The plan (M6) asks for polling until a pattern matches or a timeout expires. That needs a per-expectation timeout (`ExpectCondition.timeout_sec`) and a staging bot to validate against. Blocked by the transport decision in ADR-006: the Bot API cannot read the bot's replies, so polling it would not help. Do it after that decision, together with the first real-mode run.
- `Scenario.retry_on_failure` / `max_retries` are parsed but not applied by the executor (descriptions now say "Reserved").
- `Scenario.mode` is informational; the executor runs against whichever bot it is given. Bot selection belongs to the CLI (M11).
- Per-action required fields (`send_message` needs `text`, `wait` needs `duration_sec > 0`) are enforced only when the step runs, not when the scenario loads.
- ~~`load_scenarios_from_directory` defaults to `*.yaml` and skips `.yml`~~ Resolved in M9b-1: the directory loader reads both `.yml` and `.yaml`.
- ~~The "delay, get_updates, log, validate" sequence is repeated in three step handlers.~~ Resolved in M9b-2: `_check_replies`.
- `verify_conversation_flow` inspects only messages the test user sent, not bot replies. The executor now records replies in the trace (M9b-2), so the check can switch to them; not switched yet.
- `TelegramMessage` has no `caption`, so a bot reply that is only a caption cannot be validated.
- `ExpectCondition(contains="")` passes vacuously.
- Validation error messages always end with `...` after a 100-character excerpt.
- ~~`fixtures/test_data/sample_lab_report.pdf` is a one-line fake and `test_multi_step_scenario` writes it into the working tree if missing. Replace with real synthetic PDFs (plan section 4).~~ Resolved in M9b-5: the fake is removed, the test no longer writes it, and five synthetic PDFs are in `fixtures/documents/`.

## Deferred from: code review (2026-11-08) - Chunk 4: LLM judge

- No retry when the judge model returns malformed output; provider retries cover transport failures only. One bad reply fails that evaluation.
- System and user prompts are concatenated into one string because `LLMProvider.complete` has no system-role parameter. Fixing it needs a provider API extension.
- ~~Judge temperature is hard-coded to 0.3.~~ Resolved in M9b-4: a parameter, default 0.0.
- The raw judge reply is not stored, so a verdict cannot be re-read word for word. Scores, reasoning, threshold and cost are kept in `verification.json` and `judge_detailed.md` (M9b-4).
- ~~Trailing whitespace in `judge/models.py` and `tests/unit/test_judge.py`.~~ Both files rewritten in M9b-4.
- Not reproduced and not changed: a claim that the float mean can land just under the threshold. An exhaustive check of 0.1-step and half-point scores for the five-criterion mean found no affected case.

## REMINDER for the owner: bot pipeline cost is not measured

Decided 2026-11-08: TestForge does not check the cost of the ask-toby bot's own LLM calls (not observable through the Telegram Bot API, and ask-toby must not be changed). Only TestForge's own spend (the judge) is tracked. Revisit at a late stage: before the first `real`-mode run and when building the M11 reports. Estimating bot cost would need a source on the ask-toby side (a log or a command).

## Open items from M9b-3

- **ask-toby access.** The forbidden-phrase list should come from the ask-toby `medical-disclaimer` skill. `LedenevS/ask-toby` returned 404 for both the GitHub API and the web page, so the plan's list is used. Re-check when access exists and compare the lists.
- ~~**Judge not wired.** A scenario that asks for `llm_judge` gets a `warn` until M9b-4.~~ Resolved in M9b-4: the judge runs when a provider is given; without one the check is a `warn`.
- **interpretation.schema** is accepted but not checked. No schema registry yet.
- **Compliance on mixed replies.** A step that reads several replies at once (for example, upload confirmation plus interpretation) captures all of them, so the compliance and schema checks see the confirmation too. Keep the interpretation in its own step in M9b-5 scenarios.

## Blocker for real mode (found at M9b-6)

- **The Bot API cannot run a conversation with ask-toby.** Bots receive only messages sent to them, never their own replies, and never other bots' messages. `RealTelegramBot.send_message` speaks as the bot, so a real run would send `/start` as the bot to the test user instead of as the user to ask-toby. A real run through the current client would test nothing about ask-toby's answers. Mock mode is not affected.
- **Owner decision needed (ADR-006):** A) an MTProto client (Telethon) logged in as a dedicated test account, recommended; B) an MTProto bot account with Bot-to-Bot Communication Mode enabled on both bots (needs the ask-toby team to enable it). Both need new secrets and a new dependency. Do not run real mode until the choice is made.

## Open items from M9b-5

- **`/analyze` trigger is an assumption.** The mock answers with an interpretation only after `/analyze`; uploads are just acknowledged. The real ask-toby trigger is unknown. Check it before the first real-mode run. Three plan scenarios (`single_upload`, `batch_upload`, `conversation_qa`) and two regression fixtures (`document_upload`, `multi_step`) depend on it.
- **Mock texts not checked against ask-toby.** Interpretations, the batch interpretation, the three Q&A answers and the blood pressure prompts are ours. Compare them when the repository is reachable (same blocker as the forbidden-phrase list).
- **Live judge never called.** Tests use a stub judge with a fixed reply. The first live run (needs `TESTFORGE_LLM_API_KEY`) may show that the rubric needs calibration.
- ~~**Anthropic `temperature` is rejected by the SDK.**~~ Fixed after M9b-5. `anthropic` 2.6.0 has no `temperature` in `messages.create`, so every judge call raised `TypeError`. Found by mypy (`providers/anthropic.py:68`), reproduced against the installed SDK. Now `AnthropicProvider` does not send it. SDK 1.0 (2026-08-20) removed the argument; from API version 2026-10-21 the API returns 400 for it, even through `extra_body`. The judge therefore uses the model default (1.0), and the rubric's `temperature: 0.0` does not apply to Anthropic. Scores will vary more between runs: measure the spread on the first live run (same scenario, three runs) before setting M10 thresholds. Keeping `temperature` would need the `anthropic-version: 2023-06-01` header, which only older models accept; not done. `OpenAIProvider` still sends `temperature`; check it the same way before using it as a judge.
- **Per-run budget not enforced.** `per_run_max_usd` is validated in the config, but nothing sums the scenarios of one run. The cost check covers one scenario. Needed for M11 runs with several scenarios.
- **PDFs are not read by pytest.** They were checked by hand with pypdf. Regenerate with `uv run --no-project --with reportlab scripts/make_fixture_documents.py`.

## Lint and type debt (found at M9b-5)

- Ruff finds 207 issues in `src` and `tests` at M9b-4. 76 are RUF001: Russian text uses Cyrillic letters that look like Latin ones, so the rule flags most Russian strings. Recommended: ignore RUF001-RUF003 for this project, then fix the rest in one pass.
- Ruff format: 27 files at M9b-4 are not formatted. M9b-5 formats only the files it creates.
- mypy `--strict` on `src`: 30 errors at M9b-4. Not part of any CI yet.
- Before M9b-5, lint and mypy were never run per milestone. Add them to CI only after this pass.

## Open items from M9b-6

- **ADR-006 is proposed, not accepted.** Owner choice needed (see the blocker above).
- **Expectations 002–005 have no mock interpretation.** They describe a correct answer, so they can be run only against real replies or once per-document mock replies exist. Until then they are checked for loading and coverage only (`tests/unit/test_expectations_files.py`).
- **Judge model `claude-sonnet-4-6` is not checked against the live API.** The first live run shows it: a 404 means the ID is wrong. Change `llm.model` in the config.

## Plan divergence found in review (M5-M7, M9) - accepted into M9b

Decision: add milestone M9b before M10. Plan, decisions and acceptance criteria: `m9b-plan-conformance.md`. Rows below are closed as M9b items complete.

Review of Chunks 3 and 4 against `TESTFORGE_EXECUTION_PLAN.md` found that M5-M7 were built as a generic scenario runner plus assertion helpers, and M9 as a generic five-criterion judge, not as the plan describes. None of this is a defect in the code that exists; it is work the plan lists that does not exist yet.

| Plan item | State |
|-----------|-------|
| M5 `Scenario` fields `title`, `validation`, `cost_budget`, `performance_budget` | M9b-1 done: `title`, `priority`, `validation` with `cost_budget_usd` and `performance_budget_sec` (both > 0) |
| M5 step types `upload_document`, `wait_for_response`, `expect_pattern` | Implemented as `send_document`, `wait`, `expect_response` (+ `verify_state`, unimplemented) |
| M5 fixture-exists and budget > 0 validation | M9b-1 done: `validate_scenario_files` (checks `document_path` and `validation.expectations`); budgets must be > 0. Not yet called by a CLI: that is M11 `plan` |
| M5 five scenarios: onboarding, single_upload, batch_upload, conversation_qa, measurement | M9b-5 done: the five are in `fixtures/scenarios/*.yml`, with budgets and PDFs. The older fixtures moved to `tests/fixtures/scenarios/` |
| M6 `ExecutionTrace` (messages, responses, timings, cost per step) | M9b-2 done: per-step messages, replies, timings, pass/error. Cost per step not measured for the bot (owner decision) |
| M6 trace saved to `/runs/<id>/trace.json` | M9b-2 done: `RunStore` writes `runs/run-…/trace.json` and `latest.txt` |
| M7 schema validation (extract structured data, validate against expectations YAML) | M9b-3 done: required sections from expectations. No structured-data extraction: the interpretation is Markdown text |
| M7 compliance (disclaimer regex, forbidden phrases, Cyrillic > 80%) | M9b-3 done. Forbidden list taken from the plan (ask-toby skill unreachable, see below) |
| M7 cost verification (actual vs budget) | M9b-3 done: TestForge's spend against the budgets. Bot pipeline cost not measured (owner decision) |
| M7 performance verification (latency vs budget, per-stage) | M9b-3 done: total against budget, per-step breakdown. Per-stage limits listed as unverified |
| M7 findings saved to `/runs/<id>/verification.json` | M9b-3 done: `verification.json` in the run folder |
| CLI `testforge plan` / `run` / `verify` | Absent (M11) |
| M9 rubric YAML (`fixtures/rubrics/interpretation_quality_v1.yml`) and loader | M9b-4 done: rubric file, loader, weights sum check, sandboxed template |
| M9 dimensions clarity / medical_appropriateness / russian_grammar / disclaimer_compliance with weights 0.25 / 0.40 / 0.20 / 0.15 | M9b-4 done: the four plan dimensions, weights 0.25 / 0.40 / 0.20 / 0.15 |
| M9 per-dimension `min_score` and CRITICAL dimensions (medical_appropriateness 8.0, disclaimer_compliance 9.0) | M9b-4 done: minimums and critical flags; threshold 7.5 from the rubric; non-critical misses are warnings |
| M9 per-dimension `{score, reasoning}` plus `overall_assessment` in the model's JSON | M9b-4 done: required for every dimension, validated |
| M9 Jinja2 prompt template, Russian system prompt, document summary as input | M9b-4 done: template in the rubric file (sandboxed), Russian system prompt, `document_summary` from expectations |
| M9 Claude Sonnet 4 via `AnthropicProvider`, ADR-007 | Any `LLMProvider`; the model comes from the LLM config. ADR-007 comes in M9b-6 |
| M9 `/runs/<id>/judge_detailed.md` | M9b-4 done: written with every judge run |

Several of these (trace, budgets, baselines, reports) are consumed by M10 and M11, so they cannot be cleanly skipped. Decide whether to fold them into M10/M11 or add a milestone before M10.
