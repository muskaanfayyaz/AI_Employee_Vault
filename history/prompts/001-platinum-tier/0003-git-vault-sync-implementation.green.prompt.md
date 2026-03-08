---
id: "0003"
title: Git Vault Sync Implementation
stage: green
date: 2026-03-08
surface: agent
model: claude-sonnet-4-6
feature: 001-platinum-tier
branch: 001-platinum-tier
user: muskaan
command: /sp.implement
labels: ["platinum-tier","git-sync","claim-by-move","dashboard-lock","heartbeat","health-monitor","secrets-guard","green"]
links:
  spec: specs/001-platinum-tier/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/agents/__init__.py
  - src/agents/identity.py
  - src/agents/claim.py
  - src/sync/__init__.py
  - src/sync/git_sync.py
  - src/sync/secrets_guard.py
  - src/health/__init__.py
  - src/health/heartbeat.py
  - src/health/monitor.py
  - src/engine/dashboard_lock.py
  - src/skills/updates_merge.py
  - deploy/hooks/pre-commit
  - deploy/.env.example
  - .gitignore
tests:
  - Syntax check: 11/11 files PASS
  - Smoke tests: AgentIdentity, SecretsGuard, DashboardLock, ClaimService (atomic move), HeartbeatWriter, HealthMonitor — all PASS
---

## Prompt

Implement Git-based vault sync strategy.

Rules:
- Sync markdown only
- Exclude .env
- Cloud writes to /Updates
- Local merges into Dashboard
- Claim-by-move logic

## Response snapshot

Implemented 11 new Python modules + pre-commit hook + .env.example across 4 new packages:

**`src/agents/`** — Agent identity and task claiming
- `identity.py`: AgentIdentity reads AGENT_ID + AGENT_ENV env vars; `is_cloud` / `is_local` properties
- `claim.py`: ClaimService with atomic `os.rename()` claim-by-move; `complete()` routes cloud to `Updates/`, local to `Done/`; `recover_orphans()` returns timed-out tasks to `Needs_Action/`

**`src/sync/`** — Git vault synchronisation
- `git_sync.py`: GitSyncService — `pull --rebase`; `git add -- "*.md" "**/*.md"` (markdown only, .env excluded); exponential backoff + suspend on 3 consecutive failures; PM2-runnable standalone entry point
- `secrets_guard.py`: SecretsGuard — blocked filenames (.env, *.key, etc.), content regex patterns (API_KEY=, sk-ant-, AKIA..., high-entropy base64); `# nosecret` override; standalone `--staged` CLI for pre-commit hook

**`src/health/`** — Heartbeat and monitoring
- `heartbeat.py`: HeartbeatWriter — atomic JSON overwrite to `Logs/heartbeats/<agent_id>.json`; PM2-runnable
- `monitor.py`: HealthMonitor — staleness detection → `agent_down`/`agent_recovered` events; orphan task recovery; append-only JSONL alert log; PM2-runnable

**`src/engine/dashboard_lock.py`** — Single-writer lock
- `DashboardLock`: `fcntl.flock(LOCK_EX|LOCK_NB)` with stale-lock expiry (60s); context manager; Windows fallback (best-effort)

**`src/skills/updates_merge.py`** — Cloud-to-local merge
- `UpdatesMergeSkill`: reads `Updates/*.md` (cloud outputs); acquires DashboardLock; appends `## Cloud Updates` section to Dashboard.md; archives processed files to `Done/`

**`deploy/`** — Deployment artefacts
- `hooks/pre-commit`: shell hook invoking `python -m src.sync.secrets_guard --staged`
- `.env.example`: all required env vars documented

**`.gitignore`**: added `.env.*`, `*.key`, `*.pem`, `*secret*`, `.Dashboard.lock`, `*.tmp`, `node_modules/`

All 11 modules pass syntax check + smoke tests.

## Outcome

- ✅ Impact: Core Platinum Tier sync/safety infrastructure implemented and smoke-tested.
- 🧪 Tests: Syntax check 11/11 PASS; smoke tests for all 6 core classes PASS including atomic claim-by-move race simulation.
- 📁 Files: 11 Python modules + pre-commit hook + .env.example + .gitignore update
- 🔁 Next prompts: Write unit tests (`test_claim.py`, `test_dashboard_lock.py`, `test_git_sync.py`, etc.); integrate `ClaimService` into `main.py`; add `--cloud` flag to `main.py`; deploy to VM following `quickstart.md`.
- 🧠 Reflection: Cloud→local `Updates/` routing elegantly separates concerns without needing shared locks across VMs. DashboardLock Windows fallback ensures local agents on Windows still function (with warning) while production cloud always gets the hard POSIX guarantee.

## Evaluation notes (flywheel)

- Failure modes observed: HealthMonitor correctly detected stale heartbeat at `stale_minutes=0` in smoke test — confirms detection logic works.
- Graders run and results (PASS/FAIL): Syntax PASS (11/11). Smoke tests PASS (6/6 classes verified).
- Prompt variant (if applicable): User specified 5 concrete rules; all 5 mapped 1:1 to implementation decisions.
- Next experiment: Integration test — two concurrent ClaimService instances racing for the same task file; verify exactly one claim succeeds.
