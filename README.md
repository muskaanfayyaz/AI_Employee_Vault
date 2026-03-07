# AI Employee System

A local-first autonomous Digital FTE (Full-Time Equivalent) built on Claude, Python, and an Obsidian vault as a state machine. The system perceives events, reasons about them, plans actions, executes steps, and keeps humans in control of every sensitive decision — all from markdown files on your filesystem.

Delivered in four tiers: **Bronze → Silver → Gold → Platinum**, each independently functional and production-ready before the next begins.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [The Vault State Machine](#the-vault-state-machine)
- [Bronze Tier — The Foundation](#bronze-tier--the-foundation)
- [Silver Tier — Communication & Scheduling](#silver-tier--communication--scheduling)
- [Gold Tier — Full Business Integration](#gold-tier--full-business-integration)
- [Platinum Tier — Always-On Cloud](#platinum-tier--always-on-cloud)
- [Core Engine](#core-engine)
- [Security Model](#security-model)
- [Installation & Setup](#installation--setup)
- [CLI Commands](#cli-commands)
- [Configuration Reference](#configuration-reference)
- [Project Structure](#project-structure)

---

## Architecture Overview

```
External Events (Email / Odoo / Filesystem / Social)
         │
         ▼
  ┌─────────────┐
  │   Watchers   │  ← filesystem, Gmail, WhatsApp, Odoo, LinkedIn
  └──────┬──────┘
         │  create .md items
         ▼
  ┌─────────────┐
  │    Vault     │  ← Obsidian folder = state machine
  │  (folders)   │
  └──────┬──────┘
         │  read → reason → plan → execute
         ▼
  ┌─────────────┐
  │    Skills    │  ← Triage, Planner, Executor, EmailDrafter,
  │   (AI core)  │     SocialPoster, CeoBriefing, RalphWiggum, ...
  └──────┬──────┘
         │  outbound actions via
         ▼
  ┌─────────────┐
  │ MCP Servers  │  ← EmailMCPServer, SocialMCPServer
  └──────┬──────┘
         │  confirmed send
         ▼
  ┌─────────────┐
  │  Audit Log   │  ← Logs/YYYY-MM-DD.json (append-only)
  └─────────────┘
```

Every item flows through the vault as a markdown file with YAML front-matter. The folder it lives in **is** its status. Moving a file **is** the state transition.

---

## The Vault State Machine

```
Inbox/              ← raw drops land here
   │
   ▼ (triage)
Needs_Action/       ← triaged, awaiting AI processing
   │
   ▼ (planner)
Plans/              ← Plan.md created for each item
   │
   ▼ (executor)
In_Progress/        ← currently executing plan steps
   │          │
   │          ▼ (step requires approval)
   │      Pending_Approval/   ← human reviews draft
   │          │          │
   │          ▼ approved  ▼ rejected
   │       Approved/   Rejected/
   │          │
   │          ▼ (execution resumes)
   ▼ (all steps done)
Done/               ← archived, audit logged

Errors/             ← retries exhausted, full diagnostics
Reports/            ← CEO Briefings, Audit Reports
Logs/               ← daily JSON audit trail
Config/             ← watcher + MCP configuration
```

### Item Schema (every vault file)

```yaml
---
id: <uuid>
type: email | message | social | erp | audit | file
source: <watcher-name>
priority: low | medium | high | urgent
status: needs_action | in_progress | pending_approval | done | ...
requires_approval: true | false
classification: local_only | syncable | redacted_summary
created_at: <ISO-8601>
updated_at: <ISO-8601>
tags: [...]
---

# Item Title

Body content...
```

---

## Bronze Tier — The Foundation

**Achievement**: Fully autonomous local file processor — perceive, reason, act, log with zero external dependencies.

### What It Delivers

| Component | Function |
|-----------|----------|
| **Filesystem Watcher** | Monitors `drop_folder/` for new files, detects within 30 seconds, moves to `Needs_Action/` |
| **Triage Skill** | Classifies item type (email/social/erp/audit/file), detects priority from content keywords, flags approval requirements |
| **Planner Skill** | Reads every `Needs_Action/` item and writes a `Plans/PLAN_<item>.md` with sequenced, executable steps |
| **Executor Skill** | Works through plan steps in order, moves item to `In_Progress/`, pauses at approval gates |
| **Dashboard Skill** | Regenerates `Dashboard.md` after every cycle with live counts per folder, errors, and last-updated timestamp |
| **State Machine** | Atomic file moves between folders; every transition logged before the move executes |
| **Audit Logger** | Append-only daily JSON log at `Logs/YYYY-MM-DD.json` — every action, actor, outcome, and timestamp |
| **DRY_RUN Mode** | Global `DRY_RUN=true` flag — all reasoning and planning runs normally, no files move, no external calls made |

### How It Works — Step by Step

1. User drops a `.md` file into `drop_folder/`
2. `FilesystemWatcher` detects it within 30 seconds (watchdog + stability check — waits 2s for write to complete)
3. File is copied to `Needs_Action/` with YAML front-matter added
4. Processing cycle runs every 30 seconds:
   - **TriageSkill** reads item, classifies type + priority, updates front-matter
   - **PlannerSkill** writes `Plans/PLAN_<name>.md` with step list
   - **ExecutorSkill** reads plan, moves item to `In_Progress/`, executes steps one by one
5. On completion → item moves to `Done/`
6. **DashboardSkill** regenerates `Dashboard.md`
7. Audit entry written to `Logs/YYYY-MM-DD.json`

### Key Files

```
src/watchers/filesystem.py   — watchdog-based folder monitor
src/skills/triage.py         — type/priority classification
src/skills/planner.py        — Plan.md generation
src/skills/executor.py       — plan step execution engine
src/skills/dashboard.py      — Dashboard.md regeneration
src/engine/state_machine.py  — atomic file move + validation
src/engine/logger.py         — append-only JSON audit log
src/models/task_item.py      — TaskItem model (parse/write .md + YAML)
src/models/plan.py           — Plan model (parse/write Plan.md)
```

### Bronze Commands

```bash
# Initialize vault folders
python -m src.main --init

# Start Bronze watcher loop (DRY_RUN by default)
python -m src.main

# Run one processing cycle and exit
python -m src.main --process

# Force DRY_RUN regardless of .env
python -m src.main --dry-run
```

---

## Silver Tier — Communication & Scheduling

**Achievement**: The system monitors Gmail, drafts email replies, and submits them for human approval before sending. Everything runs on a schedule — no manual triggers needed.

### What It Adds

| Component | Function |
|-----------|----------|
| **Gmail Watcher** | Polls Gmail inbox every 60s (configurable), detects emails matching keyword/sender/label filters, creates vault items |
| **WhatsApp Watcher** | Monitors configured contacts/groups for new messages, creates action items |
| **LinkedIn Watcher** | Polls LinkedIn for notifications/mentions requiring response |
| **Email MCP Server** | Sends approved email drafts via OAuth-authenticated Gmail API; structured retry + health check |
| **Email Drafter Skill** | Uses Gemini Flash to draft contextual email replies from original email content + business context |
| **Approval Manager** | Detects human decisions (edit `decision: approved` in file, or drag to `Approved/`), routes accordingly |
| **Scheduler** | `schedule`-based cron loop: processing cycle every 30s, approval cycle every 15s |
| **Exponential Backoff** | All external calls retry 3× with 2s → 4s → 8s delays; failed items move to `Errors/` |

### Human-in-the-Loop Approval Workflow

```
Email arrives in Gmail
      │
      ▼
GmailWatcher creates Needs_Action/email-<id>.md
      │
      ▼
TriageSkill + PlannerSkill + ExecutorSkill
      │
      ▼ (EmailDrafterSkill invoked)
Gemini drafts reply → Pending_Approval/draft-email-<id>.md
      │
      ▼  (human edits decision: approved)
ApprovalManager detects → moves to Approved/
      │
      ▼  (approval cycle, every 15s)
EmailMCPServer.send_email() → Gmail API
      │
      ▼
Draft moved to Done/  +  audit logged
```

**What always requires approval**: sending email, posting to social media, any write to external systems, financial actions, deleting data.

**What is auto-approved**: reading files, creating plans, generating reports, writing logs, updating dashboard.

### Approval Decision Patterns

Two ways to approve/reject:

**Pattern A — in-place edit** (edit the file in Obsidian):
```yaml
approval:
  decision: approved    # change from "pending" to "approved" or "rejected"
  feedback: "Looks good"
```

**Pattern B — manual move**: drag the file directly from `Pending_Approval/` to `Approved/` or `Rejected/` in your file manager. The system detects it automatically.

### Key Files

```
src/watchers/gmail.py          — Gmail polling + item creation
src/watchers/whatsapp.py       — WhatsApp monitoring
src/watchers/linkedin.py       — LinkedIn notifications
src/skills/email_drafter.py    — Gemini-powered email reply drafting
src/mcp/email_server.py        — EmailMCPServer (Gmail OAuth send)
src/approval/manager.py        — ApprovalManager (detect + route decisions)
src/engine/scheduler.py        — cron-based job scheduler
src/engine/retry.py            — exponential backoff decorator
src/scripts/gmail_auth.py      — OAuth2 token generation helper
```

### Silver Commands

```bash
# Start full Silver scheduler (Gmail + approval loop)
python -m src.main --schedule

# Gmail OAuth setup (run once)
python src/scripts/gmail_auth.py
```

### Silver Configuration

`Config/gmail_watcher.yaml`:
```yaml
watcher:
  name: "gmail-inbox"
  type: "gmail"
  enabled: true
  polling_interval_seconds: 60
  filters:
    keywords: ["urgent", "invoice", "action required"]
    senders: []
    labels: ["IMPORTANT"]
  credential_ref: "GMAIL_OAUTH_TOKEN_PATH"
```

---

## Gold Tier — Full Business Integration

**Achievement**: The system integrates with Odoo ERP, manages multi-platform social media with approval gates, generates weekly CEO Briefings, audits accounting entries, and runs the Ralph Wiggum self-improvement loop.

### What It Adds

| Component | Function |
|-----------|----------|
| **Odoo Watcher** | Polls Odoo via JSON-RPC every 5 minutes for new/updated project tasks, sales orders, invoices; deduplicates by record ID |
| **Social Poster Skill** | Drafts platform-appropriate posts for LinkedIn, Facebook, Instagram, and Twitter/X using Gemini Flash; credential-leak scan before every draft |
| **Social MCP Server** | Publishes approved social drafts to LinkedIn (UGC Posts API), Facebook (Graph API), Instagram (two-step media + publish), Twitter/X (tweepy OAuth 1.0a) |
| **CEO Briefing Skill** | Generates `Reports/CEO_Briefing_YYYY-MM-DD.md` from audit logs, Done/ folder, pipeline state, Odoo events, social activity, and Ralph Wiggum insights |
| **Subscription Audit Skill** | Reads Odoo subscriptions, detects anomalies (duplicates, unusual amounts, missing refs), writes `Reports/Subscription_Audit_*.md` |
| **Ralph Wiggum Loop** | Reviews past audit logs, identifies failure patterns (retries, rejections, slow items), proposes corrections as `[RALPH_WIGGUM]`-tagged Needs_Action items |
| **Multi-MCP Orchestration** | Sequences calls across Email + Odoo + Social MCP servers; handles partial failures gracefully |

### Social Media Workflow

```
User creates linkedin-post.md with type: social
      │
      ▼
Drop into Needs_Action/ (or system detects it)
      │
      ▼
TriageSkill + PlannerSkill
      │
      ▼
ExecutorSkill → SocialPosterSkill
      │  ├── Scans for credential leaks (FR-G044)
      │  ├── Calls Gemini Flash to draft platform-specific post
      │  └── Enforces character limits per platform
      ▼
Pending_Approval/draft-linkedin-post-<id>.md
      │
      ▼  (human sets decision: approved)
Approved/draft-linkedin-post-<id>.md
      │
      ▼  (approval cycle every 15s)
SocialMCPServer.post_to_linkedin()
      │  ├── Fetches person URN from /v2/userinfo
      │  ├── Optionally uploads image via Assets API
      │  └── POSTs to /v2/ugcPosts with retry
      ▼
Done/draft-linkedin-post-<id>.md  +  audit logged
```

### Platform Constraints (enforced automatically)

| Platform | Max Chars | Max Hashtags | Tone |
|----------|-----------|--------------|------|
| LinkedIn | 3,000 | 5 | Professional, 1–3 paragraphs |
| Facebook | 63,206 | 5 | Conversational, engagement-focused |
| Instagram | 2,200 | 30 | Visual, hook + hashtag block |
| Twitter/X | 280 | 3 | Concise, punchy |

### CEO Briefing Skill

Generates a 10-section executive report every Monday at 8:00 AM (configurable):

1. **Period Summary** — review window, total actions, success rate
2. **Tasks Completed** — Done/ items with summaries
3. **Current Pipeline & Bottlenecks** — items per folder, stale approvals
4. **Errors & Failures** — unresolved Errors/ items with diagnostics
5. **Approval Summary** — approved vs rejected ratio, average decision time
6. **Revenue & Financial Activity** — Odoo invoice/sales data
7. **Social Media Activity** — posts published per platform from audit logs
8. **Subscription Health** — Odoo subscription anomalies
9. **Ralph Wiggum Insights** — AI self-review findings from review period
10. **Proactive Suggestions** — Gemini-generated recommendations based on patterns

```bash
# Generate CEO Briefing now
python -m src.main --briefing
```

### Ralph Wiggum Self-Improvement Loop

The system reviews its own past performance and proposes fixes:

```
Weekly trigger (or manual --ralph)
      │
      ▼
Reads Logs/YYYY-MM-DD.json (last 7 days)
      │
      ▼
Gemini Flash analyzes:
  - Failure patterns (recurring errors)
  - High-retry operations (slow external calls)
  - Frequently rejected drafts
  - Processing bottlenecks
      │
      ▼
Creates Needs_Action/ralph-review-<date>.md
with [RALPH_WIGGUM] tag and specific correction proposals
      │
      ▼
Proposals require human approval before any change is made
```

```bash
# Run Ralph Wiggum loop now
python -m src.main --ralph

# Run subscription audit now
python -m src.main --subscription-audit
```

### Odoo Watcher

Polls three record types:
- **Project Tasks** — new/updated tasks become action items
- **Sales Orders** — new orders trigger follow-up workflow
- **Invoices** — unpaid/overdue invoices flagged for action

Deduplication: tracks processed record IDs in `Config/odoo_last_poll.json` — same record never creates two items.

### Key Files

```
src/watchers/odoo.py              — Odoo JSON-RPC polling + dedup
src/skills/social_poster.py       — multi-platform draft generation
src/mcp/social_server.py          — SocialMCPServer (LinkedIn/FB/IG/Twitter)
src/skills/ceo_briefing.py        — 10-section executive briefing
src/skills/subscription_audit.py  — Odoo subscription anomaly detection
src/engine/ralph_wiggum_loop.py   — self-review + improvement proposals
src/engine/integration_registry.py — MCP server registry + health tracking
```

### Gold Configuration

`Config/odoo_watcher.yaml`:
```yaml
watcher:
  name: "odoo-erp"
  type: "odoo"
  enabled: true
  polling_interval_seconds: 300
  url_ref: "ODOO_URL"
  db_ref: "ODOO_DB"
  username_ref: "ODOO_USERNAME"
  api_key_ref: "ODOO_API_KEY"
  record_types: ["project.task", "sale.order", "account.move"]
```

`Config/linkedin_watcher.yaml` (and similar for facebook, instagram, twitter):
```yaml
social:
  platform: "linkedin"
  enabled: true
  credential_refs:
    access_token: "LINKEDIN_ACCESS_TOKEN"
```

---

## Platinum Tier — Always-On Cloud

**Achievement**: 24/7 cloud deployment with bidirectional vault sync, cloud/local role separation, data classification boundaries, zero-downtime deployments, and production-grade health monitoring.

> **Status**: Designed and specified. Implementation follows Gold tier completion.

### Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│   CLOUD INSTANCE    │◄──────►│   LOCAL INSTANCE    │
│  (runs 24/7)        │  sync   │  (executive seat)   │
│                     │  <5min  │                     │
│  - Watchers         │         │  - Approval UI      │
│  - Processors       │         │  - Sensitive data   │
│  - Auto-approved    │         │  - Final decisions  │
│    actions          │         │  - .env files       │
│  - Queue approvals  │         │                     │
└─────────────────────┘         └─────────────────────┘
       ↕ encrypted, mutual auth
```

### Data Classification

Every vault item carries a `classification` tag:

| Tag | Meaning | Cloud behaviour |
|-----|---------|-----------------|
| `local_only` | Sensitive — never leaves local machine | Cloud receives redacted summary only |
| `syncable` | Safe for cloud | Synced in full |
| `redacted_summary` | Cloud gets context, not values | Masked financial/PII fields |

**Default**: `local_only` (fail-safe — untagged items never leak to cloud).

Classified as `local_only` by default: credentials, financial account details, personal identifiers, health records.

### Key Platinum Features

- **Bidirectional vault sync** — changes propagate within 5 minutes of either instance coming online
- **Conflict detection** — dual-modified items flagged for human resolution, never auto-overwritten
- **Health monitor** — checks all components every 60s; attempts auto-recovery (3×) before alerting
- **Zero-downtime deployments** — blue/green swap, no items lost during update
- **Encrypted transport** — cloud↔local communication encrypted + mutual auth
- **Cloud health reports** — generated hourly: uptime %, sync rate, items processed, component statuses

---

## Core Engine

### Retry System (`src/engine/retry.py`)

All external API calls use the `@with_retry` decorator:

```python
@with_retry(base_delay=2, max_retries=3)
def post_to_linkedin(self, content: str) -> dict:
    ...
```

Retry schedule: **2s → 4s → 8s → RetriesExhaustedError**

- **Retryable**: 408, 429, 500, 502, 503, 504
- **Non-retryable**: 400, 401, 403, 404, 405, 409, 422 (fail immediately)
- **Retry-After header**: honoured when server sends it (rate limiting)
- **Max delay cap**: 30s (prevents runaway waits)
- After exhaustion: item moves to `Errors/` with full diagnostic context

### State Machine (`src/engine/state_machine.py`)

Enforces valid transitions only. Invalid moves are rejected and logged.

Valid transitions:

| From | To | Trigger |
|------|----|---------|
| Inbox | Needs_Action | Triage completes |
| Needs_Action | In_Progress | Execution begins |
| In_Progress | Pending_Approval | Step requires approval |
| In_Progress | Done | All steps complete |
| In_Progress | Errors | Retries exhausted |
| Pending_Approval | Approved | Human approves |
| Pending_Approval | Rejected | Human rejects |
| Approved | Done | Post/email confirmed sent |

### Audit Logger (`src/engine/logger.py`)

Every action produces a structured log entry in `Logs/YYYY-MM-DD.json`:

```json
{
  "timestamp": "2026-03-07T13:00:00+00:00",
  "actor": "social_poster_linkedin",
  "action": "linkedin_post_published",
  "item_id": "c09f29ba-...",
  "from_state": "Approved",
  "to_state": "Done",
  "outcome": "success",
  "details": {"post_id": "urn:li:share:...", "content_preview": "..."},
  "approval": {"required": true, "status": "approved", "approver": "human"},
  "dry_run": false
}
```

Logs are append-only. Retroactive modification is prohibited. Retained 90+ days.

### MCP Base Server (`src/mcp/base.py`)

All MCP servers extend `BaseMCPServer`:
- Credential reference validation at construction (env var names only, never values)
- `health_check()` — verifies all required env vars are set
- `ping()` — liveness endpoint
- All tools inherit `@with_retry` exponential backoff

---

## Security Model

| Rule | Implementation |
|------|---------------|
| Credentials never in vault files | All secrets stored in `.env` only; config files use env var names as references |
| Credential-leak detection | Every social post draft scanned for API key patterns, Bearer tokens, base64 blobs, GitHub PATs before writing |
| No secrets in logs | Log entries contain `content_preview` (first 120 chars) and post IDs, never raw tokens |
| DRY_RUN default | `DRY_RUN=true` out of the box; switching to live requires explicit `.env` edit |
| Approval gates | Sending email, social posts, Odoo writes — always require human approval |
| Stale approval protection | Items pending >24h flagged in Dashboard; never auto-approved |
| Classification fail-safe | Untagged items default to `local_only` — nothing leaks to cloud silently |

---

## Installation & Setup

### Prerequisites

- Python 3.12+
- Git
- A `.env` file (see below)

### 1. Install

```bash
git clone <repo>
cd AI_Employee_Vault
pip install -e ".[dev]"
```

### 2. Configure `.env`

```bash
cp .env.example .env
```

Minimum for Bronze:
```env
VAULT_ROOT=/path/to/AI_Employee_Vault
DRY_RUN=true
```

Add for Silver:
```env
GMAIL_OAUTH_TOKEN_PATH=/path/to/gmail_token.json
GEMINI_API_KEY=your-gemini-api-key
```

Add for Gold:
```env
ODOO_URL=https://your-odoo.com
ODOO_DB=your-db
ODOO_USERNAME=your-user
ODOO_API_KEY=your-key

LINKEDIN_ACCESS_TOKEN=your-token
FACEBOOK_ACCESS_TOKEN=your-token
FACEBOOK_PAGE_ID=your-page-id
INSTAGRAM_ACCESS_TOKEN=your-token
INSTAGRAM_ACCOUNT_ID=your-account-id
TWITTER_API_KEY=your-key
TWITTER_API_KEY_SECRET=your-secret
TWITTER_ACCESS_TOKEN=your-token
TWITTER_ACCESS_TOKEN_SECRET=your-secret
```

### 3. Initialize vault

```bash
python -m src.main --init
```

Creates all 13 vault folders + `Dashboard.md`.

### 4. Gmail OAuth (Silver only)

```bash
python src/scripts/gmail_auth.py
# Follow the browser OAuth flow — saves token to path configured above
```

---

## CLI Commands

```bash
# Initialize vault folders and Dashboard.md
python -m src.main --init

# Bronze: start filesystem watcher + processing loop (default)
python -m src.main

# Bronze: run one processing cycle over Needs_Action/ and exit
python -m src.main --process

# Silver: start full scheduler (Gmail + WhatsApp + approval loop + cron)
python -m src.main --schedule

# Force DRY_RUN mode regardless of .env setting
python -m src.main --dry-run

# Gold: generate CEO Briefing now and exit
python -m src.main --briefing

# Gold: run Ralph Wiggum self-improvement loop now and exit
python -m src.main --ralph

# Gold: run subscription audit now and exit
python -m src.main --subscription-audit
```

---

## Configuration Reference

### Watcher Configs (`Config/`)

| File | Controls |
|------|----------|
| `gmail_watcher.yaml` | Gmail polling interval, keyword filters, sender filters, label filters |
| `odoo_watcher.yaml` | Odoo URL/DB refs, polling interval, which record types to watch |
| `linkedin_watcher.yaml` | LinkedIn credential ref, enabled flag |
| `facebook_watcher.yaml` | Facebook token + page ID refs, enabled flag |
| `instagram_watcher.yaml` | Instagram token + account ID refs, enabled flag |
| `ceo_briefing.yaml` | Schedule (day/hour/minute), review period (days), enabled flag |
| `ralph_wiggum.yaml` | Schedule (day/hour/minute), max_iterations, stop_when_done flag |
| `subscription_audit.yaml` | Schedule, anomaly thresholds, enabled flag |

### Scheduler Defaults

| Job | Interval |
|-----|----------|
| Processing cycle | Every 30 seconds |
| Approval cycle | Every 15 seconds |
| CEO Briefing | Weekly, Monday 08:00 (configurable) |
| Ralph Wiggum | Weekly, Monday 07:00 (configurable) |
| Subscription Audit | Weekly, Friday 06:00 (configurable) |

---

## Project Structure

```
AI_Employee_Vault/
├── src/
│   ├── main.py                    # Entry point, all CLI commands
│   ├── config.py                  # Vault root + DRY_RUN resolution
│   ├── models/
│   │   ├── task_item.py           # TaskItem — parse/write vault .md files
│   │   ├── plan.py                # Plan — parse/write Plan.md files
│   │   ├── approval.py            # ApprovalRequest model
│   │   └── log_entry.py           # LogEntry + ApprovalInfo models
│   ├── watchers/
│   │   ├── base.py                # BaseWatcher interface
│   │   ├── filesystem.py          # Drop-folder monitor (watchdog)
│   │   ├── gmail.py               # Gmail polling watcher
│   │   ├── whatsapp.py            # WhatsApp monitoring
│   │   ├── linkedin.py            # LinkedIn notifications
│   │   └── odoo.py                # Odoo JSON-RPC polling + dedup
│   ├── skills/
│   │   ├── base.py                # BaseSkill, SkillInput, SkillOutput
│   │   ├── triage.py              # Classify type, priority, approval needs
│   │   ├── planner.py             # Generate Plan.md with sequenced steps
│   │   ├── executor.py            # Execute plan steps, pause at gates
│   │   ├── dashboard.py           # Regenerate Dashboard.md
│   │   ├── email_drafter.py       # Gemini-powered email reply drafts
│   │   ├── social_poster.py       # Multi-platform social post drafting
│   │   ├── ceo_briefing.py        # 10-section weekly executive briefing
│   │   ├── subscription_audit.py  # Odoo subscription anomaly detection
│   │   └── linkedin_poster.py     # LinkedIn-specific posting helper
│   ├── mcp/
│   │   ├── base.py                # BaseMCPServer (credentials, health, retry)
│   │   ├── email_server.py        # EmailMCPServer — Gmail OAuth send
│   │   └── social_server.py       # SocialMCPServer — LinkedIn/FB/IG/Twitter
│   ├── approval/
│   │   └── manager.py             # ApprovalManager — detect + route decisions
│   ├── engine/
│   │   ├── state_machine.py       # Atomic folder moves + transition validation
│   │   ├── logger.py              # Append-only JSON audit log
│   │   ├── retry.py               # @with_retry exponential backoff decorator
│   │   ├── scheduler.py           # Cron-based job scheduler
│   │   ├── ralph_wiggum_loop.py   # Self-review + improvement proposals
│   │   └── integration_registry.py # MCP server registry + health tracking
│   └── scripts/
│       ├── gmail_auth.py          # Gmail OAuth2 token setup
│       └── linkedin_auth.py       # LinkedIn OAuth token setup
├── tests/
│   └── unit/                      # Unit tests per skill/watcher/engine
├── specs/001-ai-employee-system/
│   ├── spec.md                    # Full feature specification
│   ├── plan.md                    # Architecture decisions
│   ├── tasks.md                   # Task breakdown
│   └── quickstart.md              # Quickstart guide
├── Config/                        # Watcher + scheduler YAML configs
├── Inbox/                         # Drop files here to trigger processing
├── Needs_Action/                  # Triaged items awaiting processing
├── Plans/                         # PLAN_<item>.md files
├── In_Progress/                   # Items currently executing
├── Pending_Approval/              # Drafts awaiting human decision
├── Approved/                      # Approved, awaiting MCP publish
├── Rejected/                      # Rejected items
├── Done/                          # Completed items
├── Errors/                        # Failed items with diagnostics
├── Reports/                       # CEO Briefings + audit reports
├── Logs/                          # Daily JSON audit trail
├── Dashboard.md                   # Live system status
├── .env.example                   # Environment variable template
└── README.md                      # This file
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| AI / Drafting | Google Gemini Flash (via REST API) |
| Filesystem events | watchdog |
| Scheduling | schedule |
| Email | Gmail API (OAuth 2.0) via `google-auth` |
| Social media | LinkedIn UGC Posts API, Facebook Graph API v18, Instagram Graph API, Twitter API v2 (tweepy) |
| ERP | Odoo JSON-RPC |
| Config | YAML (`pyyaml`) + `.env` (`python-dotenv`) |
| Vault format | Markdown + YAML front-matter (Obsidian-compatible) |
| Tests | pytest |

---

## Tier Completion Summary

| Tier | Status | Key Achievement |
|------|--------|-----------------|
| **Bronze** | ✅ Complete | Local file processor — perceive, reason, plan, execute, log |
| **Silver** | ✅ Complete | Gmail integration, human-in-the-loop approval, cron scheduling |
| **Gold** | ✅ Complete | Odoo ERP, multi-platform social media, CEO Briefing, Ralph Wiggum |
| **Platinum** | 🔜 Next | 24/7 cloud deployment, bidirectional sync, zero-downtime production |
