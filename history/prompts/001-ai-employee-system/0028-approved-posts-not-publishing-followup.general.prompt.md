---
id: "0028"
title: Approved Posts Not Publishing Follow-up
stage: general
date: 2026-03-07
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: "in my workflow all my post moved to approved but not posted why"
labels: ["gold-tier", "social-media", "debugging", "credentials", "twitter", "facebook", "instagram", "approval-cycle", "schedule-mode"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/main.py
  - src/approval/manager.py
  - src/mcp/social_server.py
tests:
  - null
---

## Prompt

in my workflow all my post moved to approved but not posted why

## Response snapshot

Diagnosed two root causes for approved posts not publishing. No code changes made — both causes are operational/environmental.

**Root Cause 1: `--schedule` flag required**
Publishing is triggered by `run_approval_cycle` (`main.py:99`), which is only called when running with `--schedule`. Running `--process` or the default watcher loop never invokes the approval cycle, so approved files sit in `Approved/` indefinitely.

Fix: `python -m src.main --schedule`

**Root Cause 2: API credentials broken (same as PHR-0027)**
The 3 draft files in `Approved/` are from 2026-03-04 (3 days old). Previous diagnosis (PHR-0027) identified:
- Twitter: 402 Payment Required — needs Basic plan upgrade ($100/mo)
- Facebook: OAuthException 467 — session invalidated, token needs regeneration in Meta Developer Console
- Instagram: OAuthException 463 — token expired 2026-02-28, needs regeneration

All 3 drafts confirmed present: draft-twitter-post-006ef5cc.md, draft-facebook-post-d1fd7856.md, draft-instagram-post-8a29a27f.md

## Outcome

- Impact: Identified two reasons approved social posts do not publish. Pipeline code is correct; issue is operational (wrong run mode) and/or expired credentials.
- Tests: No tests run; no code changes.
- Files: No files modified.
- Next prompts: Run with --schedule; fix Facebook + Instagram tokens in Meta Developer Console; upgrade Twitter plan or switch to v1.1 endpoint.
- Reflection: The `--schedule` vs `--process` distinction is a common operational confusion — approval cycle is silently absent in non-schedule modes. Consider adding a log warning when Approved/ has items but the approval cycle was not started.

## Evaluation notes (flywheel)

- Failure modes observed: Silent no-op — files in Approved/ with no log output because run_approval_cycle was never called.
- Graders run and results (PASS/FAIL): None
- Prompt variant (if applicable): Repeat of PHR-0027 scenario; credential fixes not yet applied.
- Next experiment (smallest change to try): Add a startup warning in run_watcher_loop and run_processing_cycle if Approved/ contains .md files and the approval cycle is not scheduled.
