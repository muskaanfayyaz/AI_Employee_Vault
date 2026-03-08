---
id: "0002"
title: Platinum Tier Deployment Plan
stage: plan
date: 2026-03-08
surface: agent
model: claude-sonnet-4-6
feature: 001-platinum-tier
branch: 001-platinum-tier
user: muskaan
command: /sp.plan
labels: ["platinum-tier","cloud-deployment","pm2","git-sync","health-monitoring","nginx","https","backup","plan"]
links:
  spec: specs/001-platinum-tier/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/001-platinum-tier/plan.md
  - specs/001-platinum-tier/research.md
  - specs/001-platinum-tier/data-model.md
  - specs/001-platinum-tier/quickstart.md
  - specs/001-platinum-tier/contracts/file-contracts.md
  - history/prompts/001-platinum-tier/0002-platinum-tier-deployment-plan.plan.prompt.md
tests:
  - Constitution Check: all 7 principles PASS (no violations)
---

## Prompt

Create deployment plan:

- Cloud VM setup
- Git vault sync
- PM2 process management
- Environment separation
- Health monitoring
- Backup strategy
- HTTPS setup

## Response snapshot

Generated full Platinum Tier implementation plan at `specs/001-platinum-tier/plan.md` covering:

**Phase 0 Research** (`research.md`): 9 architectural decisions documented — claim-by-move atomicity (`os.rename`), dashboard single-writer (`fcntl.flock`), Git sync strategy (`pull --rebase` + 60s schedule), PM2 process management, agent identity via env vars, secrets guard (git hook + .gitignore), health monitoring (heartbeat JSON files + alert JSONL), HTTPS (Nginx + Let's Encrypt), backup (Git + daily tar.gz + optional rclone).

**Phase 1 Design** (`data-model.md`): Extended vault folder structure, file format contracts for Task files, Heartbeat JSON, Health Alert JSONL, Dashboard.md, Git sync state. New source packages: `src/sync/`, `src/agents/`, `src/health/`, `src/engine/dashboard_lock.py`. New `deploy/` directory with PM2, Nginx, hook, and provisioning script.

**Contracts** (`contracts/file-contracts.md`): 6 file contracts defined — Task Claim Protocol, Dashboard Write Protocol, Heartbeat Write Protocol, Health Alert Log Protocol, Git Sync Protocol, Secrets Guard Protocol.

**Quickstart** (`quickstart.md`): 10-step VM deployment guide from Ubuntu 22.04 provisioning through PM2 startup, HTTPS setup, and verification.

**Constitution Check**: All 7 principles PASS. No violations. PM2 complexity justified (multi-process > per-unit systemd files).

**Implementation Phases**: 5 phases (A–E) covering 27 tasks: Core Agent Infrastructure → Git Sync + Secrets Guard → Health Monitoring → Deployment → main.py Integration.

## Outcome

- ✅ Impact: Complete Platinum Tier implementation plan ready for task generation.
- 🧪 Tests: Constitution Check — 7/7 principles PASS. New test files: test_claim, test_dashboard_lock, test_git_sync, test_heartbeat, test_health_monitor, test_secrets_guard, test_multi_agent.
- 📁 Files: plan.md, research.md, data-model.md, quickstart.md, contracts/file-contracts.md
- 🔁 Next prompts: `/sp.tasks` to generate actionable task list; `/sp.adr` for significant architectural decisions.
- 🧠 Reflection: PM2 chosen over raw systemd for multi-process coordination and built-in monitoring endpoint. `fcntl.flock` is Linux-only — Windows local agents get a best-effort fallback (documented risk).

## Evaluation notes (flywheel)

- Failure modes observed: Script warned about duplicate 001 prefix (001-ai-employee-system + 001-platinum-tier) — functional but operators should be aware.
- Graders run and results (PASS/FAIL): Constitution Check PASS (7/7). Research.md covers all 9 decisions.
- Prompt variant (if applicable): User explicitly specified 7 deployment concerns (VM setup, git sync, PM2, env separation, health monitoring, backup, HTTPS) — all addressed.
- Next experiment: Run /sp.tasks to break Phase A–E into atomic implementable tasks with test cases.
