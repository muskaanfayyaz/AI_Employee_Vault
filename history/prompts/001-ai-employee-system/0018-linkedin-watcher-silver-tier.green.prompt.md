---
id: "0018"
title: LinkedIn Watcher Silver Tier
stage: green
date: 2026-02-23
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: chat
labels: ["silver-tier", "linkedin", "watcher", "oauth2"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/watchers/linkedin.py
  - src/scripts/linkedin_auth.py
  - Config/linkedin_watcher.yaml
  - src/main.py
  - .env.example
tests:
  - manual: python -c "from src.watchers.linkedin import LinkedInWatcher; ..."
---

## Prompt

now linkedIn watcher in silver tier

## Response snapshot

Implemented the full LinkedIn watcher following the WhatsApp/Gmail watcher pattern:

- **`src/watchers/linkedin.py`** — `LinkedInWatcher(BaseWatcher)`:
  - Polls `/v2/invitations?q=receivedInvitations&status=PENDING` for connection requests
  - Polls `/v2/conversations?q=participant` for messages (disabled by default; requires LinkedIn Partner/MDP access)
  - Deduplicates via `Config/linkedin_processed_ids.json` state file (same pattern as WhatsApp)
  - Creates `li-inv-<id>-<slug>.md` or `li-msg-<id>-<slug>.md` Task Items in `Needs_Action/`
  - `health_check()` checks `LINKEDIN_ACCESS_TOKEN` env var
  - Graceful 401/403 handling — logs warning and returns empty list (no crash)
  - Helper functions `_extract_invitation_name()` and `_extract_conversation_name()` for parsing nested LinkedIn API response shapes

- **`src/scripts/linkedin_auth.py`** — WSL2-compatible OAuth2 manual flow:
  - Reads `Config/linkedin_credentials.json` (`client_id`, `client_secret`)
  - Prints auth URL for user to open in Windows browser
  - User pastes full redirect URL back into terminal
  - Extracts `code`, exchanges for access token via `urllib.request` (no extra SDK)
  - Saves token details to `Config/linkedin_token.json`
  - Prints `LINKEDIN_ACCESS_TOKEN=<token>` line for user to add to `.env`

- **`Config/linkedin_watcher.yaml`** — Config with `enabled: false` by default:
  - `watch_invitations: true`, `watch_messages: false`
  - `polling_interval_seconds: 300` (5 min — respects LinkedIn rate limits)
  - `credential_ref: LINKEDIN_ACCESS_TOKEN`

- **`src/main.py`** — LinkedIn watcher block added to `run_schedule_loop()`:
  - Mirrors the WhatsApp watcher block exactly
  - Only activates when `Config/linkedin_watcher.yaml` exists and `enabled: true`
  - Import: `from src.watchers.linkedin import LinkedInWatcher`

- **`.env.example`** — `LINKEDIN_ACCESS_TOKEN` moved from Gold → Silver section

## Outcome

- ✅ Impact: LinkedIn connection requests automatically create Task Items in Needs_Action/ when the watcher is enabled; messages supported when MDP access is available
- 🧪 Tests: smoke-test import + construction verified; live test requires LINKEDIN_ACCESS_TOKEN + LinkedIn App with r_liteprofile scope
- 📁 Files: src/watchers/linkedin.py, src/scripts/linkedin_auth.py, Config/linkedin_watcher.yaml, src/main.py, .env.example
- 🔁 Next prompts: set up LinkedIn App → run linkedin_auth → set enabled: true → restart --schedule
- 🧠 Reflection: LinkedIn Invitations API is accessible on standard developer accounts; Conversations API requires MDP partner access — design correctly separates these with a `watch_messages` toggle

## Evaluation notes (flywheel)

- Failure modes observed: none (implementation only)
- Graders run and results (PASS/FAIL): n/a — import smoke-test passed
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): create LinkedIn App, run linkedin_auth, verify invitation Task Item created on next poll cycle
