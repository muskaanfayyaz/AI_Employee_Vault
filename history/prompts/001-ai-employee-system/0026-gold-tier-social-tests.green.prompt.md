---
id: "0026"
title: Gold Tier Social Tests
stage: green
date: 2026-03-04
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: "Gold Tier social tests missing"
labels: ["gold-tier", "social-media", "tests", "unit", "integration", "mcp"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - tests/unit/test_social_mcp_server.py
  - tests/integration/test_gold_social.py
tests:
  - tests/unit/test_social_mcp_server.py
  - tests/integration/test_gold_social.py
---

## Prompt

Gold Tier social tests missing

## Response snapshot

Created two test files covering all Gold Tier social media components:

**`tests/unit/test_social_mcp_server.py`** (25 tests):
- Identity: `name`, `version`, `ping()` dict response
- `health_check()`: True when all 9 creds present, False when any missing
- dry_run mode: all 4 platforms return synthetic success, zero HTTP calls
- `post_to_linkedin`: success, no URN (returns failed), NonRetryableError 401
- `post_to_facebook`: success, NonRetryableError 403, generic ConnectionError
- `post_to_instagram`: success (two _http_post calls), empty image_url (early return), container returns no id, NonRetryableError 400
- `post_to_twitter`: tweepy ImportError, success (mock tweepy.Client), 401 raises NonRetryableError, 503 returns failed dict
- `_http_post` helper: 401→NonRetryableError, 503→re-raises HTTPError, success→parses JSON

Key fix during implementation: credential env vars must be set via `monkeypatch.setenv` (live throughout the test), not `patch.dict` as a context manager (which exits after `_make_server()` returns, leaving `_resolve_credential()` unable to find the vars at call time).

**`tests/integration/test_gold_social.py`** (13 tests):
- Twitter: success→Done/ move, failure→stays in Approved/
- Facebook: success→Done/ move, failure→stays in Approved/
- Instagram: success with image_url→Done/ move, missing image_url→graceful failure, stays in Approved/
- Edge cases: no social drafts (returns immediately), missing draft file (skips gracefully), dry_run=True (no file move even on success)
- Audit log: `_log_social_post` writes correct JSON (actor, action, outcome, details with platform/post_id/content_preview)
- `_log_social_post` dry_run→outcome="dry_run"
- CEO Briefing end-to-end: log entry → `_read_log_summary` → `social_events` populated with platform/post_id/operation/content_preview
- Multi-platform: 3 posts across twitter/facebook → all 3 events detected, correct per-platform counts

**Final result: 38/38 PASSED in 1.52s**

## Outcome

- ✅ Impact: Gold Tier social media pipeline now has full automated test coverage — SocialMCPServer unit tests, _handle_approved_social_posts routing integration tests, and CEO Briefing Section 8 end-to-end pipeline
- 🧪 Tests: 38 new tests — 25 unit (test_social_mcp_server.py) + 13 integration (test_gold_social.py). All pass.
- 📁 Files: Created tests/unit/test_social_mcp_server.py and tests/integration/test_gold_social.py
- 🔁 Next prompts: Resolve Twitter 401; remove test_twitter.py temp file
- 🧠 Reflection: The credential env-var lifetime bug (patch.dict exiting before method calls) caused 13 initial failures. The fix is to always use monkeypatch.setenv for credentials in fixtures — it persists for the full test scope. Never use patch.dict as a context manager when the patched env vars need to survive the with block.

## Evaluation notes (flywheel)

- Failure modes observed: patch.dict context manager exits before test method calls — credentials unavailable at _resolve_credential() call time; ping() returns dict not bool
- Graders run and results (PASS/FAIL): 38/38 PASS
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): Add these tests to CI pre-commit / GitHub Actions check
