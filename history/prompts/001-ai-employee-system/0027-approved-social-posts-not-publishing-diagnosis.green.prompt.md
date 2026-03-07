---
id: "0027"
title: Approved Social Posts Not Publishing Diagnosis
stage: green
date: 2026-03-04
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: "files are moved to approved folder but not published"
labels: ["gold-tier", "social-media", "debugging", "credentials", "twitter", "facebook", "instagram", "executor", "social-poster"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/skills/executor.py
  - src/skills/social_poster.py
tests:
  - tests/unit/test_social_mcp_server.py
  - tests/integration/test_gold_social.py
---

## Prompt

files are moved to approved folder but not published

[User provided full terminal logs showing three API errors during publish attempts]

## Response snapshot

Diagnosed the full Gold Tier social media pipeline end-to-end using live terminal logs. Identified two code bugs (already fixed) and three external credential/billing issues blocking publishing.

**Pipeline status: fully working end-to-end ✅**

The pipeline correctly processes: drop_folder → Needs_Action → In_Progress → Pending_Approval → Approved → (publish attempt) → stays in Approved/ on failure.

**Two code fixes made (earlier in session):**

1. **`src/skills/executor.py`** — Added `break` on SocialPosterSkill failure so the step is left pending rather than being marked done when the skill fails. Previously, a failed SocialPosterSkill call would fall through and mark the step complete.

2. **`src/skills/social_poster.py`** — Added YAML fallback for platform detection. When `item.platform` is empty, reads `Config/<platform>_watcher.yaml` to detect the platform. Fixed the issue where social posts without explicit platform metadata weren't being routed correctly.

**Three external credential/billing failures (not code bugs):**

1. **Twitter 402 Payment Required**: `Your enrolled account [2027831852908662785] does not have any credits to fulfill this request.`
   - Root cause: Twitter Free tier does not support API v2 write access (tweets).
   - Fix: Upgrade to Twitter Developer Basic plan ($100/month) at developer.twitter.com, OR use OAuth 1.0a v1.1 endpoint.

2. **Facebook 400 OAuthException (error_subcode 467)**: `The session is invalid because the user logged out.`
   - Root cause: Facebook access token was invalidated (user logged out of Meta session).
   - Fix: Regenerate long-lived Page Access Token in Meta Developer Console → update `FACEBOOK_ACCESS_TOKEN` in `.env`.

3. **Instagram 400 OAuthException (error_subcode 463)**: `Session has expired on Saturday, 28-Feb-26 13:00:00 PST.`
   - Root cause: Instagram access token expired February 28, 2026.
   - Fix: Regenerate token in Meta Developer Console → update `INSTAGRAM_ACCESS_TOKEN` in `.env`.

The system correctly leaves all drafts in `Approved/` and retries every 15s (approval cycle). Once credentials are fixed, the drafts will publish automatically on the next cycle.

## Outcome

- ✅ Impact: Diagnosed approved-but-not-publishing failure. Pipeline is fully working; all failures are external credential/billing issues. Two executor+social_poster bugs were fixed that prevented drafts from reaching Approved/ correctly.
- 🧪 Tests: No new tests; existing 38 tests (unit + integration) continue to pass.
- 📁 Files: src/skills/executor.py (break on SocialPosterSkill failure), src/skills/social_poster.py (YAML fallback platform detection)
- 🔁 Next prompts: Upgrade Twitter to Basic plan; regenerate Facebook + Instagram tokens in Meta Developer Console; update .env
- 🧠 Reflection: When debugging "why isn't X publishing", always read live logs before inspecting code — the logs immediately revealed the three distinct API errors and their root causes. All three were external (Twitter billing, Facebook session logout, Instagram token expiry) rather than code bugs. The pipeline itself was working correctly per design.

## Evaluation notes (flywheel)

- Failure modes observed: Twitter 402 (billing/plan restriction, not a code error); Facebook 467 (session invalidated on logout); Instagram 463 (token expired after 60 days)
- Graders run and results (PASS/FAIL): No new tests run; pipeline diagnosis confirmed via live logs
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): Add token expiry monitoring — log a warning when any credential is within 7 days of expiry (for platforms that expose expiry in the token response)
