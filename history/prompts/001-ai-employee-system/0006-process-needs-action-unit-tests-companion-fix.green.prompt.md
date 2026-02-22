---
id: "0006"
title: process-needs-action-unit-tests-companion-fix
stage: green
date: 2026-02-19
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.implement
labels: ["process_needs_action","unit-tests","companion-file","config-test","fix"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/skills/process_needs_action.py
  - tests/unit/test_process_needs_action.py
  - tests/unit/test_config.py
tests:
  - tests/unit/test_process_needs_action.py (21/21 passed)
  - tests/unit/test_config.py (5/5 passed)
  - tests/ (66/66 passed)
---

## Prompt

Create Agent Skill: process_needs_action

Behavior:
- Read all files in /Needs_Action
- Analyze content
- Create /Plans/PLAN_<name>.md
- After completion move file to /Done
- Write summary to Dashboard.md
- Log action

## Response snapshot

`process_needs_action.py` already existed from a prior Bronze tier session. Audited the implementation against the specified behavior and found two gaps:

**Bug 1 — `_collect_items` stem naming**: When a `-metadata.md` file had no `.md` companion (e.g. `task1-metadata.md` + `task1.txt`), the item stem was set to `"task1-metadata"` instead of `"task1"`, causing the plan to be named `PLAN_task1-metadata.md`.

**Fix**: Changed `"stem": content_stem if content_path else stem` → `"stem": content_stem` so the stem is always derived from the content, not the metadata filename.

**Bug 2 — companion `.txt` files not moved**: `_collect_items` only looked for `.md` companions. The watcher creates `task1.txt` + `task1-metadata.md`, but `task1.txt` was never included in the `files` list, so it stayed in `Needs_Action/` after processing.

**Fix**: Added a sibling scan for non-`.md` files with matching stem when no `.md` companion exists.

**Bug 3 — `test_dry_run_defaults_true` failing**: With `.env` now containing `DRY_RUN=false` and `config.py` using `override=True`, reloading `src.config` in the test loaded the real `.env`, making DRY_RUN False instead of True (the safe default).

**Fix**: Patched `dotenv.load_dotenv` (the source module attribute) so `importlib.reload(cfg)` re-imports the Mock, preventing `.env` from loading during the test.

**Added**: `tests/unit/test_process_needs_action.py` with 21 tests covering `_analyse_content`, `_collect_items`, and `ProcessNeedsActionSkill.execute` in both dry_run and live modes, including the `.txt` companion scenario.

**Live run output** (against real vault):
```
✅ SUCCESS
Summary : Processed 1 item(s) from Needs_Action: task1
Actions (5):
  • created Plans/PLAN_task1.md
  • moved task1-metadata.md → Done/
  • moved task1.txt → Done/
  • logged to Logs/2026-02-19.json
  • updated Dashboard.md
```

## Outcome

- ✅ Impact: process_needs_action skill fully verified and working end-to-end against the real vault
- 🧪 Tests: `pytest tests/ -q` → 66 passed, 0 failed (was 45 before; +21 new unit tests)
- 📁 Files: src/skills/process_needs_action.py (2 bug fixes), tests/unit/test_process_needs_action.py (new, 21 tests), tests/unit/test_config.py (test isolation fix)
- 🔁 Next prompts: Implement Silver tier (T027–T052) — retry logic, approval workflow, email MCP
- 🧠 Reflection: `importlib.reload` causes module-level bindings to be re-created from imports, so patching `src.config.load_dotenv` doesn't survive a reload — must patch the source (`dotenv.load_dotenv`). Companion file handling needs to account for any extension, not just `.md`.

## Evaluation notes (flywheel)

- Failure modes observed: (1) `importlib.reload` invalidates `unittest.mock.patch` on local module references; (2) watcher creates `.txt` + `-metadata.md` pairs but skill only moved `.md` files
- Graders run and results (PASS/FAIL): pytest 66/66 PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): null
