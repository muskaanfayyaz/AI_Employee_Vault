# File Contracts: Platinum Tier

**Branch**: `001-platinum-tier` | **Date**: 2026-03-08

These contracts define the stable interfaces between agents, services, and the vault file system. Any code that reads or writes these files MUST conform to these contracts.

---

## Contract 1: Task Claim Protocol

### Participants
- **Producer**: Any agent or human writing a task to `Needs_Action/` (Inbox)
- **Consumer**: Any agent performing the claim-by-move

### Preconditions
- Task file exists in `Needs_Action/` with a `.md` extension
- Task file YAML front-matter contains `id`, `created`, `type` fields

### Claim Operation
```python
# Atomic claim — MUST use os.rename (not copy+delete)
source = vault_root / "Needs_Action" / task_filename
dest_dir = vault_root / "In_Progress" / agent_id
dest_dir.mkdir(parents=True, exist_ok=True)
dest = dest_dir / task_filename

try:
    source.rename(dest)   # atomic: raises FileNotFoundError if already claimed
    # → claim SUCCEEDED: proceed to process
except FileNotFoundError:
    # → claim FAILED: another agent claimed first. Skip silently.
    pass
```

### Postconditions (success)
- `source` no longer exists in `Needs_Action/`
- `dest` exists in `In_Progress/<agent-id>/`
- No other agent holds this task (atomic guarantee)

### Postconditions (failure / race)
- `source` no longer exists (claimed by another agent)
- `dest` does NOT exist for this agent
- Caller must silently skip this task

### Timeout / Orphan Recovery
- After `CLAIM_TIMEOUT_MINUTES` (default: 30), health monitor moves files from `In_Progress/<agent-id>/` back to `Needs_Action/`
- Recovery is logged to `Logs/health-alerts.jsonl` as `task_orphaned`

---

## Contract 2: Dashboard Write Protocol

### Participants
- **Writer**: Any agent's `DashboardSkill`
- **Lock file**: `<VAULT_ROOT>/.Dashboard.lock`
- **Target**: `<VAULT_ROOT>/Dashboard.md`

### Write Operation (MUST be followed exactly)
```python
lock_path = vault_root / ".Dashboard.lock"
tmp_path = vault_root / ".Dashboard.md.tmp"
dashboard_path = vault_root / "Dashboard.md"
STALE_SECONDS = int(os.getenv("DASHBOARD_LOCK_STALE_SECONDS", "60"))

import fcntl, time

def acquire_lock(lock_path, stale_seconds):
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file  # caller must close to release
    except BlockingIOError:
        # Check if stale
        mtime = lock_path.stat().st_mtime
        if time.time() - mtime > stale_seconds:
            lock_path.unlink(missing_ok=True)
            return acquire_lock(lock_path, stale_seconds)  # retry once
        return None  # lock held, skip this cycle

lock_file = acquire_lock(lock_path, STALE_SECONDS)
if lock_file is None:
    return  # skip — dashboard will be updated next cycle

try:
    tmp_path.write_text(generate_dashboard_content(), encoding="utf-8")
    tmp_path.rename(dashboard_path)   # atomic replace
finally:
    fcntl.flock(lock_file, fcntl.LOCK_UN)
    lock_file.close()
    lock_path.unlink(missing_ok=True)
```

### Invariants
- `Dashboard.md` MUST never be in a partially-written state
- Lock acquisition MUST be non-blocking (use `LOCK_NB`)
- Stale lock (> `STALE_SECONDS` old) MAY be force-released by any agent
- Temporary file (`.Dashboard.md.tmp`) MUST be renamed atomically

---

## Contract 3: Heartbeat Write Protocol

### Participants
- **Writer**: Each agent's `HeartbeatWriter`
- **Target**: `Logs/heartbeats/<agent-id>.json`
- **Reader**: `HealthMonitor` process

### Write Schema (REQUIRED fields)
```json
{
  "agent_id": "<string: AGENT_ID env var>",
  "agent_env": "<string: 'cloud' | 'local'>",
  "timestamp": "<string: ISO-8601 UTC>",
  "status": "<string: 'idle' | 'processing' | 'waiting' | 'error'>"
}
```

### Write Schema (OPTIONAL fields)
```json
{
  "hostname": "<string>",
  "pid": "<integer>",
  "uptime_seconds": "<integer>",
  "tasks_completed_session": "<integer>",
  "tasks_in_progress": "<integer>",
  "last_task_id": "<string | null>",
  "last_task_completed": "<string: ISO-8601 | null>",
  "git_sync_last_pull": "<string: ISO-8601 | null>",
  "git_sync_last_push": "<string: ISO-8601 | null>"
}
```

### Write Rules
- Write interval: every `HEARTBEAT_INTERVAL_SECONDS` (default: 60)
- Write mode: **overwrite** (not append) — only the latest heartbeat matters
- Write atomically: write to `<agent-id>.json.tmp`, then rename
- `Logs/heartbeats/` directory MUST be created if it does not exist

### Read Rules (HealthMonitor)
- Read all `*.json` files in `Logs/heartbeats/`
- Parse `timestamp` field; compare to `now(UTC)`
- If `now - timestamp > HEARTBEAT_STALE_MINUTES * 60`: agent is DOWN
- If previously DOWN and `timestamp` is fresh: agent is RECOVERED

---

## Contract 4: Health Alert Log Protocol

### Participants
- **Writer**: `HealthMonitor`
- **Target**: `Logs/health-alerts.jsonl`
- **Readers**: Operators, dashboard skill, future notification integrations

### Write Rules
- Append-only; MUST NOT truncate or overwrite existing content
- Each line is a valid JSON object (JSONL format)
- Write atomically: use file lock or serialize writes (monitor is single-process)

### Event Schema

**Agent Down**
```json
{"timestamp":"<ISO-8601>","type":"agent_down","agent_id":"<id>","last_seen":"<ISO-8601>","stale_seconds":<int>}
```

**Agent Recovered**
```json
{"timestamp":"<ISO-8601>","type":"agent_recovered","agent_id":"<id>","downtime_seconds":<int>}
```

**Task Orphaned**
```json
{"timestamp":"<ISO-8601>","type":"task_orphaned","task_id":"<filename>","agent_id":"<id>","returned_to":"Needs_Action/"}
```

**Secret Blocked**
```json
{"timestamp":"<ISO-8601>","type":"secret_blocked","file":"<filename>","pattern":"<matched-pattern>"}
```

---

## Contract 5: Git Sync Protocol

### Participants
- **Runner**: `GitSyncService`
- **Schedule**: every `GIT_SYNC_INTERVAL_SECONDS` (default: 60) + on task completion

### Pull Operation
```bash
git -C <VAULT_ROOT> fetch origin
git -C <VAULT_ROOT> pull --rebase origin main
```

### Push Operation
```bash
git -C <VAULT_ROOT> add -A
git -C <VAULT_ROOT> commit -m "agent: <AGENT_ID> sync <ISO-8601>" --no-verify
git -C <VAULT_ROOT> push origin main
```

**`--no-verify` on commit**: The secrets pre-commit hook runs on `git commit`. The `--no-verify` flag MUST NOT be used in automated sync commits. Remove this flag from any production sync script. The hook is the last line of defence.

### Conflict Handling
- On `pull --rebase` conflict: run `git rebase --abort`, log error, increment `consecutive_failures`
- After 3 consecutive failures: write alert to `health-alerts.jsonl` and pause sync for 5 minutes
- Dashboard.md conflicts: always take `--theirs` (latest writer wins)
- Output file conflicts: should not occur (unique filenames); if they do, take `--ours` and alert

### Never-Sync Paths
These paths MUST be in `.gitignore` and the pre-commit hook MUST block their staging:
```
.env
.env.*
*.key
*.pem
*.p12
*secret*
credentials*
token*
.Dashboard.lock
*.tmp
__pycache__/
.venv/
```

---

## Contract 6: Secrets Guard Protocol

### Participants
- **Runner**: Git pre-commit hook at `<VAULT_ROOT>/.git/hooks/pre-commit`
- **Trigger**: Every `git commit` within the vault directory

### Detection Patterns
```python
BLOCKED_FILENAMES = {".env", "credentials.json", ".netrc"}
BLOCKED_EXTENSIONS = {".key", ".pem", ".p12", ".pfx", ".pkcs12"}
BLOCKED_PATTERNS = [
    r"\.env(\.[a-z]+)?$",          # .env, .env.local, .env.production
    r"\*secret\*",                 # any filename with "secret"
    r"credentials",
]
CONTENT_PATTERNS = [
    r"(?i)(api[_-]?key|secret|token|password|passwd)\s*=\s*\S{8,}",
    r"[A-Za-z0-9+/]{40,}={0,2}",  # high-entropy base64 strings
]
```

### Hook Behaviour
- Exit code 0: commit proceeds normally
- Exit code 1: commit is blocked; print offending file and line
- Log blocked attempt to `Logs/health-alerts.jsonl` if vault is already initialized

### Operator Override
- If a file is legitimately high-entropy (e.g., a public key for SSH known-hosts), the operator may add a `# nosecret` comment on that line or add the file to `.secretsignore` in the vault root.
