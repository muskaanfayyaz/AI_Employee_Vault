---
id: "0014"
title: Silver Tier Email Drafter Wired
stage: green
date: 2026-02-21
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: chat
labels: ["silver-tier","email-drafter","approval","pipeline","fix"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/watchers/gmail.py
  - src/skills/executor.py
  - src/main.py
tests:
  - none
---

## Prompt

make sure it worked on silver tier and support all features in silver tier dont change any other tier code

## Response snapshot

Root cause analysis revealed 3 bugs preventing Silver tier email-drafter and approval features from working:

1. **gmail.py** missing `**Subject**:` field in email template → EmailDrafterSkill couldn't extract subject → fixed by adding `f"**Subject**: {subject}  \n"` to create_action_file()

2. **executor.py** never called EmailDrafterSkill → all emails went straight to Done/ without creating draft → fixed by adding Silver-tier logic: when step description matches "draft reply"/"draft response" AND item.type is email/message, invoke EmailDrafterSkill which creates draft-email-xxx.md in Pending_Approval/

3. **main.py run_approval_cycle** had no visibility into pending items → fixed by counting *.md files in Pending_Approval/ and logging "N item(s) awaiting your review" each approval cycle

Correct Silver tier flow post-fix:
- Gmail email → Needs_Action/ → triage → plan → executor (step 2: EmailDrafterSkill creates draft in Pending_Approval/) → email item goes to Done/
- Draft in Pending_Approval/ → human edits decision: pending → decision: approved → check_approvals moves to Approved/

## Outcome

- ✅ Impact: Silver tier email drafting and approval workflow now fully wired
- 🧪 Tests: manual test — restart system with --schedule, new emails should generate drafts in Pending_Approval/
- 📁 Files: gmail.py, executor.py, main.py modified
- 🔁 Next prompts: restart system, send test email, verify draft appears in Pending_Approval/
- 🧠 Reflection: The skills existed but were never connected. Executor was a pure file-mover (Bronze). The Silver wiring needed to be additive (not replace Bronze behavior).

## Evaluation notes (flywheel)

- Failure modes observed: EmailDrafterSkill existed but was dead code — never called from pipeline
- Graders run and results (PASS/FAIL): n/a — requires live test
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): test with real Gmail email, verify draft-email-xxx.md appears in Pending_Approval/
