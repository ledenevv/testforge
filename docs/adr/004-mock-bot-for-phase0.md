# ADR-004: Mock Telegram Bot for Phase 0

**Status:** Accepted  
**Date:** 2026-11-08  
**Deciders:** Winston (architect), Amelia (dev)

---

## Context

TestForge needs to test ask-toby Telegram bot interactions. Two approaches for Phase 0 development:

### Option A: Real Bot from Day 1

Use real Telegram Bot API from the start:
- Requires staging bot credentials
- Network calls in every test
- Slower test execution
- Harder to debug

### Option B: Mock Bot for Phase 0

Build in-memory mock bot first, real bot later:
- No credentials needed
- Instant test execution
- Predictable responses
- Switch to real bot in M8

---

## Decision

**We choose Option B: Mock Bot for Phase 0.**

---

## Rationale

### Why Mock Bot Wins for Phase 0

**1. Zero external dependencies**

```python
# Mock bot - works immediately
bot = MockTelegramBot()
await bot.send_message("/start")
updates = await bot.get_updates()
# No API key, no network, instant response
```

**2. Faster development cycle**

- **Mock:** Run test → instant result → fix code → repeat
- **Real:** Run test → wait for API → parse response → fix code → repeat + rate limits

Phase 0 is about building the **framework**, not testing real bot behavior yet.

**3. Deterministic testing**

Mock bot responses are **canned** (from JSON files):
```json
{
  "trigger": {"command": "/start"},
  "response": {
    "text": "👋 Привет! Этот бот анализирует медицинские документы.",
    "delay_sec": 0.5
  }
}
```

Real bot responses can vary:
- LLM interpretation is non-deterministic
- API might be down
- Rate limits hit during tests

**4. No credentials needed**

Real bot requires:
- `TELEGRAM_BOT_TOKEN` from staging bot
- Coordination with ask-toby team
- Security considerations (token in CI)

Mock bot works **out of the box** for any developer cloning the repo.

**5. Parallel test execution**

Mock bot is **stateless** per instance:
```python
# Run 10 tests in parallel - no conflicts
pytest -n 10 tests/unit/test_mock_bot.py
```

Real bot shares state:
- Message IDs conflict
- Chat state gets mixed
- Need complex test isolation

---

### Why NOT Real Bot (yet)

Real bot testing is **important**, but not in Phase 0:

| Concern | Mock Bot (Phase 0) | Real Bot (M8+) |
|---------|-------------------|----------------|
| **API changes** | Not detected | ✓ Detected |
| **Real LLM quality** | Not tested | ✓ Tested |
| **Network issues** | Not simulated | ✓ Exposed |
| **Bot API bugs** | Not caught | ✓ Caught |

**Solution:** Add real bot testing in **M8: Real Bot Client**, run in CI alongside mock tests.

---

## Implementation

### MockTelegramBot Architecture

```python
class MockTelegramBot:
    """In-memory Telegram bot simulator."""
    
    def __init__(self, responses_dir: str):
        # Load canned responses from JSON
        self.responses = self._load_responses(responses_dir)
        
        # FSM state for profile setup
        self.state: str = "idle"
        self.profile_data: dict = {}
        
        # Message queues
        self.sent_messages: list[TelegramMessage] = []
        self.pending_responses: list[TelegramMessage] = []
    
    async def send_message(self, text: str) -> TelegramMessage:
        """Send message to bot (from test user)."""
        message = TelegramMessage(...)
        self.sent_messages.append(message)
        
        # Process and queue bot response
        await self._process_message(message)
        return message
    
    async def send_document(self, file_path: Path) -> TelegramMessage:
        """Upload document to bot."""
        # Queues "document received" + "interpretation" responses
    
    async def get_updates(self) -> list[TelegramUpdate]:
        """Get pending bot responses."""
        # Returns and clears pending_responses queue
```

### Response Format

Each response is a JSON file:

**`fixtures/mock_responses/start.json`:**
```json
{
  "trigger": {"command": "/start"},
  "response": {
    "text": "👋 Привет! Этот бот анализирует медицинские документы.\n\n/consent — Согласиться",
    "delay_sec": 0.5
  }
}
```

**`fixtures/mock_responses/interpretation.json`:**
```json
{
  "trigger": {"after": "document_received"},
  "response": {
    "text": "📊 **Резюме**\n\nВаши анализы в целом в пределах нормы.\n\n**Ключевые моменты:**\n- АЛТ: 25 Ед/л (норма)\n- АСТ: 22 Ед/л (норма)\n...",
    "delay_sec": 2.0
  }
}
```

### Profile Flow (FSM)

Mock bot simulates ask-toby's profile setup:

```
/consent → profile_sex → profile_birth_year → profile_height 
         → profile_weight → profile_conditions → idle
```

Each state transition sends next question, collects data.

### Supported Scenarios (Phase 0)

1. **`/start`** — Welcome message
2. **`/consent`** — Start profile setup
3. **`/help`** — Help text
4. **Profile setup** — 5-step flow (sex, birth year, height, weight, conditions)
5. **Document upload** — Confirmation + interpretation
6. **Unknown command** — Default fallback

---

## Testing Strategy

### Unit Tests (M4)

```python
@pytest.mark.asyncio
async def test_send_start_command(bot):
    """Sending /start should return welcome message."""
    await bot.send_message("/start")
    updates = await bot.get_updates()
    
    assert len(updates) == 1
    assert "Этот бот анализирует медицинские документы" in updates[0].message.text
```

**Coverage:** 15 unit tests, all pass ✓

### Integration Tests (M6)

Mock bot will be used in scenario executor tests:
```python
scenario = Scenario.from_yaml("scenarios/profile_setup.yaml")
result = await executor.run(scenario, bot=MockTelegramBot())
assert result.passed
```

### Real Bot Tests (M8)

Switch to real bot for E2E validation:
```python
if mode == "real":
    bot = RealTelegramBot(token=config.bot.token)
else:
    bot = MockTelegramBot()
```

---

## Consequences

### Positive

✅ **Fast development** — no waiting for API calls  
✅ **No credentials** — works for any developer  
✅ **Deterministic tests** — canned responses never change  
✅ **Parallel tests** — no state conflicts  
✅ **Easy debugging** — all data in-memory, inspectable  
✅ **Phase 0 unblocked** — no dependency on ask-toby staging bot

### Negative

❌ **Not testing real bot** — won't catch ask-toby bugs  
❌ **Responses are static** — LLM quality not validated  
❌ **API changes missed** — Telegram Bot API updates not detected

### Mitigation

- **M8: Real Bot Client** — add real bot testing alongside mock
- **CI runs both modes** — mock for speed, real for validation
- **Staging bot required by M8** — Phase 0 doesn't block on it

---

## Alternatives Considered

### A1: VCR.py (Record/Replay)

Use [VCR.py](https://github.com/kevin1024/vcrpy) to record real API calls, replay in tests.

**Rejected because:**
- Still need real bot credentials to record cassettes
- Cassettes get stale when bot changes
- Mock bot is simpler and more transparent

### A2: Telegram Bot API Mock Server

Run fake Telegram API server (e.g., [telegram-bot-api-mock](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Writing-Tests)).

**Rejected because:**
- Extra infrastructure (Docker container)
- More complex than in-memory mock
- Doesn't simulate ask-toby's LLM logic

### A3: Skip mock, go straight to real bot

Build RealTelegramBot first, use it for all tests.

**Rejected because:**
- Blocks Phase 0 on staging bot credentials
- Slower test execution (network latency)
- Harder to debug (remote state)

---

## Migration Path (M8)

When adding real bot support in M8:

1. **Create `RealTelegramBot` class** (same interface as `MockTelegramBot`)
2. **Add bot factory** in config:
   ```python
   def create_bot(config: ForgeConfig) -> TelegramBot:
       if config.mode == "mock":
           return MockTelegramBot(responses_dir=config.responses_dir)
       else:
           return RealTelegramBot(token=config.bot.token)
   ```
3. **Run tests in both modes** (CI matrix):
   ```yaml
   strategy:
     matrix:
       mode: [mock, real]
   ```
4. **Keep mock tests fast** — run on every commit
5. **Run real tests nightly** — validate against staging bot

---

## Related Decisions

- **ADR-001:** External tool (TestForge doesn't modify ask-toby)
- **ADR-002:** YAML config (responses loaded from `fixtures/mock_responses/`)
- **M8 (future):** Real bot client implementation

---

## Code References

- `src/testforge/telegram/mock_bot.py` — MockTelegramBot implementation
- `src/testforge/telegram/models.py` — TelegramMessage, TelegramUpdate, ProfileData
- `fixtures/mock_responses/*.json` — Canned bot responses (7 files)
- `tests/unit/test_mock_bot.py` — 15 unit tests (all pass ✓)

---

**Decision accepted:** 2026-11-08  
**Implemented in:** M4 (Mock Telegram Bot)  
**Next review:** M8 (when adding real bot support)
