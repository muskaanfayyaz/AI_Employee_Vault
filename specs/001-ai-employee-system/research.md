# Research: AI Employee System

**Phase**: 0 — Outline & Research
**Date**: 2026-02-17
**Branch**: `001-ai-employee-system`

## Decision 1: Filesystem Watcher Library

**Decision**: Use `watchdog` (Python)

**Rationale**: Mature, cross-platform (Linux inotify, macOS FSEvents,
Windows ReadDirectoryChanges), well-documented, pip-installable.
Supports file creation, modification, and deletion events with
configurable debounce.

**Alternatives considered**:
- `inotify` (Linux-only, not cross-platform)
- `pyinotify` (deprecated, Linux-only)
- polling with `os.listdir()` (simple but high latency, resource waste)

---

## Decision 2: YAML Front-Matter Format

**Decision**: Use `pyyaml` for parsing YAML front-matter in markdown
files, delimited by `---` markers.

**Rationale**: Standard markdown convention (used by Jekyll, Hugo,
Obsidian). Human-readable, easy to parse, supports all required
metadata fields. Obsidian natively renders front-matter.

**Alternatives considered**:
- JSON header blocks (less readable in markdown editors)
- TOML front-matter (less common, Obsidian doesn't render natively)
- Inline metadata in markdown body (fragile to parse)

---

## Decision 3: Audit Log Format

**Decision**: JSON Lines (one JSON object per line) within a JSON
array wrapper in `/Logs/YYYY-MM-DD.json`.

**Rationale**: Append-friendly (add to array), machine-parseable,
human-inspectable with `jq`. Schema defined in FR-038. One file
per day keeps individual files manageable.

**Alternatives considered**:
- Plain text logs (not structured, hard to query)
- SQLite (violates Principle IV — no external database)
- CSV (poor support for nested objects like approval status)

---

## Decision 4: Scheduling Library

**Decision**: Use `schedule` (Python) for Silver-tier cron-like
scheduling.

**Rationale**: Lightweight, no daemon required, human-readable API
(`schedule.every(60).seconds.do(poll)`). Runs in-process alongside
watchers. No external cron dependency.

**Alternatives considered**:
- System crontab (requires OS-level config, not portable)
- APScheduler (heavier, more features than needed)
- `asyncio` loop with sleep (manual, harder to configure)

---

## Decision 5: MCP Server Implementation

**Decision**: Implement MCP servers as Python processes using the
MCP protocol SDK, communicating via stdio transport.

**Rationale**: Claude Code natively supports MCP via stdio. Each
server is an independent process that can be started/stopped
independently. Health checks via a `ping` tool.

**Alternatives considered**:
- HTTP-based API servers (more overhead, not native MCP)
- In-process function calls (no MCP protocol, loses tool isolation)
- WebSocket transport (more complex, not needed for local comms)

---

## Decision 6: Gmail Integration

**Decision**: Use Google Gmail API via `google-api-python-client`
with OAuth2 credentials stored as `.env` references.

**Rationale**: Official API, well-documented, supports search,
read, send, label management. OAuth2 tokens stored in local file
referenced by .env variable (never in vault markdown).

**Alternatives considered**:
- IMAP polling (limited, no label support, less reliable)
- Google Apps Script (external, not local-first)

---

## Decision 7: WhatsApp Integration

**Decision**: Use WhatsApp Business API (Cloud API) for Silver tier.

**Rationale**: Official Meta API, supports send/receive messages,
webhook notifications. Requires Business account but provides
stable, documented endpoints.

**Alternatives considered**:
- `whatsapp-web.js` (unofficial, browser automation, fragile)
- Twilio WhatsApp API (third-party, adds cost and dependency)

**Note**: If Business API is not available, fall back to
`whatsapp-web.js` bridge as a development-mode alternative.

---

## Decision 8: Odoo Integration

**Decision**: Use Odoo JSON-RPC API via Python `xmlrpc.client`
(stdlib) wrapped in a custom MCP server.

**Rationale**: Odoo's external API is JSON-RPC over HTTP. Python's
`xmlrpc.client` supports this natively (no extra dependencies).
MCP wrapping provides tool isolation and health checking.

**Alternatives considered**:
- OdooRPC library (additional dependency, thin wrapper)
- REST API (requires Odoo REST module, not always installed)
- Direct database access (violates Principle IV, security risk)

---

## Decision 9: Social Media Integration

**Decision**: Use official platform APIs via per-platform adapter
modules within a single Social Media MCP server.

**Rationale**: Each platform has a different API. Adapter pattern
keeps the MCP interface uniform (`draft_post`, `publish_post`,
`get_mentions`) while handling platform-specific auth and formatting.

**Platforms and libraries**:
- LinkedIn: `linkedin-api` or official Marketing API
- Facebook/Instagram: Meta Graph API via `facebook-sdk`
- Twitter/X: `tweepy` (Twitter API v2)

**Alternatives considered**:
- Buffer/Hootsuite API (third-party, adds cost)
- Separate MCP server per platform (too many processes)

---

## Decision 10: Report Templating

**Decision**: Use `jinja2` for CEO Briefing and Accounting Audit
report generation.

**Rationale**: Standard Python templating, supports markdown output,
conditional sections, loops over data. Templates stored in
`templates/` directory.

**Alternatives considered**:
- String formatting (fragile for complex reports)
- Markdown libraries (don't support templating logic)
- Claude-generated reports (non-deterministic, hard to test)

---

## Decision 11: State Machine Implementation

**Decision**: Custom Python module (`state_machine.py`) that enforces
the transition table from FR-006 using atomic file operations
(`os.rename`).

**Rationale**: The state machine is the core of the system. A custom
implementation ensures exact compliance with the transition table,
file-level locking, and DRY_RUN support. No ORM or framework needed.

**Alternatives considered**:
- `transitions` library (good but overkill — we don't need
  callbacks, state history, or diagrams)
- Database-backed state (violates Principle IV)

---

## Decision 12: Project Packaging

**Decision**: Use `pyproject.toml` with `setuptools` backend.
Single installable package `ai_employee`.

**Rationale**: Modern Python packaging standard. Supports dependency
declaration, entry points, and development extras (pytest, mypy).

**Alternatives considered**:
- `setup.py` (legacy)
- Poetry (heavier, not needed for single package)

---

## Decision 13: Cloud Deployment Target

**Decision**: Use Docker + docker-compose on a Linux VPS
(DigitalOcean, Hetzner, or AWS EC2).

**Rationale**: Same Python environment as local. Docker provides
reproducible builds, easy rollback via image tags, and
docker-compose manages multi-service orchestration (main loop,
MCP servers, sync daemon). VPS is simple, affordable, and avoids
cloud-provider lock-in.

**Alternatives considered**:
- Kubernetes (overkill for single-user system)
- AWS ECS/Fargate (vendor lock-in, more complex)
- Bare metal process manager (no isolation, harder rollback)
- Heroku/Railway (limited control, sleep on inactivity)

---

## Decision 14: Vault Sync Protocol

**Decision**: Custom rsync-over-SSH daemon with conflict detection.
Sync manifest tracks per-item hashes and timestamps.

**Rationale**: rsync is efficient (delta transfers), SSH provides
encryption + authentication (FR-060/062), and it works well with
file-based vault structure. The sync manifest (JSON file) records
last-sync state per item, enabling conflict detection when both
sides modify the same item. Resumable by design (rsync handles
partial transfers).

**Alternatives considered**:
- Syncthing (automatic, but poor conflict control for our needs)
- Git-based sync (merge conflicts in YAML front-matter are painful)
- Custom WebSocket protocol (more engineering, less proven)
- rclone (cloud-storage focused, not peer-to-peer)

---

## Decision 15: Credential Proxy for Cloud

**Decision**: Custom Python proxy process running on the cloud
instance. Receives credential requests via Unix socket (or
localhost-only TCP). Credentials loaded from encrypted `.env.cloud`
at startup, never persisted to disk in plaintext after load.

**Rationale**: Cloud instance must not store raw `.env` files
(FR-061). A proxy isolates credential access — MCP servers request
credentials by reference name, the proxy returns them over a
secure local channel. If the container is compromised, credentials
are only in memory, not on disk.

**Alternatives considered**:
- HashiCorp Vault (heavy for single-user system)
- AWS Secrets Manager (vendor lock-in)
- Docker secrets (limited to swarm mode)
- Encrypted .env with gpg (still on disk, decrypted at runtime)

---

## Decision 16: Health Monitoring

**Decision**: Custom Python health monitor using `psutil` for
process health and HTTP/socket checks for MCP server liveness.

**Rationale**: Lightweight, no external dependency beyond `psutil`.
Polls component health at configurable intervals, writes
structured JSON reports, and uses the existing retry/backoff
infrastructure for auto-recovery attempts.

**Alternatives considered**:
- Prometheus + Grafana (overkill for single-user)
- systemd watchdog (Linux-only, not portable)
- Supervisor (process manager, not health reporting)

---

## Decision 17: Zero-Downtime Deployment Strategy

**Decision**: Blue-green container deployment using docker-compose
with two service profiles.

**Rationale**: Start the new container alongside the old one, verify
health, then switch traffic (stop old container). Items in-flight
are preserved because the vault is a shared Docker volume. No items
lost, no approvals dropped (FR-057).

**Alternatives considered**:
- Rolling update (docker-compose default — brief downtime)
- Kubernetes rolling deployment (overkill)
- Process-level hot reload (fragile with MCP servers)
