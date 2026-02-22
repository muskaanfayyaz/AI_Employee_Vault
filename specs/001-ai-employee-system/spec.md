# Feature Specification: AI Employee System

**Feature Branch**: `001-ai-employee-system`
**Created**: 2026-02-16
**Status**: Draft
**Last Updated**: 2026-02-17
**Input**: User description: "Build a local-first autonomous Digital FTE using Claude Code, Obsidian, Python Watchers, MCP servers, and a Ralph Wiggum loop — delivered in four tiers (Bronze, Silver, Gold, Platinum)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bronze: Local File Processing Loop (Priority: P1)

As a user, I set up an Obsidian vault with a defined folder structure.
A filesystem watcher detects when I drop a file into `/Inbox`. The AI
employee reads items from `/Needs_Action`, reasons about them using
Agent Skills, creates a `Plan.md` for each item, executes the plan,
and moves completed items to `/Done`. A dashboard file reflects the
current state of all items at all times.

This is the minimum viable AI employee: perceive, reason, act, log —
all locally, no external APIs, no credentials required.

**Why this priority**: This proves the entire system architecture
works end-to-end with zero external dependencies. Every subsequent
tier builds on this foundation. If Bronze doesn't work, nothing works.

**Independent Test**: Drop a text file into `/Inbox`, verify the
watcher moves it to `/Needs_Action`, the AI reads it, creates a
`Plan.md`, executes the plan, moves the result to `/Done`, writes an
audit log entry to `/Logs/YYYY-MM-DD.json`, and the dashboard updates
— all without human intervention.

**Acceptance Scenarios**:

1. **Given** an Obsidian vault with the standard folder structure and
   a running filesystem watcher,
   **When** a user drops a new `.md` file into `/Inbox`,
   **Then** the watcher detects the file within 30 seconds, moves it
   to `/Needs_Action`, and writes a detection event to the daily log.

2. **Given** a file in `/Needs_Action`,
   **When** the AI processing cycle runs,
   **Then** the AI reads the file, invokes the appropriate Agent Skill,
   and creates a `Plan.md` in `/Plans` containing: the original
   request, the AI's reasoning, and a sequenced list of steps.

3. **Given** a plan in `/Plans` with all steps completable without
   human approval,
   **When** the AI executes the plan,
   **Then** each step is executed in order, the plan file updates with
   per-step status (pending/in_progress/done/failed), and the
   completed item moves to `/Done`.

4. **Given** any state change in the vault,
   **When** the dashboard is regenerated,
   **Then** `/Dashboard.md` shows accurate counts for every folder,
   a list of recent actions, and a last-updated timestamp.

5. **Given** a system running with `DRY_RUN=true`,
   **When** the AI processes any item,
   **Then** all reasoning and plan creation proceeds normally, but no
   files are moved, no external actions are taken, and all log entries
   are prefixed with `[DRY_RUN]`.

---

### User Story 2 - Silver: Email, Messaging, and Scheduling (Priority: P2)

As a user, I want the AI employee to monitor my Gmail inbox and
WhatsApp messages, triage them by urgency, draft responses, and
submit sensitive replies for my approval before sending. The system
runs on a cron schedule so I don't need to start it manually. An
MCP server handles email send/receive operations. Plan.md files are
auto-created for multi-step tasks.

**Why this priority**: Email and messaging are the highest-volume
communication channels. Adding external watchers, human-in-the-loop
approval, and scheduled orchestration transforms the AI from a local
file processor into a practical digital assistant.

**Independent Test**: Configure the Gmail watcher and WhatsApp watcher,
send a test email and a test WhatsApp message, verify both are
detected and triaged, the AI drafts responses, approval is requested
for the email reply, and upon approval the email is sent via the MCP
server — all logged with full audit trail.

**Acceptance Scenarios**:

1. **Given** a configured Gmail watcher with importance criteria,
   **When** a matching email arrives in the inbox,
   **Then** the watcher creates an action item in `/Needs_Action`
   within the polling interval (default: 60 seconds) containing
   sender, subject, body, and detected priority.

2. **Given** a configured WhatsApp watcher,
   **When** a new message arrives from a monitored contact or group,
   **Then** the watcher creates an action item in `/Needs_Action`
   with the sender, message body, timestamp, and channel identifier.

3. **Given** an email action item in `/Needs_Action`,
   **When** the AI processes it,
   **Then** the AI auto-creates a `Plan.md` with steps: analyze email,
   draft response, route for approval (if needed), send response.

4. **Given** a draft email reply in `/Pending_Approval`,
   **When** the user approves the draft,
   **Then** the system sends the email via the email MCP server, moves
   the item to `/Done`, and logs the approval with approver identity
   and timestamp.

5. **Given** a draft in `/Pending_Approval`,
   **When** the user rejects the draft with feedback,
   **Then** the item moves to `/Rejected` with feedback attached, and
   NO outbound message is sent.

6. **Given** a cron-scheduled orchestrator,
   **When** the scheduled interval elapses,
   **Then** all configured watchers poll their sources, all items in
   `/Needs_Action` are processed, and the dashboard regenerates.

7. **Given** an email send operation fails,
   **When** the error is detected,
   **Then** the system retries up to 3 times with exponential backoff
   (2s, 4s, 8s), and if all retries fail, the item moves to
   `/Errors` with diagnostic details.

---

### User Story 3 - Gold: Business Integration and Autonomous Loop (Priority: P3)

As a user running a business, I want the AI employee to integrate with
my Odoo ERP via a JSON-RPC MCP server, manage my social media presence
across LinkedIn, Facebook, Instagram, and Twitter, generate a weekly
CEO Briefing summarizing all activity, audit my accounting entries,
and run a "Ralph Wiggum loop" — an autonomous improvement cycle where
the AI reviews its own past performance, identifies failures, and
proposes corrections. Multiple MCP servers are orchestrated together
with comprehensive error handling and retry logic.

**Why this priority**: This is the full Digital FTE vision. Business
system integration, multi-channel social media, executive reporting,
and self-improving autonomy represent the gold standard of an AI
employee that replaces routine human work across all domains.

**Independent Test**: Configure the Odoo MCP server and at least one
social media integration. Submit a sales order in Odoo, verify the AI
detects it, creates appropriate follow-up tasks, drafts a social media
post, queues it for approval, and includes the activity in the weekly
CEO Briefing. Trigger the Ralph Wiggum loop and verify it reviews past
logs, identifies at least one improvement, and proposes a correction.

**Acceptance Scenarios**:

1. **Given** a configured Odoo JSON-RPC MCP server,
   **When** a new sales order, invoice, or contact is created in Odoo,
   **Then** the watcher detects the event, creates an action item in
   `/Needs_Action` with the record type, ID, and summary.

2. **Given** a configured social media integration for any supported
   platform (LinkedIn, Facebook, Instagram, Twitter),
   **When** the AI determines a social media action is needed,
   **Then** the AI drafts a platform-appropriate post and routes it
   to `/Pending_Approval` — posts are NEVER sent without approval.

3. **Given** a running system with at least 7 days of audit logs,
   **When** the weekly CEO Briefing generation triggers (configurable
   day/time, default: Monday 8:00 AM),
   **Then** the system generates a structured briefing in
   `/Reports/CEO_Briefing_YYYY-MM-DD.md` containing: tasks completed,
   tasks pending, errors encountered, approval summary, financial
   activity summary, and social media activity summary.

4. **Given** Odoo accounting entries for the current period,
   **When** the accounting audit skill runs,
   **Then** the system reviews entries for anomalies (duplicate
   entries, unusual amounts, missing references), generates an audit
   report in `/Reports/Accounting_Audit_YYYY-MM-DD.md`, and flags
   items requiring human review.

5. **Given** at least 7 days of audit logs in `/Logs`,
   **When** the Ralph Wiggum loop runs (default: weekly),
   **Then** the AI reviews its own past actions, identifies failure
   patterns (retries, errors, rejected approvals), proposes
   corrections as new items in `/Needs_Action`, and logs the
   self-review in `/Logs` with a `[RALPH_WIGGUM]` tag.

6. **Given** multiple MCP servers configured (email, Odoo, social),
   **When** a task requires coordination across multiple services,
   **Then** the orchestrator sequences MCP calls in the correct order,
   handles partial failures (one MCP succeeds, another fails), and
   reports the combined outcome.

7. **Given** any MCP server call that fails,
   **When** the error handler processes the failure,
   **Then** the system retries with exponential backoff (configurable
   max retries, default: 3), logs each attempt, and after final
   failure moves the item to `/Errors` with full diagnostic context.

---

### User Story 4 - Platinum: Always-On Cloud + Local Executive (Priority: P4)

As a user, I want the AI employee to run 24/7 in the cloud so it
operates even when my local machine is offline. The cloud instance
handles time-sensitive tasks autonomously (up to its approval
boundaries), while my local machine remains the executive seat where
I review approvals, access sensitive data, and make final decisions.
The vault syncs bidirectionally between cloud and local with clear
security boundaries — sensitive data stays local, operational data
flows to the cloud. The orchestrator runs at production grade with
health monitoring, auto-recovery, and zero-downtime deployments.

**Why this priority**: Always-on operation is the ultimate maturity
milestone. A Platinum-tier AI employee works while I sleep, handles
time zones, and never misses a deadline — while I retain full
executive control from my local machine whenever I come online.

**Independent Test**: Deploy the cloud instance, take the local
machine offline, send a test email and an Odoo event, verify the
cloud instance detects both, processes them to the approval boundary,
and queues the approval. Bring the local machine online, verify the
pending approvals sync within 5 minutes, approve one, reject one,
and verify the outcomes propagate back to the cloud instance. Confirm
that no local-only sensitive data was transmitted to the cloud.

**Acceptance Scenarios**:

1. **Given** a cloud-deployed AI employee instance running 24/7,
   **When** a monitored event occurs (email, message, Odoo record)
   while the user's local machine is offline,
   **Then** the cloud instance processes the event through the full
   pipeline up to the approval boundary and queues any approval
   requests for when the user returns.

2. **Given** the cloud instance has queued approval requests,
   **When** the user's local machine comes online,
   **Then** all pending approvals sync to the local
   `/Pending_Approval` folder within 5 minutes, with full context
   (proposed action, AI reasoning, original event).

3. **Given** the user approves or rejects an item on the local
   machine,
   **When** the sync cycle runs,
   **Then** the decision propagates to the cloud instance within
   5 minutes and the cloud resumes or halts execution accordingly.

4. **Given** a system with cloud/local role separation configured,
   **When** the AI processes any data,
   **Then** items tagged as `local_only` (credentials, financial
   details, personal identifiers) MUST NOT be transmitted to the
   cloud instance. The cloud operates on redacted summaries only.

5. **Given** a cloud instance running for 7 consecutive days,
   **When** the health report is generated,
   **Then** the report shows: uptime percentage, sync success rate,
   items processed, items pending approval, error count, and
   component statuses — with zero unplanned downtime.

6. **Given** a cloud component failure (watcher crash, MCP server
   unreachable),
   **When** the health monitor detects the failure,
   **Then** the system attempts auto-recovery (restart the component),
   logs the incident, alerts the user, and continues operating with
   degraded functionality if recovery fails.

7. **Given** a production deployment update is available,
   **When** the update is applied,
   **Then** the system performs a zero-downtime deployment — no items
   are lost, no approvals are dropped, and the transition is logged.

---

### Edge Cases

- **Partial file write**: When a watcher detects a file still being
  written, the system MUST wait for file stability (no modifications
  for a configurable period, default: 2 seconds) before processing.

- **Ambiguous intent**: When the AI cannot determine the appropriate
  action for an item, the item MUST move to `/Pending_Approval` with
  the AI's analysis of what was unclear, rather than being silently
  dropped or incorrectly processed.

- **Stale approvals**: Approval requests older than 24 hours MUST be
  flagged in the dashboard. Items MUST NOT be auto-approved due to
  age.

- **Duplicate detection**: When two watchers detect the same event,
  the system MUST deduplicate based on a content hash and source
  identifier, keeping the first occurrence and logging the duplicate.

- **Credential expiry mid-operation**: The system MUST fail the
  current operation gracefully, log the credential error (without
  exposing the credential value), and notify the user to
  re-authenticate.

- **Vault storage capacity**: The system MUST alert the user when
  storage reaches 90% capacity and refuse new items (rather than
  corrupting existing data) at 100%.

- **Watcher crash during processing**: If a watcher crashes while
  an item is being processed, the item MUST remain in its current
  stage (not be lost). On restart, the system MUST detect and
  resume incomplete items.

- **Concurrent plan execution**: If two processing cycles overlap,
  the system MUST use file-level locking to prevent the same item
  from being processed by two cycles simultaneously.

- **Sync conflict**: If the same item is modified on both cloud and
  local machines before a sync cycle completes, the system MUST
  detect the conflict, keep both versions, flag the item for human
  resolution, and NOT silently overwrite either version.

- **Cloud instance unreachable**: If the local machine cannot reach
  the cloud instance during a sync cycle, the system MUST queue
  local changes and retry on the next cycle. No data is lost.

- **Local-only data leak prevention**: If a skill or watcher
  accidentally tags operational data as `local_only`, the system
  MUST default to treating untagged data as local-only (fail-safe)
  until explicitly classified.

## Requirements *(mandatory)*

### Functional Requirements

**Vault Structure**

- **FR-001**: System MUST maintain an Obsidian vault with the
  following folder structure as its state machine:

  ```
  AI_Employee_Vault/
  ├── Inbox/              # Raw inputs land here
  ├── Needs_Action/       # Triaged items awaiting AI processing
  ├── Plans/              # Plan.md files created by the AI
  ├── In_Progress/        # Items currently being executed
  ├── Pending_Approval/   # Items awaiting human approval
  ├── Approved/           # Items approved, awaiting execution
  ├── Rejected/           # Items rejected by human
  ├── Done/               # Completed items
  ├── Errors/             # Items that failed after retries
  ├── Reports/            # CEO Briefings, audit reports
  ├── Logs/               # Daily JSON audit logs
  ├── Config/             # Watcher configs, approval policies
  ├── Skills/             # Agent Skill definitions
  └── Dashboard.md        # Real-time system status
  ```

- **FR-002**: Each item in the vault MUST be a markdown file with a
  YAML front-matter header containing: `id`, `type`, `source`,
  `priority`, `status`, `created_at`, `updated_at`, and
  `requires_approval`.

- **FR-003**: File movement between folders MUST be atomic — no item
  may exist in two folders simultaneously. Movement represents a
  state transition.

**Event Flow**

- **FR-004**: The system MUST follow this event processing flow:

  ```
  [External Event] → Watcher detects
       ↓
  Watcher creates .md in /Inbox
       ↓
  Triage skill reads /Inbox → moves to /Needs_Action with priority
       ↓
  Processing cycle reads /Needs_Action
       ↓
  AI invokes appropriate Agent Skill
       ↓
  Skill creates Plan.md in /Plans
       ↓
  Plan executor reads /Plans → moves item to /In_Progress
       ↓
  ┌─ Step requires approval? ──→ YES → move to /Pending_Approval
  │                                        ↓
  │                              Human approves → /Approved → resume
  │                              Human rejects  → /Rejected → stop
  │
  └─ NO → execute step
       ↓
  All steps done → move to /Done
       ↓
  Log entry written to /Logs/YYYY-MM-DD.json
       ↓
  Dashboard.md regenerated
  ```

- **FR-005**: Every state transition MUST be logged before the file
  is moved.

**State Transitions**

- **FR-006**: Items MUST follow only these valid state transitions:

  | From              | To                | Trigger                    |
  |-------------------|-------------------|----------------------------|
  | Inbox             | Needs_Action      | Triage skill completes     |
  | Needs_Action      | Plans             | AI creates plan            |
  | Plans             | In_Progress       | Plan execution begins      |
  | In_Progress       | Pending_Approval  | Step requires approval     |
  | In_Progress       | Done              | All steps complete         |
  | In_Progress       | Errors            | Retries exhausted          |
  | Pending_Approval  | Approved          | Human approves             |
  | Pending_Approval  | Rejected          | Human rejects              |
  | Approved          | In_Progress       | Execution resumes          |
  | Errors            | Needs_Action      | Manual retry by user       |

- **FR-007**: Any transition not listed above MUST be rejected by the
  system and logged as an invalid transition attempt.

**Watchers**

- **FR-008**: Bronze tier MUST include a filesystem watcher that
  monitors `/Inbox` for new files and detects additions within
  30 seconds.

- **FR-009**: Silver tier MUST add a Gmail watcher that polls for
  unread emails matching configurable criteria (sender, subject
  keywords, labels) at a configurable interval (default: 60s).

- **FR-010**: Silver tier MUST add a WhatsApp watcher that monitors
  configured contacts/groups for new messages.

- **FR-011**: Gold tier MUST add an Odoo watcher that polls for new
  records (sales orders, invoices, contacts) via JSON-RPC MCP.

- **FR-012**: Each watcher MUST be independently configurable via
  a JSON or YAML file in `/Config`.

**Agent Skills**

- **FR-013**: All AI reasoning MUST be executed through Agent Skills —
  named, versioned, documented units of AI capability.

- **FR-014**: Each Agent Skill MUST define: a name, a description,
  input schema, output schema, and whether the skill can trigger
  approval-required actions.

- **FR-015**: Bronze tier MUST include at minimum: a Triage Skill
  (classifies items), a Planning Skill (creates Plan.md), and a
  Dashboard Skill (regenerates Dashboard.md).

- **FR-016**: Gold tier MUST include: CEO Briefing Skill, Accounting
  Audit Skill, Social Media Draft Skill, and Ralph Wiggum
  Self-Review Skill.

**Human-in-the-Loop**

- **FR-017**: The following actions MUST require human approval before
  execution: sending any outbound email, sending any outbound message,
  posting to any social media platform, making any payment or
  financial transaction, deleting any user data, adding new contacts
  or external integrations, and any Odoo write operation.

- **FR-018**: The following actions MUST be auto-approved: reading
  files, creating plans, generating reports, writing log entries,
  updating the dashboard, and read-only Odoo queries.

- **FR-019**: Approval requests MUST present: the proposed action,
  the AI's reasoning, the original context, and an "Approve" /
  "Reject with feedback" choice.

**MCP Servers**

- **FR-020**: Silver tier MUST include one MCP server for email
  operations (send, receive, search).

- **FR-021**: Gold tier MUST add an Odoo JSON-RPC MCP server for ERP
  operations (read/write sales orders, invoices, contacts, accounting
  entries).

- **FR-022**: Gold tier MUST add MCP integrations for social media
  platforms (LinkedIn, Facebook, Instagram, Twitter).

- **FR-023**: Each MCP server MUST expose a health check endpoint
  that the orchestrator can poll.

**Scheduling and Orchestration**

- **FR-024**: Silver tier MUST support cron-based scheduling for
  watcher polling, processing cycles, and report generation.

- **FR-025**: Gold tier MUST orchestrate multiple MCP servers for
  tasks requiring cross-service coordination.

- **FR-026**: The orchestrator MUST handle partial MCP failures —
  if one MCP call succeeds and another fails, the orchestrator MUST
  log the partial state and NOT silently drop the successful result.

**Ralph Wiggum Loop (Gold)**

- **FR-027**: The Ralph Wiggum loop MUST run on a configurable
  schedule (default: weekly).

- **FR-028**: The loop MUST review audit logs from the review period,
  identify: failure patterns, frequently rejected drafts, high-retry
  operations, and slow processing times.

- **FR-029**: The loop MUST produce a self-review report and create
  actionable improvement items in `/Needs_Action` tagged with
  `[RALPH_WIGGUM]`.

- **FR-030**: The loop MUST NOT self-approve its own improvement
  proposals — all corrections require human approval.

**Reporting (Gold)**

- **FR-031**: The Weekly CEO Briefing MUST include: tasks completed
  (count and summary), tasks pending, errors encountered, approval
  summary (approved vs. rejected ratio), financial activity summary
  (if Odoo connected), and social media activity summary.

- **FR-032**: The Accounting Audit MUST check for: duplicate entries,
  unusual amounts (exceeding configurable thresholds), missing
  references, and unbalanced transactions.

**Security Model**

- **FR-033**: All credentials MUST be stored in `.env` files only —
  never in markdown, logs, version control, or dashboard output.

- **FR-034**: Log entries MUST redact sensitive values (email
  addresses partially masked, financial amounts shown only in
  aggregate in logs, full details only in approval prompts).

- **FR-035**: The system MUST validate that no `.env` values appear
  in any file written to the vault.

- **FR-036**: MCP server connections MUST use credential references
  (environment variable names), never inline credentials.

**Logging Schema**

- **FR-037**: Each daily audit log (`/Logs/YYYY-MM-DD.json`) MUST
  be a JSON array of log entry objects.

- **FR-038**: Each log entry MUST contain the following fields:

  ```
  {
    "timestamp": "ISO-8601 datetime",
    "actor": "skill name or watcher name",
    "action": "description of what was done",
    "item_id": "reference to the vault item",
    "from_state": "folder the item was in",
    "to_state": "folder the item moved to",
    "outcome": "success | failure | retry | dry_run",
    "duration_ms": number,
    "details": "additional context string",
    "approval": {
      "required": boolean,
      "status": "auto | pending | approved | rejected | n/a",
      "approver": "human | system | null"
    },
    "dry_run": boolean
  }
  ```

- **FR-039**: Logs MUST be append-only. Retroactive modification of
  log entries is prohibited.

- **FR-040**: Logs MUST be retained for a minimum of 90 days.

**DRY_RUN Mode**

- **FR-041**: The system MUST support a global `DRY_RUN` flag
  (set via environment variable `DRY_RUN=true|false`).

- **FR-042**: When `DRY_RUN=true`:
  - All reasoning, planning, and skill invocations proceed normally.
  - No files are moved between vault folders.
  - No outbound messages are sent (email, WhatsApp, social media).
  - No Odoo write operations are executed.
  - No payments or financial transactions are initiated.
  - All log entries are prefixed with `[DRY_RUN]` and the `dry_run`
    field is set to `true`.
  - The dashboard shows a prominent `[DRY_RUN MODE]` indicator.

- **FR-043**: DRY_RUN MUST be the default mode during development
  and initial deployment. Switching to live mode MUST require
  explicit user action.

**Error Handling and Retry**

- **FR-044**: All external operations (MCP calls, API requests) MUST
  use exponential backoff on failure: configurable base delay
  (default: 2 seconds), configurable max retries (default: 3),
  backoff multiplier of 2x per retry.

- **FR-045**: After all retries are exhausted, the item MUST move to
  `/Errors` with full diagnostic context (error type, message, retry
  count, timestamps of each attempt).

- **FR-046**: The system MUST NOT enter infinite retry loops. A
  maximum retry count MUST always be enforced.

**Cloud Deployment and Sync (Platinum)**

- **FR-050**: Platinum tier MUST support 24/7 cloud deployment of the
  AI employee as a persistent service that operates independently of
  the user's local machine.

- **FR-051**: The system MUST enforce role separation between cloud
  and local instances:
  - **Cloud role**: Runs watchers, processes events, executes
    auto-approved actions, queues approval requests.
  - **Local role**: Displays pending approvals, processes human
    decisions, stores sensitive/local-only data, provides the
    executive control interface.

- **FR-052**: The system MUST sync vault state bidirectionally
  between cloud and local instances:
  - Sync MUST occur within 5 minutes of either instance coming
    online.
  - Sync MUST be conflict-aware — if the same item is modified on
    both sides, the system MUST flag the conflict for human
    resolution.
  - Sync MUST be resumable — interrupted syncs pick up where they
    left off.

- **FR-053**: The system MUST enforce data classification boundaries:
  - Items tagged `local_only` MUST NOT be transmitted to the cloud.
  - The cloud instance receives redacted summaries for local-only
    items (enough context to process, no sensitive values).
  - Default classification for untagged items MUST be `local_only`
    (fail-safe).

- **FR-054**: The system MUST classify the following as `local_only`
  by default: credentials, financial account details, personal
  identifiers (SSN, passport), health records, and any item the user
  explicitly marks as sensitive.

**Production Orchestration (Platinum)**

- **FR-055**: The cloud orchestrator MUST include a health monitor
  that checks all components (watchers, MCP servers, sync service)
  at a configurable interval (default: 60 seconds).

- **FR-056**: The health monitor MUST attempt auto-recovery for
  failed components: restart the component up to 3 times with
  exponential backoff before declaring the component down.

- **FR-057**: The system MUST support zero-downtime deployments —
  updates are applied without losing items, dropping approvals, or
  interrupting active processing.

- **FR-058**: The system MUST generate a cloud health report at
  configurable intervals (default: hourly) containing: uptime,
  sync success rate, items processed, items pending, error count,
  component statuses, and last successful sync timestamp.

- **FR-059**: The system MUST alert the user (via configured channel)
  within 5 minutes of any component failure that auto-recovery
  cannot resolve.

**Security Boundaries (Platinum)**

- **FR-060**: Cloud-to-local and local-to-cloud communication MUST
  be encrypted in transit.

- **FR-061**: The cloud instance MUST NOT store `.env` files or raw
  credentials — it receives only credential references and uses a
  secure credential proxy for external service access.

- **FR-062**: The sync protocol MUST authenticate both endpoints
  before transmitting any data.

- **FR-063**: Audit logs from the cloud instance MUST sync to the
  local `/Logs` folder so the user has a complete audit trail
  regardless of which instance performed the action.

**Tiered Delivery**

- **FR-047**: Bronze tier MUST deliver: vault folder structure,
  filesystem watcher, AI processing with Agent Skills, Plan.md
  creation, file state transitions to `/Done`, audit logging,
  dashboard, and DRY_RUN mode.

- **FR-048**: Silver tier MUST add: Gmail watcher, WhatsApp watcher,
  email MCP server, human-in-the-loop approval workflow, cron
  scheduling, auto Plan.md creation for multi-step tasks, and
  error handling with retries.

- **FR-049**: Gold tier MUST add: Odoo JSON-RPC MCP server, social
  media integrations (LinkedIn, Facebook, Instagram, Twitter),
  weekly CEO Briefing generation, accounting audit, Ralph Wiggum
  self-improvement loop, multi-MCP orchestration, and comprehensive
  error recovery.

- **FR-064**: Platinum tier MUST add: 24/7 cloud deployment,
  cloud/local role separation, bidirectional vault sync, data
  classification and security boundaries, production-grade
  orchestration with health monitoring and auto-recovery,
  zero-downtime deployments, and encrypted cloud-local
  communication.

### Key Entities

- **Task Item**: A unit of work flowing through the vault. A markdown
  file with YAML front-matter containing: `id` (unique), `type`
  (file, email, message, social, erp, audit), `source` (watcher
  name), `priority` (low, medium, high, urgent), `status` (maps to
  current folder), `requires_approval` (boolean), `created_at`,
  `updated_at`, and a body section with the original content.

- **Plan**: A structured breakdown of a Task Item into executable
  steps. Stored as `Plan.md` in `/Plans`. Contains: reference to the
  original Task Item, the AI's reasoning, and an ordered list of
  steps — each with a description, expected outcome, approval
  requirement, and status (pending/in_progress/done/failed).

- **Approval Request**: A Task Item that has been routed to
  `/Pending_Approval`. The file includes: the proposed action, the
  original context, the AI's reasoning, and a creation timestamp
  (expires after 24 hours without auto-approving).

- **Audit Log Entry**: A JSON object in the daily log file. Contains
  all fields defined in FR-038.

- **Watcher Configuration**: A JSON/YAML file in `/Config` defining
  a monitored source. Contains: watcher type, polling interval,
  filter criteria, and credential reference (env var name only).

- **Agent Skill**: A named, versioned AI capability with defined
  inputs, outputs, and an error contract. Stored as a definition
  file in `/Skills`.

- **Dashboard State**: A generated markdown file (`/Dashboard.md`)
  showing: item counts per folder, recent activity, error count,
  watcher/MCP health statuses, DRY_RUN indicator, and last-updated
  timestamp.

- **CEO Briefing**: A weekly summary report in `/Reports`. Contains:
  period covered, tasks completed, tasks pending, error summary,
  approval ratio, financial summary, social media summary.

- **Sync Manifest**: A metadata file tracking bidirectional vault
  sync between cloud and local instances. Contains: last sync
  timestamp, items synced (count and IDs), conflicts detected,
  sync direction (cloud→local, local→cloud), and sync status
  (success, partial, failed).

- **Data Classification Tag**: A front-matter field on every vault
  item indicating its sensitivity level: `local_only` (never leaves
  local machine), `syncable` (safe for cloud), or `redacted_summary`
  (cloud receives summary only). Default: `local_only`.

### Assumptions

- The user's local machine runs Linux, macOS, or WSL capable of
  executing Python background processes and watching filesystem
  events.

- The Obsidian vault is a standard folder on the local filesystem.
  No Obsidian-specific plugins are required — any markdown editor
  works.

- The user has existing Gmail, WhatsApp, and (for Gold) Odoo accounts
  they want to monitor.

- Social media integrations use official APIs or authorized
  third-party tools; the user provides API credentials.

- DRY_RUN mode is the default. Switching to live mode is a conscious
  user decision.

- The approval policy (FR-017 / FR-018) ships with safe defaults
  and is configurable via `/Config`.

- Claude Code is the AI engine. Agent Skills are implemented as
  Claude Code Skills with structured prompts.

- MCP servers run as local processes alongside the vault watchers.

- For Platinum tier, the cloud deployment target is a Linux server or
  container environment capable of running the same Python processes
  and MCP servers as the local machine.

- Cloud-local sync uses a secure channel (the specific transport is
  a planning decision); the spec requires encryption in transit and
  mutual authentication.

- The user accepts that Platinum tier requires network connectivity
  for the cloud instance; the local instance continues to function
  fully offline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A file dropped into `/Inbox` is detected, triaged,
  planned, executed, and moved to `/Done` within 5 minutes without
  human intervention (Bronze tier).

- **SC-002**: The system autonomously handles 80% or more of routine
  tasks, requiring human approval only for sensitive operations as
  defined in FR-017.

- **SC-003**: Human approval time averages less than 5 minutes per
  day across all pending items.

- **SC-004**: Zero unauthorized actions are recorded in the audit
  trail over any 30-day measurement period.

- **SC-005**: Every action taken by the system is traceable in the
  audit log with complete context (who, what, when, why, outcome).

- **SC-006**: No credentials or sensitive tokens appear in any log
  file, vault file, or dashboard output.

- **SC-007**: Each tier (Bronze, Silver, Gold, Platinum) is fully
  functional and independently usable before work begins on the
  next tier.

- **SC-008**: The system degrades gracefully when a component fails —
  remaining components continue operating and the user is alerted
  within 5 minutes.

- **SC-009**: The Ralph Wiggum loop identifies at least one
  actionable improvement per review cycle after 30 days of operation.

- **SC-010**: The weekly CEO Briefing is generated on schedule with
  accurate data from the audit logs and connected systems.

- **SC-011**: The cloud instance maintains 99% uptime over a rolling
  30-day period (measured by health reports).

- **SC-012**: Vault sync between cloud and local completes within
  5 minutes of either instance coming online, with zero data loss.

- **SC-013**: No `local_only` data appears in the cloud instance's
  storage, logs, or transmitted data — verified by automated
  classification audit.
