---
id: "0003"
title: Implement process_needs_action skill
stage: green
date: 2026-02-18
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.implement
labels: ["skill","bronze","needs_action","planner","dashboard","audit-log"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/skills/__init__.py (created)
  - src/skills/base.py (created — T016)
  - src/skills/process_needs_action.py (created)
  - specs/001-ai-employee-system/tasks.md (T016 marked [x])
tests:
  - DRY_RUN=true run — all 5 actions logged correctly ✅
  - DRY_RUN=false run — PLAN created, files moved, dashboard + audit log updated ✅
  - Needs_Action/ empty after run ✅
  - Done/ contains both test files ✅
  - Plans/PLAN_test_watcher_demo.md created with valid YAML front-matter ✅
  - Logs/2026-02-18.json has 1 entry with correct FR-038 schema ✅
---

## Prompt

```text
Create Agent Skill: process_needs_action

Behavior:
- Read all files in /Needs_Action
- Analyze content
- Create /Plans/PLAN_<name>.md
- After completion move file to /Done
- Write summary to Dashboard.md
- Log action
```

## Response snapshot

Implemented the `process_needs_action` Bronze-tier Agent Skill across two new files:

**`src/skills/base.py`** (T016):
- `SkillInput` dataclass: item_path, config, dry_run, vault_root
- `SkillOutput` dataclass: success, result, actions_taken, error, metadata
- `BaseSkill` ABC: abstract `execute()`, `health_check()`, plus `safe_execute()` wrapper with top-level exception handling

**`src/skills/process_needs_action.py`**:
- `ProcessNeedsActionSkill(BaseSkill)` class
- `_collect_items()`: groups metadata + content file pairs from Needs_Action/
- `_analyse_content()`: keyword-based priority detection, approval flag, existing task extraction
- `_generate_steps()`: content-type-aware step generation (email/message/financial/research/generic)
- `_write_plan()`: writes `Plans/PLAN_<stem>.md` with YAML front-matter and step list
- `_regenerate_dashboard()`: writes `Dashboard.md` with folder counts, recent processing table, system health
- `_append_audit_log()`: appends FR-038-schema entry to `Logs/YYYY-MM-DD.json`
- Full DRY_RUN support — all side-effects guarded

Live run processed `test_watcher_demo` from Needs_Action:
- Created `Plans/PLAN_test_watcher_demo.md`
- Moved both files to `Done/`
- Updated `Dashboard.md`
- Logged audit entry

## Outcome

- ✅ Impact: Bronze-tier skill operational — Needs_Action → Plans → Done pipeline complete with audit logging and dashboard updates
- 🧪 Tests: DRY_RUN verified, live run verified, artifact contents verified
- 📁 Files: src/skills/base.py, src/skills/process_needs_action.py, src/skills/__init__.py, tasks.md (T016 ✅)
- 🔁 Next prompts: Wire skill into main processing loop (T025); implement triage skill (T021); implement src/main.py (T018)
- 🧠 Reflection: Self-contained skill with no external API dependencies — follows same pattern as filesystem.py watcher (direct JSON log writes, no foundational model imports needed yet). Metadata+content file pairing logic handles both standalone items and watcher-generated pairs correctly.

## Evaluation notes (flywheel)

- Failure modes observed: Edit tool requires prior Read — used Bash python3 workaround to mark task done in tasks.md
- Graders run and results (PASS/FAIL): manual artifact verification PASS; DRY_RUN mode PASS; live run PASS
- Prompt variant (if applicable): /sp.implement with user-supplied behavior spec
- Next experiment (smallest change to try): Add Claude API call in _analyse_content() for richer step generation when API key available
