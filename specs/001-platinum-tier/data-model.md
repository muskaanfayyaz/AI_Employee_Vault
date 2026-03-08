# Data Model: Platinum Tier — Always-On Cloud AI Employee

**Branch**: `001-platinum-tier` | **Date**: 2026-03-08 | **Phase**: 1

---

## Vault Folder Structure (extended for Platinum)

```text
<VAULT_ROOT>/
├── Inbox/                          # New tasks (unclaimed) [EXISTING: Needs_Action/]
├── In_Progress/
│   ├── cloud-vm-001/               # Tasks claimed by cloud agent
│   └── local-dev/                  # Tasks claimed by local agent
├── Pending_Approval/               # Tasks awaiting human review [EXISTING]
├── Approved/                       # Approved for execution [EXISTING]
├── Done/                           # Completed tasks [EXISTING]
├── Rejected/                       # Rejected tasks [EXISTING]
├── Errors/                         # Failed tasks [EXISTING]
├── Reports/                        # Skill output reports [EXISTING]
├── Logs/
│   ├── YYYY-MM-DD.json             # Audit log (append-only) [EXISTING]
│   ├── heartbeats/
│   │   ├── cloud-vm-001.json       # Cloud agent heartbeat
│   │   └── local-dev.json          # Local agent heartbeat
│   └── health-alerts.jsonl         # Health monitor alert log (append-only)
├── Config/                         # YAML configuration files [EXISTING]
├── Skills/                         # Skill documentation [EXISTING]
├── Dashboard.md                    # Shared agent status (single-writer) [EXISTING]
├── .Dashboard.lock                 # Dashboard write lock file (transient)
└── drop_folder/                    # File drop zone [EXISTING]
```

**NOTE**: The existing `Needs_Action/` folder acts as the Platinum `Inbox/`. The claim-by-move rule uses `In_Progress/<agent-id>/` as the claimed staging area, consistent with existing `In_Progress/` folder.

---

## File Formats

### Task File (`Inbox/<task-id>.md`)

```markdown
---
id: <uuid4>
created: <ISO-8601>
priority: P1|P2|P3
type: <task-type>
---

# <Task Title>

## Description
<Natural language description>

## Inputs
<Any relevant inputs, references, or attachments>

## Expected Output
<What the agent should produce>
```

**State transitions**:
```
Inbox/ → In_Progress/<agent-id>/ → Done/ | Errors/
Inbox/ → In_Progress/<agent-id>/ → Pending_Approval/ → Approved/ → Done/
Inbox/ → In_Progress/<agent-id>/ → Pending_Approval/ → Rejected/
```

**Timeout recovery**: If a file remains in `In_Progress/<agent-id>/` for more than `CLAIM_TIMEOUT_MINUTES` (default: 30) without a corresponding output, the health monitor moves it back to `Inbox/`.

---

### Heartbeat File (`Logs/heartbeats/<agent-id>.json`)

Written by each agent every `HEARTBEAT_INTERVAL_SECONDS` (default: 60). Overwritten each cycle (not appended).

```json
{
  "agent_id": "cloud-vm-001",
  "agent_env": "cloud",
  "hostname": "vm-hostname",
  "pid": 12345,
  "timestamp": "2026-03-08T14:30:00Z",
  "uptime_seconds": 86400,
  "tasks_completed_session": 42,
  "tasks_in_progress": 1,
  "last_task_id": "task-abc123",
  "last_task_completed": "2026-03-08T14:28:00Z",
  "status": "idle|processing|waiting|error",
  "git_sync_last_pull": "2026-03-08T14:29:45Z",
  "git_sync_last_push": "2026-03-08T14:29:50Z"
}
```

**Staleness threshold**: `HEARTBEAT_STALE_MINUTES` (default: 5). If `now - heartbeat.timestamp > threshold`, agent is considered down.

---

### Health Alert Log (`Logs/health-alerts.jsonl`)

Append-only JSONL file. Each line is one event.

```jsonl
{"timestamp":"2026-03-08T14:35:00Z","type":"agent_down","agent_id":"cloud-vm-001","last_seen":"2026-03-08T14:29:45Z","stale_seconds":315}
{"timestamp":"2026-03-08T14:40:00Z","type":"agent_recovered","agent_id":"cloud-vm-001","downtime_seconds":315}
{"timestamp":"2026-03-08T14:41:00Z","type":"task_orphaned","task_id":"task-abc123","agent_id":"cloud-vm-001","returned_to":"Inbox/"}
{"timestamp":"2026-03-08T14:42:00Z","type":"secret_blocked","file":".env","hook":"pre-commit","pattern":".env"}
```

---

### Dashboard File (`Dashboard.md`)

Single-writer (lock required before writing). Written by `DashboardSkill`.

```markdown
# AI Employee Dashboard

**Last Updated**: 2026-03-08 14:30:00 UTC | **Updated By**: cloud-vm-001

## Agent Status

| Agent | Environment | Status | Last Heartbeat | Tasks Done (Session) |
|-------|-------------|--------|----------------|----------------------|
| cloud-vm-001 | Cloud | 🟢 Online | 14:30:00 UTC | 42 |
| local-dev | Local | 🟡 Offline >2h | 12:15:00 UTC | 8 |

## Queue Summary

| Folder | Count |
|--------|-------|
| Inbox (unclaimed) | 3 |
| In Progress | 1 |
| Pending Approval | 2 |
| Done (today) | 12 |
| Errors (today) | 0 |

## Recent Activity

- 14:28 — `cloud-vm-001` completed `task-abc123`
- 14:15 — `cloud-vm-001` completed `task-def456`
- 12:10 — `local-dev` completed `task-ghi789`

## Health Alerts

_No active alerts._
```

---

### Git Sync State (`Config/git_sync_state.json`)

Written by the `GitSyncService` after each successful sync. Kept in `Config/` (synced with vault so both agents can see it).

```json
{
  "agent_id": "cloud-vm-001",
  "last_pull": "2026-03-08T14:29:45Z",
  "last_push": "2026-03-08T14:29:50Z",
  "last_commit": "abc1234",
  "sync_errors": 0,
  "consecutive_failures": 0
}
```

---

## Entity Relationships

```text
Agent (local or cloud)
  │
  ├── writes → Heartbeat File (overwrite)
  ├── claims → Task File (move: Inbox → In_Progress/<agent-id>/)
  ├── produces → Output File (write to Done/)
  ├── writes → Audit Log (append)
  ├── acquires lock → .Dashboard.lock
  └── writes → Dashboard.md (after lock acquired)

Health Monitor
  ├── reads → all Heartbeat Files
  ├── reads → In_Progress/ (orphan detection)
  ├── writes → health-alerts.jsonl (append)
  └── moves → orphaned Task Files (In_Progress → Inbox)

Git Sync Service
  ├── pulls → remote Git repo
  ├── pushes → committed vault changes
  └── writes → Config/git_sync_state.json

Secrets Guard (pre-commit hook)
  ├── scans → staged files
  ├── blocks → commit on secret detection
  └── writes → health-alerts.jsonl (if integrated)
```

---

## Configuration Schema (`Config/platinum.yaml`)

```yaml
agent:
  id: "cloud-vm-001"         # AGENT_ID (override via env var)
  env: "cloud"               # AGENT_ENV: cloud | local

sync:
  interval_seconds: 60
  strategy: "rebase"         # pull strategy: rebase | merge
  push_after_task: true      # push immediately after task completion
  conflict_strategy: "theirs" # for shared files; "ours" for output files

claim:
  timeout_minutes: 30        # orphan recovery timeout

dashboard:
  lock_stale_seconds: 60     # stale lock expiry
  update_interval_seconds: 30

heartbeat:
  interval_seconds: 60
  stale_minutes: 5

health_monitor:
  check_interval_seconds: 60
  alert_log: "Logs/health-alerts.jsonl"

backup:
  enabled: true
  local_path: "/backups/vault"
  retention_days: 30
  rclone_remote: ""          # e.g., "s3:my-bucket" (leave empty to disable)
```

---

## Source Code Structure (additions to existing `src/`)

```text
src/
├── [EXISTING: engine/, skills/, watchers/, models/, approval/, mcp/]
├── sync/
│   ├── __init__.py
│   ├── git_sync.py          # GitSyncService: pull, push, conflict handling
│   └── secrets_guard.py     # SecretsGuard: pattern scanner for pre-commit hook
├── agents/
│   ├── __init__.py
│   ├── identity.py          # AgentIdentity: reads AGENT_ID, AGENT_ENV
│   └── claim.py             # ClaimService: atomic move + orphan recovery
├── health/
│   ├── __init__.py
│   ├── heartbeat.py         # HeartbeatWriter: periodic JSON file update
│   └── monitor.py           # HealthMonitor: staleness detection + alerts
└── engine/
    └── dashboard_lock.py    # DashboardLock: fcntl.flock wrapper with stale detection

deploy/
├── ecosystem.config.js      # PM2 multi-process config
├── nginx.conf               # HTTPS reverse proxy config
├── setup-vm.sh              # One-shot VM provisioning script
├── .env.example             # All required env vars documented
└── hooks/
    └── pre-commit           # Git pre-commit secrets guard hook

tests/
├── unit/
│   ├── test_claim.py        # Claim-by-move atomic race tests
│   ├── test_dashboard_lock.py  # Lock + stale detection tests
│   ├── test_git_sync.py     # Sync scheduling + conflict handling tests
│   ├── test_heartbeat.py    # Heartbeat write/read tests
│   ├── test_health_monitor.py  # Staleness + alert tests
│   └── test_secrets_guard.py   # Pattern detection tests
└── integration/
    └── test_multi_agent.py  # Two-agent concurrent processing tests
```
