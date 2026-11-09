# TestForge

E2E testing framework for [ask-toby](https://github.com/LedenevS/ask-toby) Telegram bot.

**TestForge** validates ask-toby's multi-tier LLM pipeline (vision extraction → LOINC normalization → distillation → interpretation) through black-box Telegram Bot API testing. Includes schema validation, compliance checks (disclaimer, forbidden phrases), LLM-as-judge quality scoring (Russian language), cost tracking, and performance metrics.

---

## Features

- **Dual-mode testing:**
  - **Mock mode** — in-memory bot with canned responses (no staging bot needed)
  - **Real mode** — tests against deployed ask-toby bot via Telegram Bot API
- **Multi-layer validation:**
  - Schema validation (Pydantic)
  - Compliance checks (disclaimer, forbidden medical phrases)
  - LLM-as-judge quality scoring (Claude Sonnet 4)
  - Cost tracking (tokens/$ per pipeline stage)
  - Performance metrics (latency, E2E duration)
- **Baseline & regression detection** — compares runs to baseline, generates alerts
- **Synthetic test data** — realistic Russian lab reports (5 PDFs included)
- **Scenarios as code** — YAML-based test scenarios with expected outcomes
- **CI/CD ready** — GitHub Actions workflow (on-demand)

---

## Quick Start (< 30 minutes)

### 1. Prerequisites

- **Python 3.12+** (you have 3.13.1 ✓)
- **Git** (you have 2.56.0 ✓)
- **Anthropic API key** (for LLM-as-judge) — get from [console.anthropic.com](https://console.anthropic.com/)

### 2. Install

```bash
# Clone repo
git clone https://github.com/<your-username>/testforge.git
cd testforge

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .
```

### 3. Configure

```bash
# Copy example config
cp .env.example .env

# Edit .env and add your Anthropic API key
notepad .env  # Add: TESTFORGE_LLM_API_KEY=sk-ant-...
```

### 4. Run First Test (Mock Mode)

```bash
# Validate config
testforge config validate --config config/examples/mock-bot.yaml

# Load scenarios
testforge plan --scenarios fixtures/scenarios/*.yml

# Run single scenario
testforge run --scenario fixtures/scenarios/single_upload.yml --mode mock

# Verify results
testforge verify --run-id latest --llm-judge

# Generate report
testforge report --run-id latest --format html
```

Open `runs/latest/report.html` in your browser. Should show **PASS**, cost ~$0.13, LLM-judge score ~8.5/10.

---

## Project Structure

```
testforge/
├── config/examples/          # Example configs (mock-bot, staging-bot)
├── docs/                     # Documentation & ADRs
├── fixtures/
│   ├── documents/            # 5 synthetic Russian lab reports (PDFs)
│   ├── expectations/         # Validation templates (YAML)
│   ├── scenarios/            # Test scenarios (YAML)
│   ├── rubrics/              # LLM-judge rubrics
│   └── mock_responses/       # Canned bot responses (mock mode)
├── src/testforge/            # Main package
│   ├── agents/               # Scenario Designer, Executor, Verifier
│   ├── providers/            # LLM providers (Anthropic, OpenAI, Mock)
│   ├── telegram/             # MockBot, RealBot, parser
│   ├── validation/           # Schema, compliance, LLM-judge, cost, perf
│   ├── baseline/             # Baseline manager
│   ├── reporting/            # HTML/JSON report generators
│   └── utils/                # Logging, retry, cost tracking
├── tests/                    # Unit & integration tests
└── runs/                     # Generated at runtime (git-ignored)
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `testforge init` | Scaffold new config file |
| `testforge config validate` | Validate config YAML |
| `testforge plan` | Load & validate scenarios |
| `testforge run` | Execute scenario(s) |
| `testforge verify` | Validate run results |
| `testforge report` | Generate HTML/JSON report |
| `testforge baseline --reset` | Clear baseline, re-establish on next run |

---

## Testing Modes

### Mock Mode (Default)

No staging bot needed. Uses in-memory `MockTelegramBot` with canned responses from `fixtures/mock_responses/`.

**Use for:**
- TestForge development
- Scenario authoring
- Quick validation (< 10s per scenario)

```bash
testforge run --scenario single_upload.yml --mode mock
```

### Real Mode

Tests against the staging ask-toby bot. TestForge sends messages from a dedicated Telegram test account over MTProto (ADR-006), because the Bot API cannot carry a conversation with a bot.

**Requires:**
- `TESTFORGE_TG_API_ID` and `TESTFORGE_TG_API_HASH` (from https://my.telegram.org)
- `TESTFORGE_TG_SESSION` (create once with `python scripts/telegram_login.py`)
- `TESTFORGE_TG_BOT` (username of the staging bot)

**Use for:**
- E2E validation before production deploy
- Baseline establishment
- Regression detection

```bash
export TESTFORGE_TG_API_ID=<api_id>
export TESTFORGE_TG_API_HASH=<api_hash>
export TESTFORGE_TG_SESSION=<session string>
export TESTFORGE_TG_BOT=<staging bot username>
export TESTFORGE_MODE=real
testforge run --scenario single_upload.yml --mode real
```

---

## Cost Budget

**Phase 0 (2 scenarios):**
- Onboarding + single upload: **$0.133**
- Batch upload (3 docs): **$0.326**
- **Total: $0.459** (within $0.50 budget)

**LLM-as-judge:** Claude Sonnet 4, ~$0.023-0.036 per scenario (10% of total).

All LLM calls are logged with model, tokens, cost. See `runs/<id>/cost.json` for breakdown.

---

## Baseline & Regression Detection

**First run:**
```bash
testforge run --scenario single_upload.yml --mode mock
# ✓ Baseline established: runs/baseline.yml
```

**Subsequent runs:**
```bash
testforge run --scenario single_upload.yml --mode mock
# Compares to baseline
# If regression: generates runs/<id>/ALERT.txt
# Exit code: 0 (pass but logged)
```

**Regression thresholds:**
- Cost: +20% → warn
- Latency: +30% → warn
- LLM-judge overall: -1.0 → warn
- Critical dimensions (medical_appropriateness <8.0, disclaimer <9.0) → **alert**

---

## CI Integration (GitHub Actions)

Workflow file: `.github/workflows/testforge.yml`

**Trigger:** Manual (`workflow_dispatch`)

**Run:**
1. Go to **Actions** → **TestForge E2E**
2. Click **Run workflow**
3. Select scenario: `single_upload`, `batch_upload`, or `all`
4. Select mode: `mock` or `real`
5. Wait for completion
6. Download artifacts: `report.html`, `ALERT.txt` (if regression)

---

## Documentation

- **[GETTING_STARTED.md](docs/GETTING_STARTED.md)** — detailed installation & first test
- **[SCENARIO_AUTHORING.md](docs/SCENARIO_AUTHORING.md)** — how to write scenarios
- **[ADDING_FIXTURES.md](docs/ADDING_FIXTURES.md)** — how to generate synthetic lab reports
- **[ADRs](docs/adr/)** — architectural decision records

---

## Development

### Install dev dependencies

```bash
pip install -e ".[dev]"
```

### Run tests

```bash
pytest tests/
```

### Lint & type-check

```bash
ruff check src tests
ruff format src tests
mypy src
```

### Add new scenario

1. Create YAML file in `fixtures/scenarios/`
2. Reference fixtures from `fixtures/documents/`
3. Define expectations in `fixtures/expectations/`
4. Validate: `testforge plan --scenarios fixtures/scenarios/<new>.yml`

---

## Phase 0 Status

**Current:** M1 complete (project setup)  
**Next:** M2-M11 (config, LLM providers, mock bot, executor, verifier, LLM-judge, baseline, CI)  
**Timeline:** 3 weeks (comfortable pace, 60-70h)

See **[TESTFORGE_EXECUTION_PLAN.md](TESTFORGE_EXECUTION_PLAN.md)** for full roadmap.

---

## Contributing

**Rules:**
- No changes to [ask-toby](https://github.com/LedenevS/ask-toby) repo
- TestForge is external black-box testing tool
- All tests run against deployed bot (or mock)

**Before submitting PR:**
```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest tests/
```

---

## License

MIT — see [LICENSE](LICENSE)

---

## Support

- **Issues:** [GitHub Issues](https://github.com/<your-username>/testforge/issues)
- **Discussions:** [GitHub Discussions](https://github.com/<your-username>/testforge/discussions)
- **ask-toby:** [LedenevS/ask-toby](https://github.com/LedenevS/ask-toby)

---

**Built for ask-toby by Winston 🏗️**
