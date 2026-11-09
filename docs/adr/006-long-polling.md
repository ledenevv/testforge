# ADR-006: Receiving the Bot's Replies in Real Mode

**Status:** Proposed. Waiting for the owner's choice (see Decision)  
**Date:** 2026-11-09  
**Deciders:** Winston (architect), User (owner)

---

## Context

The plan (M8) and the first draft of this ADR assumed Telegram long polling (`getUpdates`) or webhooks. Checking `RealTelegramBot` against the Telegram documentation showed that the Bot API cannot run a conversation with another bot:

1. **Replies are not delivered.** `getUpdates` and webhooks deliver messages sent *to* the bot. The bot's own replies are not delivered to it. So the bot cannot read what ask-toby answers.
2. **Bots do not see other bots' messages.** The Bots FAQ: "bots will not be able to see messages from other bots regardless of mode". Bot-to-bot private messages need MTProto, and Bot-to-Bot Communication Mode enabled on both bots.
3. **`send_message` speaks as the bot.** `RealTelegramBot.send_message` calls `sendMessage` with the bot token and a chat id. The message goes from the bot to that chat. It is not a message from a user to the bot, so it does not trigger ask-toby.
4. **Shared token.** Polling with the staging bot's token takes updates that the ask-toby process should receive. Two pollers on one token conflict.

**Consequence:** a real-mode run through the Bot API would test nothing about ask-toby's answers. Mock mode is not affected.

---

## Options

### A. MTProto user client (recommended)

A dedicated test Telegram account (not the owner's personal one) logs in with an MTProto library such as Telethon. It sends `/start`, documents and answers to the staging bot as a user would, and reads the replies from the update stream (a persistent connection, not HTTP polling).

- Needs: a test account, `api_id` and `api_hash` (my.telegram.org), a session string, the staging bot's username. All as GitHub Secrets.
- Needs a new dependency (Telethon).
- Matches the plan's intent (`TESTFORGE_TEST_USER_ID`). Needs no change on the ask-toby side.

### B. MTProto bot account with Bot-to-Bot Communication Mode

A bot created for TestForge logs in with MTProto using its token and messages the staging bot. Both bots need Bot-to-Bot Communication Mode enabled in BotFather.

- Needs: the ask-toby team enables the mode on the staging bot.
- No personal or test phone account.
- Not verified: no staging bot exists yet, and private-chat behaviour is untested.

### C. Bot API long polling (current code)

**Rejected:** cannot read replies (point 1) and speaks as the bot (point 3).

### D. Webhooks

**Rejected:** same limitation as C, and it needs a public HTTPS endpoint for a CI job.

### E. Test hook in ask-toby (HTTP endpoint or test mode)

Fallback. Needs work by the ask-toby team. ADR-001: TestForge does not change ask-toby.

---

## Decision

**Pending the owner's choice between A and B.** Recommendation: A.

Until then, real mode does not run. The deferred item "real-bot polling until the pattern matches" waits for this decision.

---

## Consequences (after the choice)

- `RealTelegramBot` (Bot API) is kept only for checks that need no conversation, such as verifying the token with `getMe`, or removed. The milestone that implements the choice decides.
- The real client keeps the interface of `MockTelegramBot` (ADR-004's migration path holds for the interface; the transport changes).
- The per-expectation timeout (`expect.timeout_sec`) and polling until the match are built on the chosen transport.
- Secrets (API hash, session string, bot token) live in GitHub Secrets, never in the repository.
- Bot pipeline cost is still not measured (owner decision, 2026-11-08).

---

## Related Decisions

- ADR-001: external tool (no changes to ask-toby)
- ADR-004: mock bot. Its migration path ("real bot = `RealTelegramBot`") is superseded for the transport by this ADR

---

## Code References

- `src/testforge/telegram/real_bot.py`: `send_message` (`sendMessage`), `get_updates` (`getUpdates` with offset and timeout)

---

**Decision proposed:** 2026-11-09  
**Decision accepted:** pending
