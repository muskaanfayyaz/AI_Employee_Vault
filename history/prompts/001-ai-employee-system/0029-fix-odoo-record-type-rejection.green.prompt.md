---
id: "0029"
title: Fix Odoo Record Type Rejection
stage: green
date: 2026-03-07
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: "[continuation] fix odoo_record type rejected by triage/planner/executor"
labels: ["gold-tier", "odoo", "erp", "type-system", "bugfix", "watcher"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/watchers/odoo.py
tests:
  - null
---

## Prompt

[Continuation from PHR-0028] Odoo watcher successfully detected 5 tasks but all vault items failed with:
`Invalid type: 'odoo_record'. Must be one of {'message', 'audit', 'social_post', 'erp', 'social', 'email', 'file'}`

Items cycling in Needs_Action/ every 30 seconds indefinitely.

## Response snapshot

One-line fix in `src/watchers/odoo.py:213` — changed `type: odoo_record` to `type: erp`.

The allowed type set in triage/planner/executor skills is `{'message', 'audit', 'social_post', 'erp', 'social', 'email', 'file'}`. The Odoo watcher was writing `odoo_record` which is not in this set, causing every skill to reject the item without moving it.

Fix:
```
"type: odoo_record\n"  →  "type: erp\n"
```

Existing stuck files in Needs_Action/ still have old type — patch with:
```bash
sed -i 's/^type: odoo_record$/type: erp/' Needs_Action/odoo-*.md
```

## Outcome

- Impact: Odoo vault items will now be accepted by triage/planner/executor and flow through the pipeline normally.
- Tests: No tests run; single-line change.
- Files: src/watchers/odoo.py (line 213, type value changed).
- Next prompts: Patch existing stuck Needs_Action/ files; verify end-to-end Odoo -> Needs_Action -> Done flow.
- Reflection: Type constants should be centralised (e.g. an enum or shared constant) so watcher authors cannot write an invalid type that silently cycles forever.

## Evaluation notes (flywheel)

- Failure modes observed: Silent infinite cycle — item rejected every 30s with no escalation or dead-letter queue.
- Graders run and results (PASS/FAIL): None
- Prompt variant (if applicable): Continuation of PHR-0028 session.
- Next experiment (smallest change to try): Add an ALLOWED_ITEM_TYPES constant in a shared module and import it in both watchers and skills to prevent future mismatches.
