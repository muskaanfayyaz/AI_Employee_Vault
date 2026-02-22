---
id: "0017"
title: Approved Email Send and Done
stage: green
date: 2026-02-21
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: chat
labels: ["silver-tier","approval-workflow","gmail-send","done"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/main.py
tests:
  - none
---

## Prompt

my pending approval are now moved to approved now tell me how to make them send back and marked as done

## Response snapshot

Implemented the full Approved → Send → Done flow in `src/main.py`:

- Added `_send_approved_email_drafts(vault_root, approved, dry_run)` helper called from `run_approval_cycle`
- For each approved item where `source == "email_drafter"`:
  1. Locates draft file in `Approved/` by id prefix (`draft-email-<id[:8]>.md`)
  2. Parses `**To**:`, `**Subject**:`, `## Draft Body` from `req.body` using `_parse_md_header` / `_parse_md_section`
  3. Sends via Gmail API (`MIMEText` → `base64.urlsafe_b64encode` → `service.users().messages().send()`)
  4. Moves draft file `Approved/ → Done/` via `draft_file.rename(dest)`
- Added `_parse_md_header` and `_parse_md_section` module-level helpers
- Send failure leaves the file in `Approved/` (no silent data loss)
- Dry-run mode logs what would happen without sending or moving

## Outcome

- ✅ Impact: Approved email drafts are now automatically sent via Gmail and archived to Done/ on the next approval cycle tick (every 15s)
- 🧪 Tests: requires live approved draft in Approved/ + GMAIL_OAUTH_TOKEN_PATH set
- 📁 Files: src/main.py
- 🔁 Next prompts: restart with --schedule and confirm emails are sent + appear in Done/
- 🧠 Reflection: Pattern B (files already in Approved/) is handled transparently — check_approvals() returns them in the approved list, _send_approved_email_drafts picks them up

## Evaluation notes (flywheel)

- Failure modes observed: none (implementation only)
- Graders run and results (PASS/FAIL): n/a
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): restart --schedule and verify the 2 existing approved drafts are sent and moved to Done/
