---
id: "0007"
title: silver-gmail-watcher-retry-decorator
stage: green
date: 2026-02-19
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.implement
labels: ["silver","gmail","watcher","retry","exponential-backoff","unit-tests"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/engine/retry.py
  - src/watchers/gmail.py
  - Config/gmail_watcher.yaml
  - tests/unit/test_retry.py
  - tests/unit/test_gmail_watcher.py
  - specs/001-ai-employee-system/tasks.md
tests:
  - tests/unit/test_retry.py (13/13 passed)
  - tests/unit/test_gmail_watcher.py (35/35 passed)
  - tests/ (114/114 passed)
---

## Prompt

Implement GmailWatcher based on hackathon blueprint.

Behavior:
- Fetch unread important emails
- Create markdown file in /Needs_Action
- Track processed IDs
- Respect DRY_RUN
- Log actions

## Response snapshot

Implemented Silver tier GmailWatcher (T035) plus its dependencies T027/T029 (retry decorator) and T036 (config).

**T029 — `src/engine/retry.py`**:
`@with_retry(base_delay=2, max_retries=3, multiplier=2)` decorator. On exhaustion raises `RetriesExhaustedError` carrying `retry_count`, `original_error`, and `timestamps`. `exceptions` parameter narrows which exception types trigger retries. Preserves `__name__`/`__doc__` via `functools.wraps`. Tested with `time.sleep` mocked to verify exact delay sequence (2s→4s→8s).

**T035 — `src/watchers/gmail.py`**:
`GmailWatcher(BaseWatcher)` with:
- `check_for_updates()` — Gmail search `is:unread is:important` + config filters (keywords / senders / labels). Gracefully returns `[]` if credentials are missing or API fails.
- `create_action_file()` — writes `email-<id8>-<slug>.md` with full YAML front-matter (`type: email`, `source: gmail`, `source_id: <msg_id>`) and markdown body.
- ID tracking — JSON state file at `Config/gmail_processed_ids.json` (relative to vault root). Loaded on `run()`, updated after each `create_action_file()` call.
- DRY_RUN — inherited from BaseWatcher: `create_action_file()` is NOT called in dry_run, so no IDs are tracked.
- Graceful degradation — `_get_service()` raises descriptive errors for missing deps / missing env var / missing token file; `check_for_updates()` catches all and returns `[]`.
- `health_check()` — True only when enabled AND token file exists on disk.

**T036 — `Config/gmail_watcher.yaml`**:
Valid YAML matching Watcher Configuration schema. `polling_interval_seconds: 60`. Filter lists empty by default (populate to narrow scope).

**Tests (48 new, all passing)**:
- `test_retry.py`: 13 tests — success paths, exhaustion, delay sequence, exception filtering, metadata preservation.
- `test_gmail_watcher.py`: 35 tests — base64 helpers, query building, deduplication (3 messages, 1 already processed → 2 events), action file content, state persistence, health check, DRY_RUN vs live comparison.

## Outcome

- ✅ Impact: T027, T029, T035, T036 implemented and marked [x] in tasks.md
- 🧪 Tests: `pytest tests/ -q` → 114 passed, 0 failed (was 66 before; +48 new)
- 📁 Files: src/engine/retry.py, src/watchers/gmail.py, Config/gmail_watcher.yaml, tests/unit/test_retry.py, tests/unit/test_gmail_watcher.py
- 🔁 Next prompts: T028 (silver E2E integration test), T030 (approval model), T031 (approval manager), T032 (approval_policy.yaml), T033 (MCP base), T034 (Gmail MCP server), T037 (WhatsApp watcher)
- 🧠 Reflection: Gmail watcher should defer credential validation to poll time (not init) so it can be constructed without credentials and gracefully degrade. State file path derived from inbox_path.parent in run() override — clean without requiring vault_root in constructor.

## Evaluation notes (flywheel)

- Failure modes observed: None — all 48 tests passed on first run
- Graders run and results (PASS/FAIL): pytest 114/114 PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Implement T030 approval model + T031 approval manager
