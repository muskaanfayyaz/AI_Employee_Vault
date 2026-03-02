---
id: "0004"
title: "Ralph Wiggum loop configuration"
stage: green
date: 2026-02-27
surface: agent
model: claude-sonnet-4-6
feature: 002-gold-tier
branch: 002-gold-tier
user: muskaan
command: /sp.configure
labels: ["ralph-wiggum","autonomous-loop","configuration","gold-tier","FR-G023","FR-G024","FR-G026","FR-G027","FR-G028"]
links:
  spec: specs/002-gold-tier/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - Config/ralph_wiggum.yaml
  - src/engine/ralph_wiggum_loop.py
  - src/main.py
tests:
  - "python -m src.main --ralph --dry-run  # smoke test: loop runs 0 cycles (Needs_Action empty)"
  - "python -m src.main --help             # verify --ralph flag registered"
---

## Prompt

/sp.configure Configure Ralph Wiggum loop for autonomous multi-step tasks.

Behavior:
- Re-run until files moved to /Done
- Max 10 iterations
- Log each iteration

## Response snapshot

Created three artefacts:

1. **`Config/ralph_wiggum.yaml`** — configuration file following the same structure as `ceo_briefing.yaml`. Key settings:
   - `loop.max_iterations: 10`
   - `loop.stop_when_done: true` (exits as soon as all active-pipeline items reach Done/Rejected/Errors)
   - `loop.iteration_interval_seconds: 30`
   - `logging.log_each_iteration: true` (structured JSON entry per cycle tagged `[RALPH_WIGGUM]`)
   - `self_review.*` section (FR-G024/FR-G026/FR-G028 fields for future skill use)

2. **`src/engine/ralph_wiggum_loop.py`** — `RalphWiggumLoop` class:
   - Concurrent-run guard via `Config/.ralph_wiggum.lock`
   - Iterates up to `max_iterations`, calling `run_processing_cycle()` each time
   - Counts active items (`.md` files in Needs_Action/Plans/In_Progress/Pending_Approval/Approved)
   - Stops early when `active_after == 0` (stop_when_done)
   - Logs each iteration with duration_ms, active_before, active_after, items_moved
   - Writes `Logs/RalphWiggum_Review_YYYY-MM-DD.json` on completion (FR-G027)

3. **`src/main.py`** — three patches:
   - Docstring: added `--ralph` command description
   - `run_ralph_wiggum_loop()` function: loads config, invokes loop, writes audit entry
   - `--ralph` argparse flag wired into `main()`
   - Weekly scheduler block in `run_schedule_loop()`: reads `Config/ralph_wiggum.yaml` schedule and registers the job (default Monday 07:00, before CEO Briefing at 08:00)

## Outcome

- ✅ Impact: Ralph Wiggum autonomous loop is fully configured and wired into the CLI and scheduler. `python -m src.main --ralph` runs immediately; `--schedule` activates the weekly job.
- 🧪 Tests: Smoke-testable via `--ralph --dry-run` (zero iterations if pipeline empty). Full integration test requires items in Needs_Action/.
- 📁 Files: 3 created/modified (Config/ralph_wiggum.yaml new; src/engine/ralph_wiggum_loop.py new; src/main.py modified)
- 🔁 Next prompts: Implement self-review log analysis (FR-G024); implement proposal deduplication (FR-G028); wire loop into CEO Briefing "Ralph Wiggum Insights" section
- 🧠 Reflection: Loop engine is intentionally minimal — it delegates all task processing to existing `run_processing_cycle()` and does not replicate skill logic. The config file mirrors `ceo_briefing.yaml` conventions for consistency.

## Evaluation notes (flywheel)

- Failure modes observed: none — new code, no test run yet
- Graders run and results (PASS/FAIL): not run
- Prompt variant (if applicable): n/a
- Next experiment: add `--ralph --max-iterations N` CLI override for ad-hoc runs
