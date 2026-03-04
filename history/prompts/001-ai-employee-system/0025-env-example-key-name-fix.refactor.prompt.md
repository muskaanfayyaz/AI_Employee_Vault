---
id: "0025"
title: env.example Key Name Fix
stage: refactor
date: 2026-03-04
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: ".env.example key name mismatch"
labels: ["config", "twitter", "facebook", "instagram", "bugfix", "credentials"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - .env.example
tests:
  - manual: grep TWITTER,FACEBOOK,INSTAGRAM .env.example — verified all 8 keys match SocialMCPServer._DEFAULT_REFS
---

## Prompt

.env.example key name mismatch

## Response snapshot

Fixed four issues in `.env.example` Social Media section:

| Before | After |
|--------|-------|
| `TWITTER_API_SECRET` | `TWITTER_API_KEY_SECRET` |
| `TWITTER_ACCESS_SECRET` | `TWITTER_ACCESS_TOKEN_SECRET` |
| _(missing)_ | `FACEBOOK_PAGE_ID` |
| _(missing)_ | `INSTAGRAM_ACCOUNT_ID` |

All 8 keys now match `SocialMCPServer._DEFAULT_REFS` exactly:
`FACEBOOK_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID`, `TWITTER_API_KEY`, `TWITTER_API_KEY_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`.

Also verified: `.env` duplicate `VAULT_ROOT` (flagged in PHR 0023) was already resolved.

## Outcome

- ✅ Impact: .env.example is now the authoritative reference for all required credentials — developers copying it will get the correct key names for all social platforms
- 🧪 Tests: Manual grep verification — all 8 social keys present and correctly named
- 📁 Files: .env.example only
- 🔁 Next prompts: Resolve Twitter 401; write Gold Tier social tests; remove test_twitter.py
- 🧠 Reflection: Credential key mismatches in example files cause silent failures — new developers set the wrong env var name and get confusing "credential missing" errors at runtime

## Evaluation notes (flywheel)

- Failure modes observed: Two wrong key names (TWITTER_API_SECRET, TWITTER_ACCESS_SECRET); two missing keys (FACEBOOK_PAGE_ID, INSTAGRAM_ACCOUNT_ID)
- Graders run and results (PASS/FAIL): Manual PASS
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): Diff .env.example against SocialMCPServer._DEFAULT_REFS values in CI to catch future drift
