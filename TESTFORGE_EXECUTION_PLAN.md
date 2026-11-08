# TestForge: Final Execution Plan
**Project:** TestForge для ask-toby  
**Architect:** Winston  
**Date:** 2026-11-08  
**Status:** ✅ Ready to Execute — Owner Approved  
**Timeline:** 3 weeks (comfortable pace, 60-70h)

---

## 1. Executive Summary

**TestForge** — внешний CLI-инструмент для E2E-тестирования Telegram-бота ask-toby через чёрный ящик (Telegram Bot API). Валидирует многоуровневый LLM-пайплайн (vision → LOINC → distillation → interpretation), схемы данных, compliance (дисклеймер, запрещённые фразы), качество на русском языке (LLM-as-judge), стоимость и производительность.

### Принятые решения (на основе ваших ответов)

| Вопрос | Решение | Влияние на план |
|--------|---------|----------------|
| **Staging bot** | Будет предложен позже | Phase 0 включает **mock mode** для разработки + **real bot mode** для финального E2E (когда бот появится) |
| **Test data** | Сгенерировать fake | Синтетические русские лабораторные бланки (5-10 PDFs), реалистичные но не реальные |
| **CI platform** | GitHub Actions, on-demand | Workflow для ручного запуска (`workflow_dispatch`), не на каждый PR |
| **Secrets** | No secrets management | API keys через `.env` локально; в CI — через GitHub Secrets (стандартный подход) |
| **LLM-as-judge** | Claude Sonnet | Лучшее качество оценки русского языка; дороже GPT-6.1 Sol, но в рамках бюджета |
| **Budget** | $0.10-0.50/run | **2 сценария**: onboarding + batch upload = ~$0.25-0.40 (детали ниже) |
| **Baselines** | Phase 0 establishes | Первый запуск сохраняет метрики как reference; последующие сравнивают с ними |
| **Failure handling** | Pass + log + alert | CI не падает, но логирует регрессию и генерирует alert-файл для ревью |
| **Timeline** | 3 недели, comfortable | 11 milestones, каждый с чёткими критериями приёмки |

---

## 2. Budget Allocation ($0.25-0.40 per CI run)

> **Примечание после код-ревью:** стоимость LLM-вызовов самого бота ask-toby (строки «bot pipeline» ниже) не проверяется: через Bot API она не видна. Учитываются только траты TestForge (судья). К вопросу вернуться на поздних этапах. См. `_bmad-output/m9b-plan-conformance.md`.

### 2.1 Cost Breakdown per Scenario

**Scenario 1: Onboarding + Single Document Upload**
| Stage | Model (ask-toby) | Tokens (estimate) | Cost |
|-------|------------------|-------------------|------|
| Vision extraction | Gemini 3 Flash | 10k in / 2k out | $0.005 |
| LOINC normalization | Gemini 3 Flash | 3k in / 1k out | $0.002 |
| Distillation | Grok 4.7 | 5k in / 1k out | $0.003 |
| Interpretation | GPT-6.1 Sol | 12k in / 3k out | $0.10 |
| **Subtotal (bot pipeline)** | | | **$0.11** |
| LLM-as-judge (TestForge) | Claude Sonnet 4 | 5k in / 0.8k out | $0.023 |
| **Total Scenario 1** | | | **$0.133** |

**Scenario 2: Batch Upload (3 documents)**
| Stage | Model | Tokens | Cost |
|-------|-------|--------|------|
| Vision extraction (×3) | Gemini 3 Flash | 30k in / 6k out | $0.015 |
| LOINC (×3) | Gemini 3 Flash | 9k in / 3k out | $0.006 |
| Distillation (batch) | Grok 4.7 | 15k in / 3k out | $0.009 |
| Interpretation (batch) | GPT-6.1 Sol | 30k in / 8k out | $0.26 |
| **Subtotal (bot pipeline)** | | | **$0.29** |
| LLM-as-judge | Claude Sonnet 4 | 8k in / 1.2k out | $0.036 |
| **Total Scenario 2** | | | **$0.326** |

**CI Budget:**
- **2 scenarios:** $0.133 + $0.326 = **$0.459** ✅ (в рамках $0.50)
- **Fallback (1 scenario only):** $0.133 (если нужно сэкономить)

### 2.2 Budget Controls

**Hard limits в config:**
```yaml
cost_limits:
  per_scenario_max_usd: 0.20  # Fail scenario if exceeded
  per_run_max_usd: 0.50       # Fail entire run if exceeded
  alert_threshold_usd: 0.40   # Warn if approaching limit
```

**Cost tracking:**
- Каждый LLM-вызов логируется: model, tokens_in, tokens_out, cost_usd, duration_sec
- Артефакт `/runs/<id>/cost.json` с breakdown по этапам
- CI выводит summary: "Total cost: $0.42 / $0.50 budget (84% used)"

---

## 3. Phase 0 Architecture (Updated)

### 3.1 Dual-Mode Design

**Mock Mode** (для разработки TestForge без staging bot):
```
TestForge CLI
    ↓
Mock Telegram Bot (in-memory)
    ↓
Canned responses (fixtures/mock_responses/)
    ↓
Verifier validates against expected outputs
```

**Real Bot Mode** (когда staging bot доступен):
```
TestForge CLI
    ↓
Telegram Bot API client
    ↓
ask-toby staging bot (real LLM pipeline)
    ↓
Verifier validates responses
    ↓
LLM-as-judge (Claude Sonnet 4)
```

### 3.2 Components (Final)

```
┌─────────────────────────────────────────────────────────┐
│                   TestForge CLI                         │
│   init · plan · generate · run · verify · report       │
└───────────────────────┬─────────────────────────────────┘
                        │
        ┌───────────────┴───────────────────┐
        ▼                                   ▼
┌─────────────────┐               ┌─────────────────┐
│  Config Manager │               │  LLM Provider   │
│  - Bot target   │               │  - Anthropic    │
│  - Mock/Real    │               │    (Claude)     │
│  - Budget       │               │  - OpenAI       │
│  - Fixtures     │               │  - Mock (tests) │
└─────────────────┘               └─────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
          ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
          │  Scenario        │  │  Executor        │  │  Verifier        │
          │  Designer (stub) │  │  Agent           │  │  Agent           │
          │                  │  │                  │  │                  │
          │ - Loads 5        │  │ - Mock bot       │  │ - Schema val     │
          │   hardcoded      │  │   (in-memory)    │  │ - Compliance     │
          │   scenarios      │  │ - Real bot       │  │ - LLM-judge      │
          │ - YAML format    │  │   (Bot API)      │  │   (Claude)       │
          │                  │  │ - Upload docs    │  │ - Cost check     │
          │ (Phase 1: LLM-   │  │ - Poll responses │  │ - Perf metrics   │
          │  powered gen)    │  │                  │  │ - Baseline comp  │
          └──────────────────┘  └──────────────────┘  └──────────────────┘
                    │                      │                      │
                    └──────────────────────┼──────────────────────┘
                                           ▼
                                  ┌─────────────────┐
                                  │  Artifact Store │
                                  │  /runs/<id>/    │
                                  │  - trace.json   │
                                  │  - cost.json    │
                                  │  - judge.md     │
                                  │  - baseline.yml │
                                  │  - report.html  │
                                  │  - alert.txt    │
                                  └─────────────────┘
```

---

## 4. Synthetic Test Data (Fake Lab Reports)

### 4.1 Documents to Generate (5 PDFs for Phase 0)

**Requirements:**
- Realistic Russian lab report forms (Invitro/Gemotest style)
- No real PHI (fake names, dates, IDs)
- Cover main test types ask-toby handles

**Document List:**

1. **`lab_report_001_biochem_normal.pdf`**
   - Biochemistry panel (АЛТ, АСТ, общий холестерин, глюкоза)
   - All values within normal reference ranges
   - Source lab: "Инвитро"
   - Date: 2026-10-15
   - Patient: Иванов Иван Иванович (fake)

2. **`lab_report_002_cbc_anemia.pdf`**
   - Complete blood count (гемоглобин, эритроциты, лейкоциты, тромбоциты)
   - Hemoglobin below normal (anemia flag)
   - Source lab: "Гемотест"
   - Date: 2026-10-20

3. **`lab_report_003_thyroid_normal.pdf`**
   - Thyroid panel (ТТГ, Т3 свободный, Т4 свободный)
   - All within normal
   - Source lab: "Инвитро"
   - Date: 2026-11-01

4. **`lab_report_004_mixed_flags.pdf`**
   - Mixed panel: liver enzymes + lipid profile
   - 2 values flagged high (cholesterol, ALT)
   - Source lab: "Гемотест"
   - Date: 2026-11-05

5. **`clinical_note_005_ecg.pdf`**
   - ECG interpretation (textual, not lab values)
   - Type: `clinical_notes` (tests ask-toby's `notes` field extraction)
   - Date: 2026-11-03

**Generation Method:**
- Use LLM (Claude Sonnet) to generate realistic Russian medical text
- Render to PDF with Python (reportlab or weasyprint)
- Store in `fixtures/documents/`
- Commit to repo (version-controlled test data)

### 4.2 Expected Outputs (Validation Templates)

**`fixtures/expectations/lab_report_001.yml`:**
```yaml
document_id: lab_report_001
fixture_file: lab_report_001_biochem_normal.pdf

vision_extraction:
  schema: LabExtractionSchema
  required_fields: [tests, source_lab, lab_date]
  tests:
    min_count: 4
    expected_names: ["АЛТ", "АСТ", "Холестерин", "Глюкоза"]
  source_lab: "Инвитро"
  lab_date: "2026-10-15"

loinc_normalization:
  expected_mappings:
    "АЛТ": "1742-6"
    "АСТ": "1920-8"
    "Холестерин общий": "2093-3"
    "Глюкоза": "2345-7"

interpretation:
  schema: InterpretationResponse
  must_contain_sections: 
    - "Резюме"
    - "Ключевые моменты"
    - "Что обсудить с врачом"
  must_not_contain_phrases:
    - "диагноз"
    - "диагностирую"
    - "назначаю"
    - "рекомендую лечение"
    - "рекомендую принимать"
  disclaimer_pattern: "Это информационный разбор.*не заменяет консультацию врача"

llm_judge:
  rubric: interpretation_quality_v1
  model: claude-sonnet-4
  dimensions:
    clarity: {min_score: 7.0, weight: 0.25}
    medical_appropriateness: {min_score: 8.0, weight: 0.40}
    russian_grammar: {min_score: 7.0, weight: 0.20}
    disclaimer_compliance: {min_score: 9.0, weight: 0.15}
  overall_pass_threshold: 7.5

cost_budget:
  vision_extraction_max: 0.01
  loinc_normalization_max: 0.005
  distillation_max: 0.005
  interpretation_max: 0.15
  total_max: 0.20

performance:
  upload_to_extraction_start_max_sec: 10
  extraction_duration_max_sec: 20
  interpretation_duration_max_sec: 60
  total_e2e_max_sec: 120
```

---

## 5. Baseline Establishment (Phase 0)

### 5.1 First Run Behavior

**When no baseline exists** (`/runs/baseline.yml` not found):
1. Run scenarios normally
2. Collect metrics: cost, latency, LLM-judge scores
3. **Save as baseline:** `/runs/baseline.yml`
4. Report: "✓ Baseline established (first run)"

**`baseline.yml` format:**
```yaml
baseline_id: baseline-20261108-153022
created_at: "2026-11-08T15:30:22Z"
testforge_version: "0.1.0"
ask_toby_version: "unknown"  # Will add version detection in Phase 1

scenarios:
  SC-001:  # Onboarding + single upload
    cost_usd: 0.133
    duration_sec: 68
    llm_judge_scores:
      clarity: 8.2
      medical_appropriateness: 8.8
      russian_grammar: 8.0
      disclaimer_compliance: 10.0
      overall: 8.5
    
  SC-002:  # Batch upload
    cost_usd: 0.326
    duration_sec: 142
    llm_judge_scores:
      overall: 8.3

meta:
  total_runs: 1
  last_updated: "2026-11-08T15:30:22Z"
```

### 5.2 Subsequent Runs (Regression Detection)

**When baseline exists:**
1. Run scenarios
2. Compare metrics to baseline
3. **Regression thresholds:**
   - Cost: +20% → warn
   - Latency: +30% → warn
   - LLM-judge overall: -1.0 point → warn
   - Any dimension < critical threshold (8.0 for medical_appropriateness, 9.0 for disclaimer) → **alert**

**Failure handling (per your decision):**
- **Do not fail CI** — always exit 0
- **Log warnings** to stdout
- **Generate alert file:** `/runs/<id>/ALERT.txt` with human-readable summary
- **Report includes diff:** baseline vs. current

**Alert example (`/runs/run-123/ALERT.txt`):**
```
⚠️ REGRESSION DETECTED — HUMAN REVIEW REQUIRED

Run ID: run-20261110-094531
Compared to baseline: baseline-20261108-153022

Scenario SC-001 (Onboarding + single upload):
  ✓ Cost: $0.138 (+3.8% vs baseline $0.133) — PASS
  ✓ Duration: 72s (+5.9% vs baseline 68s) — PASS
  ⚠️ LLM-judge overall: 7.3 (-1.2 vs baseline 8.5) — REGRESSION
      - Medical appropriateness: 7.0 (-1.8) — BELOW CRITICAL (8.0)
      - Clarity: 7.8 (-0.4)
      - Russian grammar: 7.5 (-0.5)
      - Disclaimer compliance: 9.5 (-0.5)

Possible causes:
  - ask-toby prompt change
  - Model update (GPT-6.1 → GPT-6.2?)
  - LLM-as-judge model drift

Action required:
  1. Review LLM-judge detailed report: /runs/run-123/judge_detailed.md
  2. Check ask-toby recent changes (git log since baseline date)
  3. Re-run test to confirm (flakiness check)
  4. If confirmed, investigate prompt or update baseline
```

---

## 6. Phase 0 Implementation Plan (11 Milestones, 3 Weeks)

### Week 1: Foundation (M1-M4)

#### M1: Project Setup (Day 1, 4h)
**Tasks:**
- [ ] Create repo: `testforge/`
- [ ] `pyproject.toml` (Python 3.12+, dependencies: typer, pydantic, httpx, pytest, structlog)
- [ ] Directory structure: `src/testforge/`, `fixtures/`, `config/`, `tests/`, `docs/`
- [ ] `README.md` (install, quickstart)
- [ ] `.env.example` (TESTFORGE_BOT_TOKEN, TESTFORGE_LLM_API_KEY, TESTFORGE_MODE=mock|real)
- [ ] `.gitignore` (`.env`, `__pycache__`, `.pytest_cache`, `runs/`)
- [ ] ADR-001: Why external tool (not integrated into ask-toby)

**Acceptance:**
```bash
git clone <testforge-repo>
cd testforge
python -m venv .venv && source .venv/bin/activate  # or uv venv
pip install -e .
testforge --help  # Shows commands
```

---

#### M2: Configuration System (Day 1-2, 6h)
**Tasks:**
- [ ] Pydantic models: `TestConfig`, `BotTarget`, `LLMConfig`, `Scenario`, `CostLimits`
- [ ] YAML config loader + env variable substitution (`${TESTFORGE_BOT_TOKEN}`)
- [ ] Validation: required fields, type checks, budget > 0
- [ ] Example configs: `config/examples/mock-bot.yaml`, `config/examples/staging-bot.yaml`
- [ ] CLI command: `testforge config validate`

**Config example (`config/examples/mock-bot.yaml`):**
```yaml
mode: mock  # or 'real'

bot:
  name: "ask-toby (mock)"
  token: "${TESTFORGE_BOT_TOKEN}"  # Not used in mock mode
  test_user_id: 12345678

llm:
  provider: anthropic
  api_key: "${TESTFORGE_LLM_API_KEY}"
  model: claude-sonnet-4
  temperature: 0.3
  max_tokens: 4096

cost_limits:
  per_scenario_max_usd: 0.20
  per_run_max_usd: 0.50
  alert_threshold_usd: 0.40

scenarios_dir: fixtures/scenarios
fixtures_dir: fixtures/documents
expectations_dir: fixtures/expectations
baseline_file: runs/baseline.yml
```

**Acceptance:**
```bash
testforge config validate --config config/examples/mock-bot.yaml
# ✓ Configuration valid

testforge config validate --config config/examples/invalid.yaml
# ✗ Error: Missing required field 'bot.token'
```

**ADR:** ADR-002: YAML vs. TOML (YAML chosen for human-readability, consistency with ask-toby)

---

#### M3: LLM Provider Abstraction (Day 2-3, 8h)
**Tasks:**
- [ ] `LLMProvider` base class (abstract): `complete(prompt, max_tokens) -> LLMResponse`
- [ ] `LLMResponse` model: `text: str, tokens_in: int, tokens_out: int, cost_usd: float, duration_sec: float`
- [ ] `AnthropicProvider` (Claude Sonnet 4)
- [ ] `OpenAIProvider` (for future, not used in Phase 0)
- [ ] `MockProvider` (returns canned responses from fixtures)
- [ ] Token counting (tiktoken for OpenAI, Anthropic API for Claude)
- [ ] Cost calculation (provider-specific pricing)
- [ ] Retry logic with exponential backoff (3 retries, max 30s)
- [ ] Unit tests with `MockProvider`

**Acceptance:**
```python
# Integration test (requires API key)
from testforge.providers import AnthropicProvider
from testforge.config import LLMConfig

config = LLMConfig(
    provider="anthropic",
    api_key=os.getenv("TESTFORGE_LLM_API_KEY"),
    model="claude-sonnet-4",
    temperature=0.3,
    max_tokens=100
)
provider = AnthropicProvider(config)
response = await provider.complete("Say 'Привет' in Russian")

assert "Привет" in response.text
assert response.tokens_in > 0
assert response.tokens_out > 0
assert response.cost_usd > 0
assert response.duration_sec > 0
```

**ADR:** ADR-003: Direct provider SDKs vs. LiteLLM (chose direct for simplicity)

---

#### M4: Mock Telegram Bot (Day 3-4, 8h)
**Tasks:**
- [ ] `MockTelegramBot` class (in-memory, no network)
- [ ] Implements: `send_message(text)`, `send_document(file_path)`, `get_updates()`
- [ ] Canned responses from `fixtures/mock_responses/`
- [ ] Supports scenarios: `/start`, `/consent`, profile setup, document upload, interpretation
- [ ] Response templates (Jinja2): parametrized by fixture metadata
- [ ] Unit tests: send message → receive expected response

**Mock response example (`fixtures/mock_responses/start.json`):**
```json
{
  "trigger": {"command": "/start"},
  "response": {
    "text": "👋 Привет! Этот бот анализирует медицинские документы.\n\nПеред началом работы прочитайте, пожалуйста, информацию о том, что я делаю и как храню данные.\n\n/consent — Согласиться и продолжить",
    "delay_sec": 0.5
  }
}
```

**Acceptance:**
```python
from testforge.telegram import MockTelegramBot

bot = MockTelegramBot(responses_dir="fixtures/mock_responses")
await bot.send_message("/start")
response = await bot.get_updates()

assert "Этот бот анализирует медицинские документы" in response.text
```

**ADR:** ADR-004: Mock bot for Phase 0 (real bot in M8)

---

### Week 2: Execution & Verification (M5-M8)

#### M5: Scenario Schema & Loader (Day 5-6, 8h)
**Tasks:**
- [ ] `Scenario` Pydantic model (id, title, steps, validation, cost_budget, performance_budget)
- [ ] `ScenarioStep` model (step type: send_message, upload_document, wait_for_response, expect_pattern)
- [ ] YAML loader + validator
- [ ] **Author 5 scenarios manually** (hardcoded, not LLM-generated):
  1. `onboarding.yml` — /start → /consent → profile → menu
  2. `single_upload.yml` — upload 1 doc → interpretation
  3. `batch_upload.yml` — upload 3 docs → interpretation
  4. `conversation_qa.yml` — upload → 3-turn Q&A
  5. `measurement.yml` — record blood pressure
- [ ] Scenario validation: all referenced fixtures exist, budgets > 0

**Scenario example (`fixtures/scenarios/single_upload.yml`):**
```yaml
id: SC-002
title: "Single document upload and interpretation"
description: "User uploads one biochemistry lab report, receives interpretation with disclaimer"
priority: P0
tags: [smoke, interpretation, cost-critical]

steps:
  - step: send_message
    message: "/start"
    expect:
      contains: "Этот бот анализирует"
      timeout_sec: 5
  
  - step: send_message
    message: "/consent"
    expect:
      contains: "Теперь заполним профиль"
  
  - step: send_profile
    data:
      sex: "m"
      birth_year: 1985
      height_cm: 180
      weight_kg: 75
      chronic_conditions: ""
      medications: ""
    expect:
      contains: "Профиль сохранён"
  
  - step: upload_document
    fixture: lab_report_001_biochem_normal.pdf
    expect:
      contains: "Документ получен"
      timeout_sec: 15
  
  - step: wait_for_interpretation
    timeout_sec: 90
    expect:
      contains_all:
        - "Резюме"
        - "Ключевые моменты"
        - "Что обсудить с врачом"
      not_contains:
        - "диагноз"
        - "назначаю"

validation:
  schema: fixtures/expectations/lab_report_001.yml
  llm_judge: true
  compliance: true
  cost_budget_usd: 0.20
  performance_budget_sec: 120
```

**Acceptance:**
```bash
testforge plan --scenarios fixtures/scenarios/*.yml
# ✓ Loaded 5 scenarios
# ✓ All fixtures exist
# ✓ Total budget: $0.60
```

**ADR:** ADR-005: YAML scenario format (human-authored in Phase 0, LLM-generated in Phase 1)

---

#### M6: Executor Agent (Day 6-8, 12h)
**Tasks:**
- [ ] `ExecutorAgent` class
- [ ] `ExecutionTrace` model (records all messages, responses, timings, costs)
- [ ] Step executors:
  - `send_message` → calls bot.send_message()
  - `upload_document` → loads fixture, calls bot.send_document()
  - `wait_for_interpretation` → polls bot.get_updates() until pattern match or timeout
- [ ] Pattern matching (regex + contains/not_contains checks)
- [ ] Timeout handling
- [ ] Cost tracking per step (sum of LLM calls in bot's pipeline)
- [ ] **Mock mode implementation:** use MockTelegramBot
- [ ] Save execution trace to `/runs/<run_id>/trace.json`

**Acceptance:**
```bash
testforge run --scenario fixtures/scenarios/single_upload.yml --mode mock
# [Step 1/6] Send /start → ✓ Matched "Этот бот" in 0.5s
# [Step 2/6] Send /consent → ✓ Matched "профиль" in 0.3s
# [Step 3/6] Send profile → ✓ Matched "сохранён" in 0.8s
# [Step 4/6] Upload lab_report_001 → ✓ Matched "получен" in 1.2s
# [Step 5/6] Wait for interpretation → ✓ Matched all required sections in 3.5s (mock)
# [Step 6/6] Validation pending
# 
# ✓ Execution complete
# Trace saved: /runs/run-20261111-103022/trace.json
```

---

#### M7: Verifier Agent — Schema & Compliance (Day 9-10, 10h)
**Tasks:**
- [ ] `VerifierAgent` class
- [ ] **Schema validation:**
  - Extract structured data from bot messages (JSON blocks, tables)
  - Validate against Pydantic schemas (from expectations YAML)
  - Report: field missing, type mismatch, value out of range
- [ ] **Compliance checks:**
  - Disclaimer present (regex match)
  - No forbidden phrases (list from ask-toby's `medical-disclaimer` skill)
  - Russian language (basic check: Cyrillic characters > 80%)
- [ ] **Cost verification:**
  - Compare actual cost (from trace) vs. budget (from scenario)
  - Report: under budget / over budget / alert threshold
- [ ] **Performance verification:**
  - Compare actual latency vs. budget
  - Per-stage breakdown (if available from trace)
- [ ] Save findings to `/runs/<run_id>/verification.json`

**Acceptance:**
```bash
testforge verify --run-id run-20261111-103022
# ✓ Schema validation: PASS
#   - InterpretationResponse valid
#   - All required fields present
# ✓ Compliance: PASS
#   - Disclaimer present
#   - No forbidden phrases detected
#   - Russian language confirmed
# ✓ Cost: PASS
#   - Actual: $0.133 < Budget: $0.20
# ✓ Performance: PASS
#   - Total: 68s < Budget: 120s
# 
# Pending: LLM-judge evaluation (run with --llm-judge)
```

---

#### M8: Real Telegram Bot Client (Day 11-12, 10h)
**Tasks:**
- [ ] `RealTelegramBot` class (uses Telegram Bot API)
- [ ] Async wrapper: `httpx.AsyncClient` for API calls
- [ ] Methods: `send_message`, `send_document`, `get_updates` (long polling)
- [ ] Update offset tracking (continue from last seen update)
- [ ] Response parsing: extract text from bot's messages
- [ ] Timeout handling (wait up to N seconds for response)
- [ ] Error handling: API errors, rate limits, network failures
- [ ] **Conditional execution:** only runs if `mode: real` and `TESTFORGE_BOT_TOKEN` is set
- [ ] Unit tests with mocked httpx responses

**Note:** Real bot testing **deferred until staging bot available** — но код готов, можно запустить когда бот появится.

**Acceptance (when staging bot ready):**
```bash
export TESTFORGE_BOT_TOKEN=<staging_token>
export TESTFORGE_TEST_USER_ID=<your_telegram_id>
export TESTFORGE_MODE=real

testforge run --scenario fixtures/scenarios/single_upload.yml --mode real
# [Step 1/6] Send /start → ✓ Bot responded in 1.2s
# [Step 2/6] Send /consent → ✓ Bot responded in 0.8s
# ...
# [Step 5/6] Wait for interpretation → ✓ Received in 42s
# 
# ✓ Execution complete (real bot)
# Trace saved: /runs/run-20261115-140533/trace.json
# Cost: $0.14 (actual bot LLM calls)
```

**ADR:** ADR-006: Long polling vs. webhooks (polling chosen for simplicity)

---

### Week 3: LLM-as-Judge & Integration (M9-M11)

#### M9: LLM-as-Judge Evaluation (Day 13-14, 10h)
**Tasks:**
- [ ] `LLMJudge` class
- [ ] Rubric YAML schema (`fixtures/rubrics/interpretation_quality_v1.yml`)
- [ ] Prompt template (Jinja2):
  - System: "Вы эксперт по оценке медицинских разборов"
  - User: document summary + bot interpretation + rubric dimensions
  - Response format: JSON with scores + reasoning
- [ ] Claude Sonnet 4 integration (via AnthropicProvider)
- [ ] Score extraction & validation (0-10 scale, weighted average)
- [ ] Pass/fail logic: overall ≥ threshold, critical dimensions ≥ min
- [ ] Save detailed report: `/runs/<run_id>/judge_detailed.md`

**Rubric (`fixtures/rubrics/interpretation_quality_v1.yml`):**
```yaml
rubric_id: interpretation_quality_v1
version: 1.0
model: claude-sonnet-4

dimensions:
  - id: clarity
    name: "Ясность и структурированность"
    description: "Текст легко читается, логичная структура, нет жаргонизмов без объяснения"
    weight: 0.25
    min_score: 7.0
    
  - id: medical_appropriateness
    name: "Медицинская корректность"
    description: "Интерпретация соответствует показателям, нет диагнозов/назначений, корректные референсы"
    weight: 0.40
    min_score: 8.0  # Critical
    
  - id: russian_grammar
    name: "Качество русского языка"
    description: "Грамматика, орфография, пунктуация, естественность формулировок"
    weight: 0.20
    min_score: 7.0
    
  - id: disclaimer_compliance
    name: "Соответствие дисклеймеру"
    description: "Дисклеймер присутствует и корректен, нет ложных ожиданий"
    weight: 0.15
    min_score: 9.0  # Critical

overall_pass_threshold: 7.5

prompt_template: |
  Вы эксперт по оценке качества информационных медицинских разборов лабораторных анализов.
  
  **Задача:** Оцените разбор бота по четырём критериям (0-10 баллов каждый).
  
  **Документ пациента:**
  {document_summary}
  
  **Разбор бота:**
  {bot_interpretation}
  
  **Критерии оценки:**
  {% for dim in dimensions %}
  {{ loop.index }}. **{{ dim.name }}** (вес {{ dim.weight }}):
     {{ dim.description }}
  {% endfor %}
  
  Ответьте СТРОГО в формате JSON:
  {
    "clarity": {"score": <0-10>, "reasoning": "<1-2 предложения>"},
    "medical_appropriateness": {"score": <0-10>, "reasoning": "<1-2 предложения>"},
    "russian_grammar": {"score": <0-10>, "reasoning": "<1-2 предложения>"},
    "disclaimer_compliance": {"score": <0-10>, "reasoning": "<1-2 предложения>"},
    "overall_assessment": "<общее впечатление, 2-3 предложения>"
  }
```

**Acceptance:**
```bash
testforge verify --run-id run-20261111-103022 --llm-judge
# LLM-as-Judge (Claude Sonnet 4):
#   ✓ Clarity: 8.2/10 (weight 0.25)
#      "Текст структурирован, разделы чёткие, термины объяснены"
#   ✓ Medical appropriateness: 8.8/10 (weight 0.40) ✓ CRITICAL
#      "Все показатели корректно интерпретированы, диагнозов нет"
#   ✓ Russian grammar: 8.0/10 (weight 0.20)
#      "Грамматика верная, одна опечатка (несущественная)"
#   ✓ Disclaimer compliance: 10.0/10 (weight 0.15) ✓ CRITICAL
#      "Дисклеймер присутствует, формулировка корректная"
# 
#   Overall: 8.6/10 ✓ PASS (threshold: 7.5)
# 
# Cost: $0.023 (LLM-judge call)
# Detailed report: /runs/run-20261111-103022/judge_detailed.md
```

**ADR:** ADR-007: Claude Sonnet 4 for judge (chosen for Russian language quality)

---

#### M9b: Plan conformance (added after code review, before M10)
M5-M7 и M9 были построены как универсальные компоненты и не покрывают их критерии приёмки выше (trace, бюджеты, compliance/cost-проверки, рубрика судьи, сценарии по плану). M10 зависит от этих данных, поэтому закрываем разрыв до M10.

**Состав:** M9b-1 модель сценария и проверка файлов, M9b-2 trace и артефакты прогона, M9b-3 проверка прогона, M9b-4 судья по рубрике, M9b-5 сценарии по плану и потоки mock-бота, M9b-6 ADR и синтетические PDF (M10 не блокирует).

**Детали, принятые решения, приёмка и оценка (~40 ч):** `_bmad-output/m9b-plan-conformance.md`.

---

#### M10: Baseline & Regression Detection (Day 15-16, 8h)
**Tasks:**
- [ ] `BaselineManager` class
- [ ] First run: save metrics to `runs/baseline.yml`
- [ ] Subsequent runs: load baseline, compare metrics
- [ ] Regression thresholds (from Part 5.2):
  - Cost: +20% → warn
  - Latency: +30% → warn
  - LLM-judge overall: -1.0 → warn
  - Critical dimensions < min → **alert**
- [ ] Alert generation: `runs/<run_id>/ALERT.txt` (human-readable)
- [ ] Report includes diff: baseline vs. current (table format)
- [ ] **Exit code: always 0** (pass but log)

**Acceptance:**
```bash
# First run
testforge run --scenarios fixtures/scenarios/single_upload.yml --mode mock
# ✓ Baseline established: runs/baseline.yml
# Metrics saved for scenario SC-002

# Second run (simulated regression)
testforge run --scenarios fixtures/scenarios/single_upload.yml --mode mock
# ⚠️ REGRESSION DETECTED
# Scenario SC-002:
#   ✓ Cost: $0.138 (+3.8%) — PASS
#   ⚠️ LLM-judge overall: 7.3 (-1.3) — REGRESSION
#      Medical appropriateness: 7.0 (below critical 8.0)
# 
# Alert saved: runs/run-20261116-112045/ALERT.txt
# Exit code: 0 (pass but logged)
```

---

#### M11: CLI, Reporting & CI (Day 17-18, 10h)
**Tasks:**
- [ ] Complete CLI commands:
  - `testforge init --config <path>` (scaffold config file)
  - `testforge config validate`
  - `testforge plan --scenarios <dir>` (load & validate scenarios)
  - `testforge run --scenario <file> --mode <mock|real>`
  - `testforge verify --run-id <id> [--llm-judge]`
  - `testforge report --run-id <id> --format <html|json>`
  - `testforge baseline --reset` (clear baseline, re-establish on next run)
- [ ] HTML report generator (Jinja2 template):
  - Summary: pass/fail, cost, latency
  - Per-scenario results
  - LLM-judge scores (radar chart or table)
  - Baseline comparison (if exists)
  - Alerts (if any)
- [ ] JSON report (machine-readable, for CI parsing)
- [ ] **GitHub Actions workflow** (`.github/workflows/testforge.yml`):
  - Trigger: `workflow_dispatch` (manual)
  - Inputs: scenario (dropdown), mode (mock/real)
  - Steps: checkout, setup Python, install deps, run TestForge, upload artifacts
  - Publish: HTML report, ALERT.txt (if exists)

**CI Workflow (`.github/workflows/testforge.yml`):**
```yaml
name: TestForge E2E

on:
  workflow_dispatch:
    inputs:
      scenario:
        description: 'Scenario to run'
        required: true
        type: choice
        options:
          - single_upload
          - batch_upload
          - all
      mode:
        description: 'Execution mode'
        required: true
        type: choice
        options:
          - mock
          - real

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -e .
      
      - name: Run TestForge
        env:
          TESTFORGE_BOT_TOKEN: ${{ secrets.TESTFORGE_BOT_TOKEN }}
          TESTFORGE_LLM_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          TESTFORGE_MODE: ${{ inputs.mode }}
        run: |
          if [ "${{ inputs.scenario }}" = "all" ]; then
            testforge run --scenarios fixtures/scenarios/*.yml --mode ${{ inputs.mode }}
          else
            testforge run --scenario fixtures/scenarios/${{ inputs.scenario }}.yml --mode ${{ inputs.mode }}
          fi
          testforge verify --run-id latest --llm-judge
          testforge report --run-id latest --format html
      
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: testforge-report
          path: |
            runs/*/report.html
            runs/*/ALERT.txt
            runs/*/cost.json
          if-no-files-found: warn
      
      - name: Check for alerts
        run: |
          if [ -f runs/latest/ALERT.txt ]; then
            echo "::warning::Regression detected, review ALERT.txt"
            cat runs/latest/ALERT.txt
          fi
```

**Acceptance:**
```bash
# Local
testforge run --scenario fixtures/scenarios/single_upload.yml --mode mock
testforge verify --run-id latest --llm-judge
testforge report --run-id latest --format html
open runs/latest/report.html

# CI (manual trigger on GitHub)
# Navigate to Actions → TestForge E2E → Run workflow
# Select: scenario=single_upload, mode=mock
# → Workflow runs, uploads report.html
# → If regression: warning annotation + ALERT.txt in artifacts
```

---

## 7. Phase 0 Definition of Done (Final Checklist)

**Must-Have (Blocking):**
- [ ] **M1-M11 complete** — все задачи выполнены, acceptance criteria met
- [ ] **5 scenarios authored** — hardcoded YAML, validated, documented
- [ ] **5 synthetic PDFs generated** — realistic Russian lab reports, committed to repo
- [ ] **Mock mode works end-to-end** — run scenario, verify, report (no real bot needed)
- [ ] **Real bot mode code ready** — tested with mocked API, ready for staging bot
- [ ] **LLM-as-judge implemented** — Claude Sonnet 4, rubric-based scoring
- [ ] **Baseline established** — first run saves metrics, subsequent runs compare
- [ ] **Regression detection works** — alerts generated, not blocking CI
- [ ] **HTML report generated** — human-readable summary, LLM-judge scores, cost breakdown
- [ ] **CI workflow configured** — GitHub Actions, on-demand trigger
- [ ] **Documentation complete** — README, ADRs, scenario authoring guide

**Nice-to-Have (Non-Blocking):**
- [ ] Performance profiling (identify slowest steps)
- [ ] Cost optimization (reduce LLM-judge calls for non-critical scenarios)
- [ ] Multi-scenario parallelization (run 2 scenarios concurrently)
- [ ] Screenshot/trace export (if ask-toby adds web UI in future)

**Acceptance Test (Final Gate):**
```bash
# Developer follows README quickstart:
git clone <testforge-repo>
cd testforge
pip install -e .
cp .env.example .env
# Edit .env: add TESTFORGE_LLM_API_KEY

testforge init --config myconfig.yaml
testforge plan --scenarios fixtures/scenarios/*.yml
testforge run --scenario fixtures/scenarios/single_upload.yml --mode mock
testforge verify --run-id latest --llm-judge
testforge report --run-id latest --format html

# Result: HTML report opens in browser, shows PASS, cost $0.133, LLM-judge 8.5/10
# Time from clone to report: < 30 minutes
```

---

## 8. Post-Phase 0: Handoff & Next Steps

### 8.1 Deliverables

1. **Code:** `testforge/` repo, all M1-M11 code committed
2. **Fixtures:** 5 synthetic PDFs + expectations YAMLs
3. **Scenarios:** 5 hardcoded scenarios (onboarding, single upload, batch, Q&A, measurement)
4. **Documentation:**
   - `README.md` — install, quickstart, architecture overview
   - `docs/SCENARIO_AUTHORING.md` — how to write scenarios
   - `docs/ADDING_FIXTURES.md` — how to generate synthetic lab reports
   - `docs/adr/` — 7 ADRs (external tool, config format, mock bot, scenario format, LLM-judge, bot client, CI)
5. **CI:** GitHub Actions workflow (on-demand)
6. **Baseline:** Saved from first mock run, ready for comparison

### 8.2 Known Limitations (Phase 0)

- **No real bot testing yet** — staging bot not available, only mock mode validated
- **Scenarios hardcoded** — LLM-powered generation deferred to Phase 1
- **5 fixtures only** — limited coverage, expands in Phase 1
- **No multi-turn conversation tracking** — Phase 1 adds conversation history validation
- **No family accounts testing** — Phase 1 adds member switching, data isolation checks
- **No medication reminder timing** — Phase 1 adds time-based flow testing

### 8.3 Phase 1 Proposal (4-6 weeks)

**Prerequisites:** Phase 0 complete, staging bot deployed.

**Goals:**
1. **LLM-powered scenario generation** — analyze ask-toby docs, generate 50+ scenarios
2. **Expanded fixture library** — 20+ synthetic documents (varied test types, edge cases)
3. **Real bot validation** — run full suite against staging bot, establish production baselines
4. **Multi-turn conversational tests** — 5-10 turn dialogs, conversation history checks
5. **Family accounts & measurements** — create member, switch, record BP/glucose, verify isolation
6. **Medication reminders** — add meds, verify scheduled delivery (may need time mocking)
7. **Regression suite** — 20 golden documents, track LLM-judge scores over time
8. **Performance benchmarking** — per-stage latency, token efficiency, cost per doc type
9. **A/B testing support** — compare two prompt versions, statistical significance

**Phase 1 DoD:**
- 50+ scenarios cover all ask-toby commands
- 20+ synthetic documents (varied complexity)
- Real bot E2E suite runs in CI (on staging deploy)
- Production baselines established (latency, cost, quality)
- Regression alerts integrated into ask-toby's monitoring (Sentry, Slack)

---

## 9. Success Criteria (Reminder)

### Phase 0 Succeeds If:
1. ✅ Developer runs first test in **< 30 minutes** (README only)
2. ✅ Mock mode works **end-to-end** (no real bot needed)
3. ✅ LLM-as-judge scores are **meaningful** (not all 10/10 or random)
4. ✅ CI budget **< $0.50/run** (currently $0.459 for 2 scenarios)
5. ✅ HTML report is **clear** and shows pass/fail reasons
6. ✅ Baseline & regression detection **works** (alerts generated)
7. ✅ Code is **maintainable** (typed, tested, documented)

### Phase 0 Fails If:
- ❌ LLM-as-judge is unreliable (same input → vastly different scores)
- ❌ Cost tracking is inaccurate (>20% error)
- ❌ Documentation incomplete (new user cannot run without help)
- ❌ Mock mode too simplistic (doesn't simulate ask-toby's behavior)

---

## 10. Risk Mitigation (Updated)

| Risk | Mitigation (Phase 0) |
|------|---------------------|
| **Staging bot not ready** | ✅ Mock mode allows development without bot; M8 ready for bot when available |
| **LLM-as-judge too expensive** | ✅ Budget: $0.023/scenario, only 2 scenarios in CI = $0.046 (10% of budget) |
| **Claude Sonnet Russian quality unknown** | ✅ M9 includes calibration: run 5-10 manual evaluations, tune rubric |
| **Synthetic PDFs unrealistic** | ✅ Generate with Claude, review visually, iterate until convincing |
| **CI secrets not managed** | ✅ Use GitHub Secrets (standard practice), document in README |
| **Baseline drift (model updates)** | ✅ Alert on regression, manual review decides: update baseline or investigate |
| **Flaky mock responses** | ✅ Deterministic canned responses, no randomness in mock mode |

---

## 11. Immediate Next Actions (Start Now)

### Today (Day 1):
1. ✅ **Approve this plan** (if ready, or request changes)
2. Create TestForge repo (GitHub)
3. **M1: Project setup** (4h) — directory structure, pyproject.toml, README
4. **M2: Config system** (start, 2h) — Pydantic models

### Tomorrow (Day 2):
5. **M2: Config system** (finish, 4h) — YAML loader, validation, examples
6. **M3: LLM providers** (start, 4h) — base class, AnthropicProvider

### This Week (Days 3-5):
7. **M3: LLM providers** (finish) — OpenAIProvider, MockProvider, tests
8. **M4: Mock Telegram bot** — canned responses, unit tests
9. **M5: Scenario schema** — Pydantic models, author 5 scenarios

---

## 12. Questions Before You Start?

**Ready to execute?** Or do you need:
- Clarification on any milestone?
- Different timeline (2 weeks aggressive)?
- Different budget allocation?
- Additional scenarios in Phase 0?

**My recommendation:** Start with M1 today (project setup), get the skeleton working, then iterate on M2-M11. I can help with any milestone — just say which one you're working on.

— **🏗️ Winston**

---

## Appendix: File Structure (Phase 0)

```
testforge/
├── .github/
│   └── workflows/
│       └── testforge.yml                # On-demand CI workflow
├── config/
│   └── examples/
│       ├── mock-bot.yaml                # For development without staging bot
│       └── staging-bot.yaml             # For real bot (when available)
├── docs/
│   ├── ARCHITECTURE.md                  # High-level design (link to this plan)
│   ├── GETTING_STARTED.md               # Install, first test in 30 min
│   ├── SCENARIO_AUTHORING.md            # How to write scenarios
│   ├── ADDING_FIXTURES.md               # How to generate synthetic PDFs
│   └── adr/
│       ├── 001-external-tool.md
│       ├── 002-yaml-config.md
│       ├── 003-direct-provider-sdks.md
│       ├── 004-mock-bot-phase-0.md
│       ├── 005-yaml-scenarios.md
│       ├── 006-long-polling.md
│       └── 007-claude-sonnet-judge.md
├── fixtures/
│   ├── documents/
│   │   ├── lab_report_001_biochem_normal.pdf
│   │   ├── lab_report_002_cbc_anemia.pdf
│   │   ├── lab_report_003_thyroid_normal.pdf
│   │   ├── lab_report_004_mixed_flags.pdf
│   │   └── clinical_note_005_ecg.pdf
│   ├── expectations/
│   │   ├── lab_report_001.yml
│   │   ├── lab_report_002.yml
│   │   └── ... (one per document)
│   ├── scenarios/
│   │   ├── onboarding.yml
│   │   ├── single_upload.yml
│   │   ├── batch_upload.yml
│   │   ├── conversation_qa.yml
│   │   └── measurement.yml
│   ├── rubrics/
│   │   └── interpretation_quality_v1.yml
│   └── mock_responses/
│       ├── start.json
│       ├── consent.json
│       ├── profile_setup.json
│       └── interpretation.json
├── src/
│   └── testforge/
│       ├── __init__.py
│       ├── cli.py                       # Typer app, all commands
│       ├── config.py                    # Pydantic models, YAML loader
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── scenario_designer.py    # Stub (loads hardcoded scenarios)
│       │   ├── executor.py             # Step execution, trace collection
│       │   └── verifier.py             # Schema, compliance, LLM-judge, cost, perf
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py                 # LLMProvider ABC
│       │   ├── anthropic.py            # Claude Sonnet 4
│       │   ├── openai.py               # GPT (future)
│       │   └── mock.py                 # Canned responses
│       ├── telegram/
│       │   ├── __init__.py
│       │   ├── mock_bot.py             # In-memory bot (Phase 0 primary)
│       │   ├── real_bot.py             # Bot API client (M8, ready for staging)
│       │   └── parser.py               # Extract text/data from bot messages
│       ├── validation/
│       │   ├── __init__.py
│       │   ├── schema.py               # Pydantic validators
│       │   ├── compliance.py           # Disclaimer, forbidden phrases
│       │   ├── llm_judge.py            # Rubric-based LLM evaluation
│       │   ├── cost.py                 # Budget checks
│       │   └── performance.py          # Latency checks
│       ├── baseline/
│       │   ├── __init__.py
│       │   └── manager.py              # Save/load/compare baselines
│       ├── reporting/
│       │   ├── __init__.py
│       │   ├── html.py                 # Jinja2 HTML report
│       │   └── json.py                 # Machine-readable JSON
│       └── utils/
│           ├── logging.py              # Structlog setup
│           ├── retry.py                # Exponential backoff
│           └── cost_tracking.py        # Token counting, pricing
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_providers.py
│   │   ├── test_mock_bot.py
│   │   ├── test_schema_validation.py
│   │   └── test_llm_judge.py
│   ├── integration/
│   │   ├── test_executor_mock_mode.py
│   │   └── test_e2e_mock.py            # Full scenario in mock mode
│   └── fixtures/
│       └── canned_llm_responses.json   # For MockProvider
├── runs/                                # Git-ignored, generated at runtime
│   ├── baseline.yml
│   └── run-<timestamp>/
│       ├── trace.json
│       ├── cost.json
│       ├── verification.json
│       ├── judge_detailed.md
│       ├── report.html
│       └── ALERT.txt (if regression)
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── uv.lock (if using uv) or requirements.txt
```

---

**End of Execution Plan. Ready to start M1?** 🏗️
