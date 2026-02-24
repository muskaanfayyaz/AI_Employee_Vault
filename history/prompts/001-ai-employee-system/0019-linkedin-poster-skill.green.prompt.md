---
id: "0019"
title: LinkedIn Poster Skill Silver Tier
stage: green
date: 2026-02-24
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: chat
labels: ["silver-tier", "linkedin", "poster", "skill", "w_member_social"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/skills/linkedin_poster.py
  - src/skills/executor.py
  - src/main.py
  - src/scripts/linkedin_auth.py
tests:
  - manual: python -c "from src.skills.linkedin_poster import LinkedInPosterSkill; print('OK')"
---

## Prompt

it is added to scope w_member_social

## Response snapshot

Implemented full LinkedIn posting flow (draft → approve → post):

- **`src/scripts/linkedin_auth.py`**: Added `w_member_social` to SCOPES — user must re-run auth to get a new token with posting permission

- **`src/skills/linkedin_poster.py`** — `LinkedInPosterSkill`:
  - Reads `type: social` TaskItem from Needs_Action/
  - Extracts content from `## Content` section or item body
  - Uses Gemini to polish the post (fallback placeholder if no API key)
  - Creates `draft-li-post-<id[:8]>.md` in Pending_Approval/ with full approval workflow
  - FR-017 compliant — never posts directly, always requires human approval

- **`src/skills/executor.py`**: Added LinkedInPosterSkill hook after EmailDrafterSkill block — triggers when `item.type == "social"` and `"draft post"` in step description (planner generates this step for `type: social` items automatically)

- **`src/main.py`**:
  - Added `_post_approved_linkedin_drafts(vault_root, approved, dry_run)` — called from `run_approval_cycle` alongside email drafts
  - Added `_get_linkedin_person_urn(token)` — fetches `urn:li:person:{sub}` from `/v2/userinfo`
  - Posts via `POST /v2/ugcPosts` with `w_member_social` token
  - Moves draft Approved/ → Done/ after successful post

## Outcome

- ✅ Impact: Dropping a type: social file in drop_folder/ → auto-drafts LinkedIn post → human approves → posts to LinkedIn
- 🧪 Tests: import smoke-test passed; live test requires re-running linkedin_auth with w_member_social scope
- 📁 Files: src/skills/linkedin_poster.py, src/skills/executor.py, src/main.py, src/scripts/linkedin_auth.py
- 🔁 Next prompts: re-run linkedin_auth → update token in .env → drop a test post → verify approval flow
- 🧠 Reflection: /v2/userinfo sub field gives person URN without needing r_liteprofile; ugcPosts API available with w_member_social

## Evaluation notes (flywheel)

- Failure modes observed: none (implementation only)
- Graders run and results (PASS/FAIL): import smoke-test passed
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): drop test social item → verify Pending_Approval/ draft → approve → confirm post appears on LinkedIn
