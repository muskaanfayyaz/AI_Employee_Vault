---
id: "0030"
title: LinkedIn Approved Post Not Publishing Fix
stage: green
date: 2026-03-07
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: "no still its not showing on linkedin i have checked on activity in profile and developer linkedin as product Share on LinkedIn and its approved"
labels: ["gold-tier", "linkedin", "social", "bugfix", "approval", "mcp"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/mcp/social_server.py
  - src/main.py
tests:
  - null
---

## Prompt

no still its not showing on linkedin i have checked on activity in profile and developer linkedin as product Share on LinkedIn and its approved

## Response

Diagnosed and fixed three bugs blocking LinkedIn publishing after approval:

**Root causes:**
1. `_post_approved_linkedin_drafts` in main.py called `mcp.health_check()` which requires ALL platform credentials (Facebook, Instagram, Twitter, LinkedIn). Since only LinkedIn token was set, health check failed and LinkedIn posting was skipped entirely.
2. `.env` was not loaded inside `run_approval_cycle`, so `LINKEDIN_ACCESS_TOKEN` appeared unset even though it existed in `.env`.
3. `_http_post` tried to `json.loads()` an empty 201 response body (LinkedIn UGC Posts API returns 201 with empty body + `X-RestLi-Id` header). Fixed to handle empty body and capture header.

**Attempted new LinkedIn Posts API** (`/rest/posts` with `LinkedIn-Version: 202210`) but received HTTP 426 Upgrade Required — user's LinkedIn Developer App is "Classic" and cannot use the new versioned API without migration. Reverted to UGC Posts API.

**Fixes applied:**
- `src/main.py`: Replace `mcp.health_check()` with direct `os.getenv("LINKEDIN_ACCESS_TOKEN")` check + `load_dotenv()` before the check
- `src/mcp/social_server.py`: Fix `_http_post` to handle empty 201 body and capture `X-RestLi-Id` response header for post ID

**Result:** Post successfully published.
- Post ID: `urn:li:share:7436074797492764673`
- Image asset: `urn:li:digitalmediaAsset:D4D22AQEH3HR0Cg_i1g`
- Draft archived to `Done/draft-linkedin-post-c09f29ba.md`

**Side note:** Twitter draft in `Approved/` failing with 402 — API account out of credits.
