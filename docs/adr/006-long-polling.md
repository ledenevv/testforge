# ADR-006: Receiving the Bot's Replies in Real Mode

**Status:** Accepted (option A, chosen by the owner)  
**Date:** 2026-11-09  
**Deciders:** Winston (architect), User (owner)

---

## Context

The plan (M8) and the first draft of this ADR assumed Telegram long polling (`getUpdates`) or webhooks. Checking `RealTelegramBot` against the Telegram documentation showed that the Bot API cannot run a conversation with another bot:

1. **Replies are not delivered.** `getUpdates` and webhooks deliver messages sent *to* the bot. The bot's own replies are not delivered to it, so the bot cannot read what ask-toby answers.
2. **Bots do not see other bots' messages.** The Bots FAQ: "bots will not be able to see messages from other bots regardless of mode". Bot-to-bot private messages need MTProto and Bot-to-Bot Communication Mode enabled on both bots.
3. **`send_message` speaks as the bot.** `RealTelegramBot.send_message` calls `sendMessage` with the bot token and a chat id. The message goes from the bot to that chat, not from a user to the bot, so it does not trigger ask-toby.
4. **Shared token.** Polling with the staging bot's token takes updates that the ask-toby process should receive. Two pollers on one token conflict.

**Consequence:** a real-mode run through the Bot API would test nothing about ask-toby's answers. Mock mode is not affected.

---

## Options

### A. MTProto user client (chosen)

A dedicated test Telegram account (not the owner's personal one) logs in with Telethon. It sends `/start`, documents and answers to the staging bot as a user would, and reads the replies from the update stream of the same account. The update stream is a persistent connection, not HTTP polling.

- Needs: a test account, `api_id` and `api_hash` from my.telegram.org, a session string, the staging bot's username. All as secrets.
- Needs a new dependency (Telethon).
- Matches the plan's intent (`TESTFORGE_TEST_USER_ID`). Needs no change on the ask-toby side.

### B. MTProto bot account with Bot-to-Bot Communication Mode

A bot created for TestForge logs in with MTProto using its token and messages the staging bot. Both bots need Bot-to-Bot Communication Mode enabled in BotFather.

- Needs: the ask-toby team enables the mode on the staging bot.
- No personal or test phone account.
- Not verified: no staging bot exists yet. Kept as a fallback if option A is ever blocked.

### C. Bot API long polling (the earlier `RealTelegramBot` design)

**Rejected:** cannot read replies (point 1) and speaks as the bot (point 3).

### D. Webhooks

**Rejected:** same limitation as C, and it needs a public HTTPS endpoint for a CI job.

### E. Test hook in ask-toby (HTTP endpoint or test mode)

Fallback. Needs work by the ask-toby team. ADR-001: TestForge does not change ask-toby.

---

## Decision

Option A. Real mode uses a dedicated Telegram test account, logged in over MTProto with Telethon. The owner chose it on 2026-11-09.

---

## Implementation (M8b-1)

- `src/testforge/telegram/user_bot.py`: `TelegramUserBot`, with the same interface as `MockTelegramBot` (the `TelegramBot` protocol). Replies are collected by an event handler that is filtered to the bot's id, and returned by `get_updates`.
- `scripts/telegram_login.py`: one-time login. Prints the session string.
- Settings come from environment variables: `TESTFORGE_TG_API_ID`, `TESTFORGE_TG_API_HASH`, `TESTFORGE_TG_SESSION`, `TESTFORGE_TG_BOT` (the bot's username). Secrets live in GitHub Secrets (CI) or `.env` (local), never in YAML.
- `RealTelegramBot` (Bot API) is not used for conversations. It stays in the code until the factory is wired (M8b-2), then it is removed or kept only for checks such as `getMe`.

---

## Consequences

- Real runs use a real Telegram account. Telegram can limit accounts that send automated messages (FloodWait errors, restrictions). Use the dedicated test account only.
- The session string gives full access to that account. Store it only as a secret.
- Not handled yet: edited messages from the bot, FloodWait retries, session expiry, and waiting for several replies in the executor (per-expectation timeout). The first real run shows which of these ask-toby needs.
- Telethon is a dependency (`telethon>=1.45,<2`). It ships without type stubs, so mypy ignores it (`pyproject.toml`).
- Bot pipeline cost is still not measured (owner decision, 2026-11-08).

---

## Related Decisions

- ADR-001: external tool (no changes to ask-toby)
- ADR-004: mock bot. The migration path keeps the client interface; the transport changes to option A
- `_bmad-output/m8b-real-client.md`: the plan for M8b

---

## Code References

- `src/testforge/telegram/user_bot.py`: `TelegramUserBot`
- `scripts/telegram_login.py`: one-time login
- `tests/unit/test_user_bot.py`: 16 tests on a fake Telethon client
- `src/testforge/telegram/real_bot.py`: Bot API client, not used for conversations

---

**Decision proposed:** 2026-11-09  
**Decision accepted:** 2026-11-09 (option A)
