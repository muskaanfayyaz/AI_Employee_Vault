# Implementation Plan: Platinum Tier — Always-On Cloud AI Employee

**Branch**: `001-platinum-tier` | **Date**: 2026-03-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-platinum-tier/spec.md`

---

## Summary

Extend the Gold Tier AI Employee system to Platinum Tier by adding always-on cloud deployment on a Linux VM, safe multi-agent coordination (claim-by-move + single-writer dashboard), Git-based vault sync, secrets guard, health monitoring, PM2 process management, HTTPS monitoring endpoint, and a backup strategy. The single Python codebase runs on both local and cloud — only `.env` configuration diverges.

---

## Technical Context

**Language/Version**: Python 3.12 (existing; no change)
**Primary Dependencies**: watchdog 4.x, schedule 1.2, python-dotenv 1.0, PyYAML 6.0, fcntl (stdlib), subprocess (stdlib, for git), PM2 (Node.js, process manager on VM)
**Storage**: File-based (vault folder tree as database; Git as version history)
**Testing**: pytest (existing); new unit tests for claim/lock/sync/health modules
**Target Platform**: Linux VM (Ubuntu 22.04 LTS) for cloud agent; Windows/Mac/Linux for local agent
**Project Type**: Single Python project, multi-environment deployment
**Performance Goals**: Task end-to-end latency ≤ 10 minutes; Git sync ≤ 60s round-trip; heartbeat freshness ≤ 60s
**Constraints**: Secrets never in vault/Git; no external database; file-based state only (constitution IV); all operations logged (constitution VI); graceful shutdown + auto-restart (constitution VII)
**Scale/Scope**: 2 concurrent agents (1 local + 1 cloud); ~100 tasks/day; single vault Git repo

---

## Constitution Check

| Principle | Assessment | Status |
|-----------|------------|--------|
| I. Human Sovereignty | Claim-by-move and dashboard writes are automated but non-financial; sensitive actions still require approval gate | ✅ PASS |
| II. Privacy First | Secrets in `.env` outside vault; pre-commit hook blocks accidental secret commits; Git sync only pushes vault files | ✅ PASS |
| III. Agent Skills First | New capabilities (GitSyncService, HeartbeatWriter, HealthMonitor, ClaimService) implemented as structured, testable modules with defined interfaces | ✅ PASS |
| IV. File-Based State | All state in vault files: heartbeats, alerts, tasks, dashboard. No external database. `os.rename()` for atomic transitions | ✅ PASS |
| V. Human-in-the-Loop | No new financial/destructive gates added. Existing approval gates preserved. Health alerts surface to human via file | ✅ PASS |
| VI. Audit Logging | All agent actions logged to `Logs/YYYY-MM-DD.json`. Health events to `health-alerts.jsonl`. Git history is implicit audit trail | ✅ PASS |
| VII. Graceful Failure | PM2 auto-restart; exponential backoff in GitSyncService on failure; stale lock release; orphan task recovery; DRY_RUN mode preserved | ✅ PASS |

**GATE: PASSED** — All 7 principles satisfied. No violations or justifications required.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-platinum-tier/
├── plan.md              # This file (/sp.plan output)
├── research.md          # Phase 0: all architectural decisions
├── data-model.md        # Phase 1: vault structure + file formats
├── quickstart.md        # Phase 1: VM deployment guide
├── contracts/
│   └── file-contracts.md   # Phase 1: file interface contracts
├── checklists/
│   └── requirements.md     # Spec quality checklist
└── tasks.md             # Phase 2 output (/sp.tasks — NOT created here)
```

### Source Code (additions to existing `src/`)

```text
src/
├── [EXISTING — unchanged]
│   ├── engine/           # state_machine, scheduler, logger, ralph loop, retry
│   ├── skills/           # triage, planner, executor, dashboard, etc.
│   ├── watchers/         # filesystem, gmail, whatsapp, linkedin, odoo
│   ├── models/           # task_item, log_entry, plan, approval
│   ├── approval/         # manager
│   ├── mcp/              # email_server, social_server, base
│   ├── config.py
│   └── main.py           # extended with --cloud flag
│
├── sync/                 # NEW: Git vault synchronisation
│   ├── __init__.py
│   ├── git_sync.py       # GitSyncService: pull/push/conflict handling
│   └── secrets_guard.py  # SecretsGuard: pattern scanner
│
├── agents/               # NEW: Agent identity + task claiming
│   ├── __init__.py
│   ├── identity.py       # AgentIdentity: AGENT_ID, AGENT_ENV
│   └── claim.py          # ClaimService: atomic move + orphan recovery
│
└── health/               # NEW: Heartbeat + monitoring
    ├── __init__.py
    ├── heartbeat.py      # HeartbeatWriter: periodic JSON write
    └── monitor.py        # HealthMonitor: staleness detection + alerts

src/engine/
└── dashboard_lock.py     # NEW: DashboardLock: fcntl.flock + stale detection

deploy/                   # NEW: Deployment configuration
├── ecosystem.config.js   # PM2 multi-process config
├── nginx.conf            # HTTPS reverse proxy
├── setup-vm.sh           # One-shot VM provisioning script
├── .env.example          # Documented env vars (all required)
└── hooks/
    └── pre-commit        # Git secrets guard hook (shell script)

tests/
├── unit/                 # NEW tests
│   ├── test_claim.py
│   ├── test_dashboard_lock.py
│   ├── test_git_sync.py
│   ├── test_heartbeat.py
│   ├── test_health_monitor.py
│   └── test_secrets_guard.py
└── integration/
    └── test_multi_agent.py
```

**Structure Decision**: Single-project structure (Option 1) extended with three new source packages (`sync/`, `agents/`, `health/`) and a `deploy/` directory. All new code lives alongside existing `src/` packages. No new top-level project or monorepo split needed.

---

## Architecture Overview

```text
┌─────────────────────────────┐     ┌──────────────────────────────────┐
│       LOCAL MACHINE          │     │          CLOUD VM (Ubuntu 22.04) │
│                             │     │                                  │
│  ┌─────────────────────┐   │     │  ┌──────────────────────────┐   │
│  │  Local Agent         │   │     │  │  Cloud Agent (PM2)        │   │
│  │  python -m src.main  │   │     │  │  ai-employee-cloud        │   │
│  │  --schedule --cloud  │   │     │  │  python -m src.main       │   │
│  │                      │   │     │  │  --schedule --cloud        │   │
│  │  AgentID: local-dev  │   │     │  │  AgentID: cloud-vm-001    │   │
│  └──────────┬───────────┘   │     │  └────────────┬─────────────┘   │
│             │               │     │               │                  │
│  ┌──────────▼───────────┐   │     │  ┌────────────▼─────────────┐   │
│  │  GitSyncService       │   │     │  │  GitSyncService (PM2)     │   │
│  │  pull every 60s       │   │     │  │  git-sync process        │   │
│  │  push after task      │   │     │  └────────────┬─────────────┘   │
│  └──────────┬───────────┘   │     │               │                  │
│             │               │     │  ┌────────────▼─────────────┐   │
│             │               │     │  │  HealthMonitor (PM2)      │   │
│             │               │     │  │  health-monitor process   │   │
└─────────────┼───────────────┘     └──┼──────────────────────────────┘
              │                        │
              ▼                        ▼
        ┌─────────────────────────────────┐
        │         Git Remote Repo         │
        │   (GitHub / GitLab / self-host) │
        │                                 │
        │   vault/                        │
        │   ├── Needs_Action/             │
        │   ├── In_Progress/              │
        │   ├── Done/                     │
        │   ├── Logs/heartbeats/          │
        │   ├── Dashboard.md             │
        │   └── ...                      │
        └─────────────────────────────────┘

        HTTPS Monitor (Nginx + Let's Encrypt)
        ┌─────────────────────────────────┐
        │  https://monitor.yourdomain.com │
        │  → Nginx → PM2 Web (port 9615)  │
        │  Basic auth + TLS              │
        └─────────────────────────────────┘
```

---

## Component Design

### `src/sync/git_sync.py` — GitSyncService

**Interface**:
```python
class GitSyncService:
    def __init__(self, vault_root: Path, agent_id: str, config: dict): ...
    def pull(self) -> SyncResult: ...   # git pull --rebase; returns ok/error
    def push(self, message: str) -> SyncResult: ...  # git commit + push
    def sync(self) -> SyncResult: ...   # pull then push (scheduled)
    def run_forever(self): ...          # blocking loop; used by standalone process
```

**Error handling**: Exponential backoff (1s → 2s → 4s → max 60s) on failure. After 3 consecutive failures, write to `health-alerts.jsonl` and suspend for 5 minutes.

---

### `src/agents/claim.py` — ClaimService

**Interface**:
```python
class ClaimService:
    def __init__(self, vault_root: Path, agent_id: str, timeout_minutes: int = 30): ...
    def claim(self, task_file: Path) -> bool: ...       # atomic rename; True = claimed
    def list_unclaimed(self) -> list[Path]: ...         # files in Needs_Action/
    def recover_orphans(self) -> list[Path]: ...        # return timed-out In_Progress/ tasks
```

---

### `src/health/heartbeat.py` — HeartbeatWriter

**Interface**:
```python
class HeartbeatWriter:
    def __init__(self, vault_root: Path, agent_id: str, agent_env: str): ...
    def write(self, status: str, **extra_fields): ...  # atomic overwrite of heartbeat JSON
    def run_forever(self, interval_seconds: int = 60): ...  # blocking loop
```

---

### `src/health/monitor.py` — HealthMonitor

**Interface**:
```python
class HealthMonitor:
    def __init__(self, vault_root: Path, stale_minutes: int = 5): ...
    def check_all(self) -> list[HealthEvent]: ...  # returns new alert events
    def run_forever(self, interval_seconds: int = 60): ...  # blocking loop
```

---

### `src/engine/dashboard_lock.py` — DashboardLock

**Interface**:
```python
class DashboardLock:
    def __init__(self, vault_root: Path, stale_seconds: int = 60): ...
    def acquire(self) -> bool: ...   # non-blocking; True = acquired
    def release(self): ...
    def __enter__(self) -> bool: ...  # context manager
    def __exit__(self, *args): ...
```

---

### `deploy/ecosystem.config.js` — PM2 Config

```javascript
module.exports = {
  apps: [
    {
      name: "ai-employee-cloud",
      script: "src/main.py",
      interpreter: "/home/ubuntu/vault/.venv/bin/python3",
      args: "--schedule --cloud",
      cwd: "/home/ubuntu/vault",
      env_file: "/home/ubuntu/.ai-employee.env",
      restart_delay: 5000,
      max_restarts: 10,
      autorestart: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
    {
      name: "git-sync",
      script: "src/sync/git_sync.py",
      interpreter: "/home/ubuntu/vault/.venv/bin/python3",
      cwd: "/home/ubuntu/vault",
      env_file: "/home/ubuntu/.ai-employee.env",
      restart_delay: 5000,
      autorestart: true,
    },
    {
      name: "health-monitor",
      script: "src/health/monitor.py",
      interpreter: "/home/ubuntu/vault/.venv/bin/python3",
      cwd: "/home/ubuntu/vault",
      env_file: "/home/ubuntu/.ai-employee.env",
      restart_delay: 5000,
      autorestart: true,
    },
    {
      name: "backup",
      script: "src/sync/backup.py",
      interpreter: "/home/ubuntu/vault/.venv/bin/python3",
      cwd: "/home/ubuntu/vault",
      env_file: "/home/ubuntu/.ai-employee.env",
      cron_restart: "0 2 * * *",  // 2am UTC daily
      autorestart: false,
    },
  ],
};
```

---

### `deploy/nginx.conf` — HTTPS Config

```nginx
server {
    listen 80;
    server_name monitor.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name monitor.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/monitor.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/monitor.yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;

    auth_basic "AI Employee Monitor";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:9615;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

---

## Implementation Phases (for `/sp.tasks` input)

### Phase A: Core Agent Infrastructure (P1 + P2)
1. `src/agents/identity.py` — AgentIdentity class
2. `src/agents/claim.py` — ClaimService with atomic rename + orphan recovery
3. `src/engine/dashboard_lock.py` — DashboardLock with fcntl + stale detection
4. Integrate ClaimService into processing cycle (`main.py`)
5. Integrate DashboardLock into DashboardSkill
6. Unit tests: `test_claim.py`, `test_dashboard_lock.py`

### Phase B: Git Sync + Secrets Guard (P3 + P6)
7. `src/sync/git_sync.py` — GitSyncService with pull/push/backoff
8. `src/sync/secrets_guard.py` — SecretsGuard pattern scanner
9. `deploy/hooks/pre-commit` — Git hook shell script
10. `.gitignore` updates for vault
11. Unit tests: `test_git_sync.py`, `test_secrets_guard.py`
12. Integration: wire GitSyncService into Scheduler

### Phase C: Health Monitoring (P7)
13. `src/health/heartbeat.py` — HeartbeatWriter
14. `src/health/monitor.py` — HealthMonitor
15. `Logs/heartbeats/` folder creation in `init_vault()`
16. Dashboard updated to show agent health status
17. Unit tests: `test_heartbeat.py`, `test_health_monitor.py`

### Phase D: Deployment (P1 FR-012)
18. `deploy/ecosystem.config.js` — PM2 config
19. `deploy/nginx.conf` — HTTPS reverse proxy config
20. `deploy/setup-vm.sh` — one-shot provisioning script
21. `deploy/.env.example` — documented env vars
22. `src/sync/backup.py` — nightly vault backup script
23. Integration tests: `test_multi_agent.py`

### Phase E: main.py Integration + `--cloud` flag
24. Add `--cloud` argument to `main.py`
25. Wire HeartbeatWriter into schedule loop
26. Wire ClaimService as default claim mechanism
27. End-to-end smoke test via quickstart.md Step 9

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Git push conflict between local + cloud agents | Medium | Medium | `pull --rebase` + per-agent file namespaces; conflict alert on 3 failures |
| `fcntl.flock` not available on Windows local agent | High | Low | Cloud agent is Linux-only; local Windows agent falls back to best-effort write (log warning) |
| PM2 restarts agent mid-task, causing orphan | Low | Medium | Orphan recovery in HealthMonitor (30-min timeout + return to Inbox) |
| Secrets accidentally committed before hook installed | Low | High | `.gitignore` as first layer; hook as second; document in quickstart Step 5 |
| VM disk fills up (logs + backups) | Low | High | Log rotation via `pm2-logrotate`; 30-day backup retention; `df` alert in health monitor |

---

## Complexity Tracking

No constitution violations. All complexity is justified by the feature requirements:

| Component | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| fcntl.flock | Dashboard single-writer across processes | threading.Lock is in-process only |
| PM2 (not systemd) | Multi-process management + log aggregation | Raw systemd requires one unit file per process; harder to manage |
| pre-commit hook | Secrets guard enforcement | .gitignore alone doesn't block `git add` of already-existing files |
