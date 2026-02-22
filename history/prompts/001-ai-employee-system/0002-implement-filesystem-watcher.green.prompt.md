---
id: "0002"
title: Implement Filesystem Watcher
stage: green
date: 2026-02-18
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.implement
labels: ["filesystem-watcher","watchdog","bronze","t020","dry-run","drop-folder"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/watchers/filesystem.py
  - drop_folder/.gitkeep
  - .env.example
  - specs/001-ai-employee-system/tasks.md
tests:
  - Manual e2e: drop file → Needs_Action copy + metadata.md created + audit log written
  - Manual DRY_RUN: no files copied when DRY_RUN=true
  - Observer probe: PollingObserver fallback verified on /mnt/d/ (WSL2/NTFS)
---

## Prompt

Implement filesystem watcher using watchdog.

Behavior:
- Monitor ./drop_folder
- When file created, copy to AI_Employee_Vault/Needs_Action
- Create metadata .md file
- Log action
- Respect DRY_RUN mode

## Response snapshot

Implemented `src/watchers/filesystem.py` (T020) extending `BaseWatcher` with:

1. **`_DropFolderHandler`** — watchdog `FileSystemEventHandler` that pushes created-file paths onto a `Queue`.
2. **`FilesystemWatcher`** — extends `BaseWatcher`:
   - `check_for_updates()`: drains queue → `_pending` dict; on subsequent calls returns paths that have been stable (no mtime change) for `stability_seconds` (default 2s).
   - `create_action_file()`: copies original to `Needs_Action/`, writes companion `<stem>-metadata.md` with YAML front-matter (Task Item schema), appends audit log entry to `Logs/YYYY-MM-DD.json`.
   - `start()`: uses `_make_observer()` probe — tries native inotify Observer, falls back to `PollingObserver` for WSL2/NTFS mounts.
   - `run()`: tight 0.5s stability-poll loop (overrides parent's coarser polling loop).
   - `health_check()`: returns `observer.is_alive()`.
3. **`_make_observer()`**: probes inotify by writing `.watcher_probe` and waiting 1s; falls back to `PollingObserver(timeout=1)`.
4. **`_resolve_dry_run()`**: tries `src.config.DRY_RUN` import, falls back to `os.getenv("DRY_RUN", "true")`.
5. **`.env.example`**: created with all config keys including `DRY_RUN=true` default.
6. **`drop_folder/`**: created with `.gitkeep`.

End-to-end verified on live vault:
- `PollingObserver` selected (WSL2 NTFS mount).
- File copied in ~2.5s (3 poll cycles at 0.5s).
- `test_watcher_demo-metadata.md` created with correct YAML front-matter.
- Audit log entry written to `Logs/2026-02-17.json`.
- DRY_RUN: no files copied, base class logs `[DRY_RUN] Would create action file for: ...`.

## Outcome

- ✅ Impact: T020 complete — Bronze-tier filesystem watcher operational end-to-end on the vault.
- 🧪 Tests: Manual e2e pass (both /tmp inotify and /mnt/d PollingObserver paths). DRY_RUN mode verified.
- 📁 Files: src/watchers/filesystem.py (new), drop_folder/.gitkeep (new), .env.example (new), tasks.md (T020 marked [x]).
- 🔁 Next prompts: T021 triage skill, T019 integration test (test_bronze_e2e.py), T002 pyproject.toml setup.
- 🧠 Reflection: WSL2 NTFS mounts don't support inotify — the probe-based observer selection pattern (`_make_observer`) is essential for cross-platform vault paths.

## Evaluation notes (flywheel)

- Failure modes observed: inotify silent failure on /mnt/d/ Windows FS mounts in WSL2 — no exception thrown, events simply don't fire. Detected via probe pattern.
- Graders run and results (PASS/FAIL): Manual e2e PASS, DRY_RUN PASS, PollingObserver fallback PASS.
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Add configurable poll_interval for PollingObserver; expose via env var WATCHER_POLL_INTERVAL.
