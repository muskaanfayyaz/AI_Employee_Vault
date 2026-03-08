# Research: Platinum Tier — Always-On Cloud AI Employee

**Branch**: `001-platinum-tier` | **Date**: 2026-03-08 | **Phase**: 0

---

## Decision 1: Claim-by-Move Atomicity Mechanism

**Decision**: Use Python's `Path.rename()` (wraps `rename(2)` syscall) for atomic task claiming.

**Rationale**:
- `rename(2)` is atomic within a single filesystem partition on Linux — either the rename succeeds entirely or it doesn't happen.
- The vault files (Inbox → In_Progress) will always be on the same partition (single VM disk or single NFS mount), so the atomicity guarantee holds.
- If two agents call `rename()` simultaneously for the same source file, only one will succeed; the other receives `FileNotFoundError` (POSIX) or `FileExistsError` — both are handleable without data corruption.
- No external lock manager, Redis, or database required. Fits the File-Based State principle.

**Alternatives Considered**:
- *fcntl advisory locks*: Requires both agents to cooperate on a shared lock file. Cross-process on the same machine works; cross-VM does not (lock files are not visible across VMs). Rejected.
- *Git-based locking (branch per task)*: Extremely heavyweight; adds Git round-trips to every claim. Rejected.
- *Database (SQLite, PostgreSQL)*: Violates File-Based State constitution principle. Rejected.

**Constraint**: The claim-by-move rule only guarantees single-claim within one VM. Between the local machine and the cloud VM, the Git sync interval (60 seconds) creates the isolation window — agents on different machines will not see the same file simultaneously if sync is working correctly. The `In_Progress/<agent-id>/` subfolder convention further disambiguates post-hoc.

---

## Decision 2: Dashboard Single-Writer Lock

**Decision**: File-based exclusive lock using Python's `fcntl.flock(LOCK_EX | LOCK_NB)` with a stale-lock timeout.

**Rationale**:
- `fcntl.flock()` is available on all POSIX systems (Linux, macOS) — works on the local machine and the cloud VM.
- `LOCK_NB` (non-blocking) means a waiting agent immediately knows the lock is held and can retry or skip — no deadlock possible.
- A separate `.Dashboard.lock` file holds the lock; the dashboard file itself is only written after the lock is acquired.
- Stale lock detection: if the lock file's `mtime` is older than 60 seconds, any agent may delete it and re-acquire (handles crashes).

**Lock Protocol**:
1. Open `.Dashboard.lock` for writing.
2. Call `flock(LOCK_EX | LOCK_NB)`.
3. If `BlockingIOError`: check lock file `mtime`. If > 60s old, delete and retry from step 1. Else skip this write cycle.
4. Write `Dashboard.md` atomically (write to `.Dashboard.md.tmp` then rename).
5. Release lock (`flock(LOCK_UN)`).

**Alternatives Considered**:
- *`threading.Lock()`*: In-process only — does not work between separate agent processes. Rejected.
- *Redis SETNX*: Requires running Redis; violates simplicity and file-based constitution principle. Rejected.
- *Disable concurrent dashboard writes (round-robin schedule)*: Complex coordination; doesn't scale. Rejected.

---

## Decision 3: Git Vault Sync Strategy

**Decision**: Python subprocess calling `git` CLI on a 60-second schedule using rebase strategy (`git pull --rebase`).

**Rationale**:
- `git pull --rebase` keeps local commits on top of remote changes, minimising merge conflict noise.
- Each agent writes to separate files (its own heartbeat file, its own output files) — true merge conflicts are rare.
- The sync process runs as a scheduled job within the existing `Scheduler` infrastructure.
- Git SSH key authentication is used on the VM (deploy key stored outside the vault in `~/.ssh/`).

**Conflict Resolution Strategy**:
- **Theirs-wins for shared state files** (Dashboard.md, heartbeats): Use `git checkout --theirs` on conflict.
- **Ours-wins for output files**: Each agent writes to uniquely-named output files; conflicts should not occur.
- **Abort on unresolvable conflict**: Log error, surface alert, do not auto-force-push.

**Sync Schedule**:
- Pull: every 60 seconds.
- Push: after every successful task completion and on a 60-second heartbeat push schedule.
- Net latency: worst-case 120 seconds (60s pull + 60s push) for end-to-end task visibility.

**Alternatives Considered**:
- *Syncthing / rsync*: No version history, no conflict resolution. Rejected.
- *`git merge` (instead of rebase)*: Creates merge commits that pollute the vault history. Rejected.
- *Polling remote via GitPython library*: Adds dependency; subprocess `git` is simpler and more debuggable. Rejected.

---

## Decision 4: Process Management — PM2

**Decision**: Use PM2 for cloud VM process management.

**Rationale**:
- PM2 supports any interpreter via `interpreter: "python3"` in `ecosystem.config.js`.
- `pm2 startup` + `pm2 save` generates and installs a systemd service to auto-start processes on reboot — satisfying FR-001 (always-on).
- Built-in log rotation (`pm2 install pm2-logrotate`), process monitoring (`pm2 monit`), and HTTP status endpoint (`pm2 web`).
- `pm2 reload` enables zero-downtime restarts during deployments.
- Familiar to operators who already use Node.js tooling; simpler than writing raw systemd unit files for multi-process setups.

**PM2 Process Inventory**:
| Name | Script | Mode | Restart Policy |
|------|--------|------|----------------|
| `ai-employee-cloud` | `src/main.py --cloud --schedule` | fork | always |
| `git-sync` | `src/sync/git_sync.py` | fork | always |
| `health-monitor` | `src/health/monitor.py` | fork | always |

**Alternatives Considered**:
- *Raw systemd unit files*: Sufficient for single process; PM2 is better for multi-process coordination and log aggregation. Remains as fallback if PM2 is unavailable.
- *Docker Compose*: Heavier; adds container overhead for what is fundamentally a single-machine deployment. Deferred to future tier.
- *Supervisor*: Older Python-native alternative; PM2 has better log management and the `pm2 web` monitoring endpoint.

---

## Decision 5: Agent Identity and Environment Separation

**Decision**: Agents are identified by `AGENT_ID` environment variable (e.g., `cloud-vm-001`, `local-dev`). Environment is determined by `AGENT_ENV` (`cloud` or `local`). Both are set in the local `.env` file outside the vault.

**Rationale**:
- A single codebase runs on both local and cloud; configuration diverges only through environment variables.
- Agent identity is written into claimed task filenames (`In_Progress/<agent-id>/`) and heartbeat files (`Logs/heartbeats/<agent-id>.json`).
- The `AGENT_ENV=cloud` flag enables cloud-only behaviours (stricter DRY_RUN defaults, different log paths).
- No code forking required — same `main.py`, different `.env`.

**New CLI flag**: `--cloud` mode added to `main.py` which sets defaults appropriate for always-on operation (no interactive prompts, automatic restart on error, stricter vault-path validation).

---

## Decision 6: Secrets Guard Implementation

**Decision**: Git pre-commit hook + `.gitignore` layered defence.

**Layer 1 — `.gitignore`**: Vault-root `.gitignore` blocks `.env`, `*.key`, `*.pem`, `*secret*`, `credentials*`, `token*` from ever being staged.

**Layer 2 — Pre-commit hook**: `vault/.git/hooks/pre-commit` script scans staged files for patterns matching:
- Known secret file names (`.env`, `*.key`, `*.pem`)
- High-entropy strings (base64-like patterns > 40 chars)
- Common credential key names (`API_KEY=`, `SECRET=`, `TOKEN=`, `PASSWORD=`)

If any match is found, the hook exits non-zero and prints the offending file/line. The commit is blocked.

**Alternatives Considered**:
- *`git-secrets` (AWS tool)*: Good but requires external installation; pre-commit hook is self-contained.
- *`detect-secrets` (Yelp)*: Excellent but adds a Python dependency; pre-commit hook is simpler for this scope.
- Both tools can be added later as an enhancement without breaking the hook-based architecture.

---

## Decision 7: Health Monitoring Architecture

**Decision**: Heartbeat files in `Logs/heartbeats/<agent-id>.json`; monitor process reads all heartbeat files every 60 seconds; stale alerts written to `Logs/health-alerts.jsonl`.

**Heartbeat file format**:
```json
{
  "agent_id": "cloud-vm-001",
  "agent_env": "cloud",
  "timestamp": "2026-03-08T14:30:00Z",
  "uptime_seconds": 86400,
  "tasks_completed": 42,
  "last_task": "task-2026-03-08-001.md",
  "status": "idle"
}
```

**Alert file format** (append-only JSONL):
```json
{"timestamp": "...", "type": "agent_down", "agent_id": "cloud-vm-001", "last_seen": "...", "stale_seconds": 360}
{"timestamp": "...", "type": "agent_recovered", "agent_id": "cloud-vm-001"}
```

**Alternatives Considered**:
- *Prometheus + Grafana*: Full observability stack; vastly over-engineered for single-VM deployment. Deferred.
- *External uptime monitor (UptimeRobot, BetterStack)*: Requires a public HTTP endpoint; adds external dependency. Deferred.

---

## Decision 8: HTTPS Setup

**Decision**: Nginx reverse proxy terminating HTTPS (Let's Encrypt TLS) in front of PM2's built-in HTTP metrics endpoint on port 9615.

**Rationale**:
- PM2's `pm2 web` command exposes a JSON status endpoint on port 9615.
- Nginx proxies `https://monitor.yourdomain.com` → `http://127.0.0.1:9615` with basic auth.
- Let's Encrypt (Certbot) provides free, auto-renewing TLS certificates.
- Operators can check agent status from any browser without SSH access.

**Alternatives Considered**:
- *Self-signed certificate*: Browser warnings; poor UX. Rejected.
- *Cloudflare Tunnel*: Excellent zero-config HTTPS but requires Cloudflare account. Deferred as enhancement.
- *No HTTPS (HTTP only)*: Exposes credentials over plain text. Rejected.

---

## Decision 9: Backup Strategy

**Decision**: Three-layer backup: (1) Git history as primary, (2) daily `tar.gz` snapshots to `/backups/vault/`, (3) optional off-VM copy via `rclone` to cloud storage.

**Layer 1 — Git history**: Every task, output, and state change is a Git commit. Rollback = `git checkout <hash>`. Retention: Git history is unlimited.

**Layer 2 — Daily snapshots**: A PM2-managed `backup.py` script runs nightly at 02:00 UTC. Creates `vault-YYYY-MM-DD.tar.gz` in `/backups/vault/`. Retains last 30 days. Excludes `.git/` and `.venv/`.

**Layer 3 — Off-VM backup**: `rclone sync /backups/vault/ remote:ai-employee-backups/` — optional, configured via `RCLONE_REMOTE` env var. Supports S3, GCS, Backblaze B2, etc.

---

## Summary Table

| Decision | Choice | Constitution Gate |
|----------|--------|-------------------|
| Claim atomicity | `os.rename()` (POSIX atomic) | IV. File-Based State ✅ |
| Dashboard lock | `fcntl.flock` + stale timeout | IV. File-Based State ✅ |
| Git sync | `pull --rebase` + push on schedule | II. Privacy First (secrets guard) ✅ |
| Process manager | PM2 with Python interpreter | VII. Graceful Failure (auto-restart) ✅ |
| Agent identity | `AGENT_ID` + `AGENT_ENV` env vars | II. Privacy First (secrets in .env) ✅ |
| Secrets guard | git hook + .gitignore | II. Privacy First ✅ |
| Health monitor | Heartbeat files + alert log | VI. Audit Logging ✅ |
| HTTPS | Nginx + Let's Encrypt | I. Human Sovereignty (secure access) ✅ |
| Backup | Git + daily tar.gz + rclone | VII. Graceful Failure ✅ |
