---
id: "0005"
title: remove-duplicate-folders-gitignore-fix
stage: refactor
date: 2026-02-19
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: general
labels: ["cleanup","refactor","gitignore","duplicate-folders","watchers"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - .gitignore
tests:
  - tests/ (45/45 passed post-cleanup)
---

## Prompt

make sure there are duplicate folder which are present in root and src folder manage it and remove unnessesary

## Response snapshot

Audited all directories. Found one clear duplicate and one missing gitignore pattern.

**Removed:**
- `/watchers/` (root level) — contained empty stubs `base_watcher.py` and `filesystem_watcher.py` (1-line empty files). Real implementations are `src/watchers/base.py` and `src/watchers/filesystem.py`. This was the source of the user's confusion ("my file is empty").

**Kept — planned for Silver tier:**
- `src/approval/` — T031 will add `approval/manager.py` (human-in-the-loop flow)
- `src/mcp/` — MCP server implementations (Silver/Gold tiers)

**Fixed `.gitignore`** — added:
```
# Build artifacts
*.egg-info/
dist/
build/
```

**Tests: 45/45 passing** after cleanup.

## Outcome

- ✅ Impact: Root-level `watchers/` duplicate removed; project structure is clean
- 🧪 Tests: `pytest tests/ -q` → 45 passed, 0 failed
- 📁 Files: `.gitignore` (added egg-info/dist/build patterns)
- 🔁 Next prompts: Implement Silver tier (T027–T052)
- 🧠 Reflection: Empty stub files in a wrong location caused user confusion about which file contains the watcher implementation. Deleting the stubs prevents this confusion going forward.

## Evaluation notes (flywheel)

- Failure modes observed: Duplicate directory at root confused user into editing empty stubs instead of real implementation
- Graders run and results (PASS/FAIL): pytest 45/45 PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): null
