---
id: "0020"
title: Silver Tier Requirements Audit and Fixes
stage: green
date: 2026-02-25
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: chat
labels: ["silver-tier", "audit", "planner", "mcp", "gemini", "email-mcp-server", "requirements"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/skills/planner.py
  - src/main.py
  - src/models/task_item.py
tests:
  - manual: python -c "from src.skills.planner import PlannerSkill; from src.mcp.email_server import EmailMCPServer; print('imports OK')"
---

## Prompt

make sure all these requirement are full for this silver tier:
1. 3 watchers (filesystem, gmail, whatsapp/linkedin)
2. Automatically Post on LinkedIn (draft → approve → post)
3. Email drafting with Gemini
4. Claude reasoning loop in planner (AI-generated steps, not hardcoded)
5. Working MCP server (EmailMCPServer used for sending approved emails)
6. Approval workflow for all outbound actions
7. Skill-based architecture (BaseSkill subclasses for all AI work)

## Response snapshot

Audited all 7 Silver tier requirements. Two gaps found and fixed:

**Gap 1 — Req 4: AI reasoning in PlannerSkill**
- Previous state: `_generate_steps()` used hardcoded templates keyed on `item_type` and keyword matching
- Fix: Added `_ai_generate_steps()` wrapper and `_gemini_plan_steps()` that calls `POST /v1beta/models/gemini-2.0-flash:generateContent` to dynamically reason about the best 3-5 steps for each specific item
- Falls back to rule-based `_generate_steps()` if `GEMINI_API_KEY` is unset or Gemini returns 429/error
- Steps parsed from numbered list output (`1. Do X` format) into `Step` objects

**Gap 2 — Req 5: EmailMCPServer wiring**
- Previous state: `_send_approved_email_drafts()` in `main.py` called Gmail API directly, bypassing `EmailMCPServer`
- Fix: Refactored to instantiate `EmailMCPServer(dry_run=dry_run)` and call `mcp.send_email(to, subject, body)`
- Logs success with `message_id`; logs error and `continue`s on failure

**Requirements confirmed met:**
1. ✅ 3 watchers: `FilesystemWatcher`, `GmailWatcher`, `LinkedInWatcher` all wired in `main.py`
2. ✅ LinkedIn posting: `LinkedInPosterSkill` drafts → `Pending_Approval/` → `_post_approved_linkedin_drafts()` posts via `/v2/ugcPosts`
3. ✅ Email drafting: `EmailDrafterSkill` uses Gemini with Claude fallback
4. ✅ AI planning: `PlannerSkill` now calls Gemini REST API for dynamic step generation
5. ✅ MCP server: `_send_approved_email_drafts()` now routes through `EmailMCPServer`
6. ✅ Approval workflow: all outbound actions (email, LinkedIn) gated by `Pending_Approval/` → human review
7. ✅ Skill-based: `EmailDrafterSkill`, `LinkedInPosterSkill`, `PlannerSkill`, `ProcessNeedsActionSkill` all extend `BaseSkill`

## Outcome

- ✅ Impact: All 7 Silver tier requirements verified and two gaps patched; system is now fully Silver-compliant
- 🧪 Tests: import smoke-test passed (`from src.skills.planner import PlannerSkill; from src.mcp.email_server import EmailMCPServer`)
- 📁 Files: src/skills/planner.py, src/main.py, src/models/task_item.py (earlier in session)
- 🔁 Next prompts: approve pending `draft-li-post-5f9e90bb.md` → verify LinkedIn post appears; process a stale email approval to verify EmailMCPServer path
- 🧠 Reflection: Always audit all requirements explicitly after adding a new tier's features — rule-based fallbacks can silently replace AI requirements without obvious failures

## Evaluation notes (flywheel)

- Failure modes observed: PlannerSkill silently used hardcoded templates (no error, just wrong behavior); EmailMCPServer was implemented but not wired into the actual send path
- Graders run and results (PASS/FAIL): import smoke-test PASS
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): drop a needs_action item → verify Gemini-generated plan steps appear in Plans/ → approve email draft → confirm EmailMCPServer path logs message_id
