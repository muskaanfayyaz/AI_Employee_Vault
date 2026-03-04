---
id: "0023"
title: Gold Tier Social MCP Server Fix
stage: green
date: 2026-03-04
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: "fix Facebook posting; fix instagram posting; fix Social MCP Server missing"
labels: ["gold-tier", "social-media", "facebook", "instagram", "twitter", "mcp", "refactor", "bugfix"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/mcp/social_server.py
  - src/main.py
  - src/skills/social_poster.py
tests:
  - manual: python3 -c "from src.mcp.social_server import SocialMCPServer; s = SocialMCPServer(dry_run=True); print(s.name, s.version)"
---

## Prompt

1. fix Facebook posting
2. fix instagram posting
3. fix Social MCP Server missing

(Issued sequentially after the Gold Tier audit (PHR 0022) revealed three critical issues: Facebook/Instagram posting was a stub that moved files to Done/ without actually posting, and no Social MCP Server existed.)

## Response snapshot

**Fix 1 — Facebook posting:**
- Implemented `_post_to_facebook()` in `main.py` using Facebook Graph API v18 (`POST /{page_id}/feed`)
- Wired into `_handle_approved_social_posts()`
- Added `_log_social_post()` helper to write structured audit log entries with `integration` tag (fixes CEO Briefing Section 8 blind spot)
- Added `continue` guard so `Done/` move only happens after `status == "sent"`

**Fix 2 — Instagram posting:**
- Implemented `_post_to_instagram()` in `main.py` using two-step Graph API v18:
  - Step 1: `POST /{account_id}/media` (create container with `image_url` + `caption`)
  - Step 2: `POST /{account_id}/media_publish` (publish container)
- Returns early with error if `image_url` is empty (Instagram feed posts require it)
- Updated `social_poster.py` draft template to add `## Image URL` section prompting human reviewers to supply image URL before approving
- Updated `_handle_approved_social_posts()` to extract `image_url` from draft body

**Fix 3 — Social MCP Server (architecture consolidation):**
- Created `src/mcp/social_server.py` with `SocialMCPServer(BaseMCPServer)` class
- Implements four platform tools: `post_to_linkedin`, `post_to_facebook`, `post_to_instagram`, `post_to_twitter`
- All tools wrapped with `@with_retry(base_delay=2, max_retries=3)`
- `_http_post()` module helper raises `NonRetryableError` for 4xx codes ({400,401,403,404,405,409,422}), re-raises `HTTPError` for retryable 5xx/429
- `dry_run=True` mode returns synthetic success responses without making API calls
- Refactored `main.py`: removed four inline functions (`_post_to_facebook`, `_post_to_instagram`, `_post_to_twitter`, `_get_linkedin_person_urn`), replaced with `SocialMCPServer` calls in `_post_approved_linkedin_drafts()` and `_handle_approved_social_posts()`
- Smoke test: `from src.mcp.social_server import SocialMCPServer` → OK; `from src.main import _handle_approved_social_posts, _log_social_post` → OK

## Outcome

- ✅ Impact: Three critical Gold Tier gaps closed: (1) Facebook/Instagram now post via real Graph API calls, (2) data integrity restored (Done/ only updated after confirmed `status == "sent"`), (3) all four social platforms routed through unified SocialMCPServer with retry/health-check/credential validation, (4) CEO Briefing Section 8 now receives social event data via audit log
- 🧪 Tests: Manual import smoke test passes. No automated tests added — Gold Tier social tests remain a gap
- 📁 Files: Created src/mcp/social_server.py; Modified src/main.py (removed 4 inline functions, refactored 2 handlers); Modified src/skills/social_poster.py (Instagram image URL section)
- 🔁 Next prompts: Resolve Twitter 401 (check Developer Portal OAuth 1.0a settings + Read/Write permissions + same-app credentials); write Gold Tier social tests; clean up test_twitter.py; fix duplicate VAULT_ROOT in .env
- 🧠 Reflection: The stub in `_handle_approved_social_posts` was the most dangerous issue — items marked Done without being posted creates a false audit record. Architecture consolidation into SocialMCPServer brings social platforms in line with the email MCP pattern and provides uniform retry, health checks, and dry_run support

## Evaluation notes (flywheel)

- Failure modes observed: Stub code moving files to Done/ without posting (data integrity violation); Instagram requires mandatory image_url that draft flow didn't capture
- Graders run and results (PASS/FAIL): Manual smoke test PASS — imports clean, dry_run mode returns synthetic success
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): Run `DRY_RUN=true python3 src/main.py` → drop an Instagram draft in Approved/ → verify it moves to Done/ with audit log entry containing `integration` tag
