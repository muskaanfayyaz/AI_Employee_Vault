# Feature Specification: Gold Tier — Business Integration & Autonomous Loop

**Feature Branch**: `002-gold-tier`
**Created**: 2026-02-26
**Status**: Draft
**Parent Spec**: `001-ai-employee-system`
**Input**: User description: "Extend system to Gold Tier. Add: Odoo accounting integration via JSON-RPC, LinkedIn/Facebook/Instagram/Twitter automation, Weekly CEO briefing generator, Subscription audit logic, Ralph Wiggum autonomous loop, Retry handler, Graceful degradation. Include: Cross-domain integration architecture, Security boundaries, Approval thresholds, Audit logging schema."

---

## Context

Gold Tier extends the Silver Tier AI Employee (email triage, cron scheduling, human-in-the-loop approval) into a full Digital FTE that connects to business systems, manages social presence, reports to leadership, and continuously improves itself. All Silver Tier behaviours remain active; this spec adds capabilities on top of them.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Odoo Business Event Detection & Response (Priority: P1)

As a business owner, I want the AI employee to monitor my Odoo ERP for new and changed records — sales orders, invoices, contacts, and accounting entries — and automatically triage them into the vault's action queue, so that no business event goes unnoticed or unprocessed.

**Why this priority**: Odoo is the system of record for money and customers. Connecting to it first makes every subsequent capability (audit, briefing, subscriptions) possible. Without this, Gold Tier has no business data.

**Independent Test**: Connect the Odoo integration with test credentials. Create a new invoice in Odoo. Verify the AI employee detects the invoice within the polling interval, creates a vault item in `/Needs_Action` with the invoice ID and summary, processes it through the standard pipeline, and logs the full event chain. No other Gold Tier capability needs to be active.

**Acceptance Scenarios**:

1. **Given** a configured Odoo integration and a polling interval of 60 seconds,
   **When** a new sales order is created in Odoo,
   **Then** the AI employee detects the order within 60 seconds and creates a vault item in `/Needs_Action` containing: record type, Odoo ID, customer name, and total amount (no raw credentials in the item).

2. **Given** a vault item created from an Odoo invoice,
   **When** the AI processes the item,
   **Then** the system creates a `Plan.md` with appropriate steps (review, respond, flag, or route for approval) based on the invoice type and amount.

3. **Given** an Odoo write operation is required (e.g., marking an invoice as reviewed),
   **When** the plan step executes,
   **Then** the action is routed to `/Pending_Approval` before any write is performed — Odoo is NEVER written to without human approval.

4. **Given** the Odoo integration is temporarily unreachable,
   **When** a polling cycle runs,
   **Then** the system logs the connection failure, retries with exponential backoff (3 attempts minimum), and continues processing previously queued items without crashing.

5. **Given** `DRY_RUN=true`,
   **When** any Odoo operation is planned,
   **Then** all reasoning and plan creation proceeds normally, but no Odoo reads are skipped — only Odoo write operations are suppressed, and all log entries carry `[DRY_RUN]`.

---

### User Story 2 — Social Media Drafting & Approval (Priority: P2)

As a business owner, I want the AI employee to draft platform-appropriate posts for LinkedIn, Facebook, Instagram, and Twitter based on business events, content cues from the vault, or scheduled campaigns, and route every draft through my approval before anything is published.

**Why this priority**: Social media is the most visible output channel. A single unapproved post can cause reputational harm. The approval gate is non-negotiable. This story delivers that gate before any other social capability is built.

**Independent Test**: Drop a content brief into `/Needs_Action` tagged `type: social_post`. Verify the AI drafts a platform-appropriate post for each configured platform, places each draft in `/Pending_Approval`, waits for approval, and only upon approval routes the post for publishing. Without approval, nothing is sent. Platforms not configured are skipped gracefully.

**Acceptance Scenarios**:

1. **Given** a content brief or trigger event in `/Needs_Action`,
   **When** the AI processes it with social media context,
   **Then** the AI generates a separate draft for each configured platform (LinkedIn, Facebook, Instagram, Twitter), respecting character limits and tone guidelines per platform.

2. **Given** a drafted social post in `/Pending_Approval`,
   **When** the approval request is presented,
   **Then** the approval item shows: platform name, full post text, character count, any attached media reference, and the original trigger context.

3. **Given** an approved social post,
   **When** the execution step runs,
   **Then** the post is published to the specified platform, the vault item moves to `/Done`, and the action is logged with: platform, post ID (returned by the platform), timestamp, and approval reference.

4. **Given** a rejected social post with user feedback,
   **When** the rejection is recorded,
   **Then** the item moves to `/Rejected` with the feedback embedded, and NO content is published — no retry without a new approval cycle.

5. **Given** a social platform API is unavailable at publish time,
   **When** the publish step executes,
   **Then** the system retries with exponential backoff, logs each attempt, and after exhausting retries moves the item to `/Errors` with diagnostic details. The approved draft is preserved in the error item for manual resubmission.

6. **Given** any social media action,
   **When** `DRY_RUN=true`,
   **Then** draft creation proceeds normally, approval routing proceeds normally, but the final publish step is suppressed and logged as `[DRY_RUN]`.

---

### User Story 3 — Weekly CEO Briefing (Priority: P3)

As a CEO or business owner, I want a structured weekly summary delivered to a designated vault location (and optionally to my email) every Monday at 8:00 AM, covering all activity from the prior week — tasks, approvals, errors, financials, and social media — so I can stay informed with minimal reading time.

**Why this priority**: The CEO Briefing is the primary value-delivery mechanism for executive stakeholders. It proves the system is working and provides actionable oversight. It depends on the Odoo and social capabilities being functional but does not require them — it degrades gracefully if data sources are unavailable.

**Independent Test**: Run the briefing generator against at least 7 days of audit logs (real or synthesised). Verify a `CEO_Briefing_YYYY-MM-DD.md` appears in `/Reports` containing all required sections. Verify that sections for unavailable data sources (e.g., Odoo not connected) show a `[DATA UNAVAILABLE]` notice rather than an error. Verify the briefing is delivered on schedule.

**Acceptance Scenarios**:

1. **Given** a scheduled trigger on the configured day and time (default: Monday 08:00),
   **When** the briefing generation skill runs,
   **Then** a file `CEO_Briefing_YYYY-MM-DD.md` is created in `/Reports` containing all mandatory sections (defined in FR-031).

2. **Given** a completed briefing,
   **When** email delivery is configured,
   **Then** the briefing is routed through the standard approval workflow before being sent — the CEO receives nothing without the approval gate being passed.

3. **Given** a data source (e.g., Odoo) that is unavailable when the briefing runs,
   **When** the briefing is generated,
   **Then** the affected section shows `[DATA UNAVAILABLE — source offline]` and the briefing is still generated and delivered on schedule for all available sections.

4. **Given** no audit logs exist for the review period,
   **When** the briefing runs,
   **Then** the briefing is still generated with a note "No activity recorded for this period" — it MUST NOT fail silently or produce an empty file.

---

### User Story 4 — Subscription Audit (Priority: P3)

As a business owner using Odoo's subscription module, I want the AI employee to periodically audit all active, overdue, and cancelled subscriptions, flag anomalies (missed renewals, unexpected cancellations, billing gaps), and surface items requiring human review — without making any changes to Odoo without approval.

**Why this priority**: Missed renewals and billing gaps directly impact cash flow. Manual subscription auditing is time-consuming and error-prone. This capability prevents revenue leakage. It shares the Odoo integration from Story 1, so no new connectivity is required.

**Independent Test**: Point the subscription audit at a test Odoo instance with a set of subscriptions including at least one overdue, one recently cancelled, and one with a billing gap. Verify the audit report is created in `/Reports`, all anomalies are listed with Odoo record IDs, and no Odoo records are modified.

**Acceptance Scenarios**:

1. **Given** a configured Odoo subscription audit on its schedule (default: weekly),
   **When** the audit skill runs,
   **Then** the system reads all active, overdue, and recently cancelled subscriptions from Odoo and generates a report in `/Reports/Subscription_Audit_YYYY-MM-DD.md`.

2. **Given** the audit identifies anomalies (missed renewal, unexpected cancellation, billing gap, duplicate subscription),
   **When** the report is generated,
   **Then** each anomaly is listed with: subscription ID, customer name, anomaly type, amount at risk, and recommended action.

3. **Given** an anomaly requiring follow-up action (e.g., re-invoicing a missed payment),
   **When** the audit skill creates a follow-up,
   **Then** a vault item is created in `/Needs_Action` for each anomaly requiring action — no Odoo write is made by the audit skill itself.

4. **Given** Odoo subscription data is unavailable,
   **When** the audit runs,
   **Then** the skill logs the failure, skips the audit, and creates a vault item flagging the missed audit run. It MUST NOT silently succeed with empty output.

---

### User Story 5 — Ralph Wiggum Autonomous Improvement Loop (Priority: P4)

As a user, I want the AI employee to periodically review its own past performance — examining failures, retries, rejected approvals, and slow operations — and propose concrete improvements to its own configuration and skill logic, for my review and approval.

**Why this priority**: A self-improving system compounds its value over time. Without this loop, errors that repeat go unaddressed. Ralph Wiggum closes the feedback cycle from all prior tiers and ensures the system learns from mistakes.

**Independent Test**: Accumulate at least 7 days of audit logs containing failures, retries, and rejected items. Trigger the Ralph Wiggum loop. Verify a self-review log entry tagged `[RALPH_WIGGUM]` is written. Verify improvement proposals appear in `/Needs_Action`. Verify the proposals require human approval before any change takes effect.

**Acceptance Scenarios**:

1. **Given** at least 7 days of audit logs and at least one recorded failure, retry, or rejection,
   **When** the Ralph Wiggum loop runs (default: weekly, configurable),
   **Then** the system analyses the logs and produces a structured self-review report in `/Logs/RalphWiggum_Review_YYYY-MM-DD.json` tagged `[RALPH_WIGGUM]`.

2. **Given** the self-review identifies improvement opportunities,
   **When** the loop completes its analysis,
   **Then** each improvement is created as a vault item in `/Needs_Action` with: the identified pattern, evidence (log references), and the proposed correction.

3. **Given** an improvement proposal in `/Needs_Action`,
   **When** the plan executor processes it,
   **Then** the proposal is routed to `/Pending_Approval` — the Ralph Wiggum loop MUST NOT self-approve its own suggestions.

4. **Given** fewer than 7 days of audit logs,
   **When** the loop is triggered,
   **Then** the loop skips analysis, logs a `[RALPH_WIGGUM][SKIPPED] Insufficient log history` entry, and reschedules for the next cycle. No error is raised.

5. **Given** Ralph Wiggum has run for 30 days,
   **When** its reports are reviewed,
   **Then** at least one actionable improvement has been proposed per cycle — the loop MUST NOT produce empty reports when failures exist in the logs.

---

### User Story 6 — Retry Handler & Graceful Degradation (Priority: P2)

As a user, I want the system to handle all external integration failures (Odoo unreachable, social platform rate-limited, briefing email failed) without crashing, without losing work, and without requiring my intervention — automatically retrying within safe limits and clearly reporting what degraded and why.

**Why this priority**: Gold Tier touches multiple external systems. Any one of them can fail independently. Graceful degradation is what separates a toy prototype from a reliable digital employee. This story is a horizontal capability that protects all Gold Tier stories.

**Independent Test**: Simulate each of the four external integration failures (Odoo unreachable, each social platform returning 500, email delivery failure). For each, verify: (a) the system retries exactly the configured number of times, (b) the item moves to `/Errors` with full diagnostic context after retries are exhausted, (c) all other integrations continue processing normally, (d) the dashboard reflects the degraded state, and (e) no data is lost.

**Acceptance Scenarios**:

1. **Given** an external integration call that fails,
   **When** the retry handler processes the failure,
   **Then** the system retries with exponential backoff (configurable base: 2s, multiplier: 2x, max retries: 3) and logs each attempt with: attempt number, timestamp, error type, and error message.

2. **Given** all retries exhausted for a vault item,
   **When** the final retry fails,
   **Then** the item moves to `/Errors` with a complete diagnostic record: integration name, error history, retry timestamps, and the last known state of the item.

3. **Given** one integration is in a degraded state (all retries failing),
   **When** new items arrive that use a different integration,
   **Then** the other integrations continue processing normally — degradation of one integration MUST NOT cascade to others.

4. **Given** a degraded integration that recovers,
   **When** the next processing cycle runs,
   **Then** items in `/Errors` from that integration are NOT automatically reprocessed — they require explicit user action to requeue. This prevents surprise replays.

5. **Given** the system is in a degraded state,
   **When** the dashboard regenerates,
   **Then** the dashboard shows a `[DEGRADED]` indicator for each affected component with the last error message and last successful contact timestamp.

---

### Edge Cases

- **Odoo API version mismatch**: When the Odoo instance returns responses in an unexpected format, the system MUST log the mismatch, skip the affected records, and NOT silently discard data. A vault item is created in `/Errors` with the raw response excerpt.

- **Social platform rate limit**: When a social platform returns a rate-limit error, the system MUST respect the `Retry-After` header (or equivalent), log the rate limit event, and NOT count rate-limit delays as retry failures.

- **CEO Briefing duplicate**: When the briefing trigger fires twice in the same period (e.g., scheduling glitch), the system MUST detect the duplicate (same week/period), skip generation, and log a `[DUPLICATE_SKIPPED]` entry.

- **Subscription audit over large dataset**: When the Odoo subscription count exceeds a configurable page size, the audit MUST paginate through all records — it MUST NOT silently audit only the first page.

- **Ralph Wiggum log explosion**: When audit logs contain more than a configurable entry count (default: 10,000 per review period), the loop MUST summarise rather than exhaustively enumerate — to prevent AI context overflow.

- **Approval cascade**: When a Gold Tier action requires approval and the user is unavailable for more than 24 hours, the item MUST be flagged in the dashboard as `[STALE_APPROVAL]` — it MUST NOT be auto-approved due to age.

- **Cross-domain partial failure**: When a task requires both an Odoo write and a social media post, and one succeeds while the other fails, the system MUST log the partial state, NOT reverse the successful action, and flag the failed action for human review.

- **Credential rotation**: When an Odoo or social media credential is rotated by the user, the system MUST reload credentials from environment on the next cycle without requiring a restart.

- **Concurrent Ralph Wiggum triggers**: If two Ralph Wiggum cycles overlap (e.g., manual trigger while scheduled run is active), the second invocation MUST detect the active run, skip execution, and log a `[CONCURRENT_SKIP]` entry.

---

## Requirements *(mandatory)*

### Functional Requirements

**Odoo Integration**

- **FR-G001**: The system MUST connect to Odoo using a configurable credential set stored exclusively in `.env` — never in vault files, logs, or dashboard output.

- **FR-G002**: The Odoo integration MUST support read operations for: sales orders, invoices, contacts, accounting journal entries, and subscriptions.

- **FR-G003**: The Odoo integration MUST support write operations for: marking records as reviewed, adding notes/comments, updating status fields — and ALL write operations MUST be routed through the approval workflow before execution.

- **FR-G004**: The Odoo integration MUST expose the following capabilities as discrete, named operations:
  - `fetch_invoices` — retrieve invoices by date range, status, or customer
  - `fetch_payments` — retrieve payment records
  - `fetch_subscriptions` — retrieve subscription records with status
  - `create_invoice` — create a draft invoice (draft status only; MUST NOT auto-post)
  - `create_payment` — create a payment record (requires approval before commit)
  - `fetch_journal_entries` — retrieve accounting journal entries for audit

- **FR-G005**: Invoice creation MUST produce draft invoices only. The system MUST NEVER auto-post an invoice to Odoo without explicit human approval. This is an inviolable constraint.

- **FR-G006**: Payment creation MUST be queued to `/Pending_Approval` before any commit to Odoo. The system MUST NEVER initiate a payment without human approval. This is an inviolable constraint.

- **FR-G007**: The Odoo integration MUST implement paginated polling — it MUST retrieve all changed records since the last poll timestamp, not just the first page.

- **FR-G008**: The Odoo integration MUST store the last-polled timestamp in a persistent state file in `/Config` so polls resume correctly after restart.

**Approval Thresholds**

- **FR-G009**: The system MUST enforce the following tiered approval policy for financial actions:

  | Action Type                        | Threshold           | Approval Required |
  |------------------------------------|---------------------|-------------------|
  | Read any Odoo record               | Any amount          | No (auto)         |
  | Create draft invoice               | Any amount          | No (auto for draft creation; Yes for posting) |
  | Post/confirm invoice               | Any amount          | Yes — always      |
  | Create or commit payment           | Any amount          | Yes — always      |
  | Accounting journal write           | Any amount          | Yes — always      |
  | Social media post (any platform)   | N/A                 | Yes — always      |
  | Send email                         | N/A                 | Yes — always      |
  | Delete or archive any Odoo record  | Any amount          | Yes — always      |

- **FR-G010**: Approval thresholds MUST be configurable via `/Config/approval_policy.json` — the table above represents safe defaults. Users MAY raise (but not lower below safe defaults) thresholds.

- **FR-G011**: Any operation whose approval threshold is not explicitly defined in the policy MUST default to requiring approval. Unknown operations are NEVER auto-approved.

**Social Media Integration**

- **FR-G012**: The system MUST support the following platforms as independently configurable integrations: LinkedIn, Facebook, Instagram, Twitter/X. Each platform is optional — the system operates with any subset configured.

- **FR-G013**: Each social platform integration MUST support: `draft_post`, `publish_post` (approval-gated), `fetch_recent_posts`, and `fetch_engagement_metrics`.

- **FR-G014**: Social media posts MUST respect per-platform constraints: character limits, supported media types, and API rate limits. The drafting skill MUST produce platform-specific versions, not a single generic post.

- **FR-G015**: Social media publish operations MUST NEVER execute without a recorded approval in the vault. The approval record MUST reference the exact post text that was approved — any post modification after approval triggers a new approval cycle.

**CEO Briefing**

- **FR-G016**: The CEO Briefing skill MUST run on a configurable schedule (default: Monday 08:00 local time) and produce a report at `/Reports/CEO_Briefing_YYYY-MM-DD.md`.

- **FR-G017**: The CEO Briefing MUST include the following sections, each with a `[DATA UNAVAILABLE]` fallback if the source is offline:
  1. **Period Summary** — date range covered and briefing generation timestamp
  2. **Tasks Completed** — count and one-line summaries of all items moved to `/Done`
  3. **Tasks Pending** — count and age of items still in queue (by stage)
  4. **Errors & Failures** — count, types, and unresolved items in `/Errors`
  5. **Approval Summary** — total requests, approval rate, average time-to-decision
  6. **Financial Activity** — (if Odoo connected) invoices created, payments processed, anomalies flagged
  7. **Social Media Activity** — (if any platform connected) posts drafted, approved, published, engagement summary
  8. **Subscription Health** — (if Odoo subscriptions enabled) active count, overdue count, at-risk revenue
  9. **Ralph Wiggum Insights** — (if loop has run) top identified patterns and proposals status

- **FR-G018**: The CEO Briefing MUST NOT contain raw credentials, full financial account numbers, or personal identifiers — only aggregated summaries and item counts.

**Subscription Audit**

- **FR-G019**: The subscription audit skill MUST run on a configurable schedule (default: weekly, same day as CEO Briefing) and produce a report at `/Reports/Subscription_Audit_YYYY-MM-DD.md`.

- **FR-G020**: The audit MUST check for the following anomaly types:
  - Subscriptions overdue for renewal (past renewal date, not yet renewed)
  - Subscriptions cancelled within the past review period
  - Subscriptions with a billing gap (invoices expected but not found)
  - Duplicate subscription records for the same customer
  - Subscriptions with amounts that deviate more than a configurable threshold (default: 20%) from their historical average

- **FR-G021**: For each anomaly found, the audit MUST create a vault item in `/Needs_Action` with: anomaly type, subscription ID, customer reference, amount at risk, and recommended action — so the AI can plan a follow-up.

- **FR-G022**: The subscription audit MUST NOT modify any Odoo record. It is strictly read-and-report. Any remediation is a separate workflow triggered by the vault items it creates.

**Ralph Wiggum Loop**

- **FR-G023**: The Ralph Wiggum loop MUST run on a configurable schedule (default: weekly). It MUST have a minimum review window of 7 days — it MUST NOT run against fewer than 7 days of logs.

- **FR-G024**: The loop MUST analyse the audit logs for: failure rate by integration, retry rate by operation type, rejection rate for approval requests, operations consistently exceeding expected duration.

- **FR-G025**: For each identified pattern, the loop MUST produce a structured improvement proposal containing: pattern description, evidence (log timestamp references), severity (low/medium/high), and proposed correction.

- **FR-G026**: All improvement proposals MUST be routed to `/Pending_Approval`. The Ralph Wiggum loop MUST NOT apply any change to configuration, skills, or system behaviour without human approval.

- **FR-G027**: The self-review output MUST be logged to `/Logs/RalphWiggum_Review_YYYY-MM-DD.json` with each log entry tagged `[RALPH_WIGGUM]`.

- **FR-G028**: The loop MUST implement a deduplication check — if the same improvement was proposed in a previous cycle and is still pending approval, the loop MUST NOT create a duplicate proposal. It MUST log `[RALPH_WIGGUM][DUPLICATE_SKIPPED]` instead.

**Retry Handler**

- **FR-G029**: All external integration calls (Odoo, social platforms, email) MUST pass through a shared retry handler with the following configurable parameters:
  - `base_delay_seconds` (default: 2)
  - `backoff_multiplier` (default: 2.0)
  - `max_retries` (default: 3)
  - `max_delay_seconds` (default: 30, cap to prevent excessive wait)

- **FR-G030**: The retry handler MUST distinguish between retryable errors (connection timeout, 429 rate limit, 503 service unavailable) and non-retryable errors (401 unauthorized, 404 not found, 400 bad request). Non-retryable errors MUST fail immediately without retrying.

- **FR-G031**: Each retry attempt MUST be logged individually with: attempt number, delay applied, error type, and error message.

- **FR-G032**: For rate-limit errors (HTTP 429 or equivalent), the retry handler MUST honour any `Retry-After` value provided by the service. Rate-limit delays MUST NOT count as retry failures.

**Graceful Degradation**

- **FR-G033**: Each Gold Tier integration (Odoo, each social platform, email) MUST operate as an independently degradable component. Failure of one MUST NOT affect the operation of others.

- **FR-G034**: When a component enters a degraded state (all retries exhausted for the most recent attempt), the dashboard MUST show a `[DEGRADED: <component>]` indicator with the last error message and last successful contact timestamp.

- **FR-G035**: Items in `/Errors` due to integration failure MUST NOT be automatically reprocessed when the integration recovers. They MUST remain in `/Errors` until the user explicitly requeues them. This is a deliberate design constraint to prevent surprise replays.

- **FR-G036**: The system MUST continue generating CEO Briefings and Subscription Audit reports even when all external integrations are degraded — using audit log data and marking unavailable sections explicitly.

**Cross-Domain Integration Architecture**

- **FR-G037**: The orchestrator MUST maintain an integration registry — a runtime map of all configured integrations, their health status, and last-contact timestamps.

- **FR-G038**: When a task requires coordination across multiple integrations (e.g., Odoo data → social post → briefing), the orchestrator MUST execute steps sequentially as defined in the `Plan.md`, recording the outcome of each step before proceeding to the next.

- **FR-G039**: In the event of a partial cross-domain failure (some steps succeeded, some failed), the orchestrator MUST: log the partial state, preserve the outputs of successful steps in the vault item, flag the failed steps for human review, and NOT attempt to undo already-successful steps.

**Security Boundaries**

- **FR-G040**: All Odoo credentials (URL, database name, username, API key/password) MUST be stored in `.env` only. The vault, logs, briefings, and dashboard MUST NEVER contain raw Odoo credentials.

- **FR-G041**: All social media API credentials MUST be stored in `.env` only, with one credential block per platform. The vault MUST only reference credential names (e.g., `LINKEDIN_API_KEY`), never their values.

- **FR-G042**: Financial data in vault items and reports MUST be shown at the summary/aggregate level only (e.g., total invoice count, total amount by status). Individual transaction details are accessible only in the approval prompt — not in logs or dashboard.

- **FR-G043**: The system MUST validate before every write operation that no credential values from `.env` are present in the data being written to Odoo, social platforms, or any vault file.

- **FR-G044**: Social media post content MUST be reviewed for credential/sensitive-data leakage as part of the drafting skill. Any draft containing patterns matching credential formats (API keys, tokens, passwords) MUST be rejected by the drafting skill and flagged for review.

- **FR-G045**: Audit logs MUST partially mask sensitive identifiers: email addresses shown as `u***@domain.com`, financial amounts shown in aggregate in logs (full amounts only in approval prompts), customer names shown in full (not sensitive by default).

**Audit Logging Schema (Gold Tier Extensions)**

- **FR-G046**: All Gold Tier log entries MUST conform to the base log schema defined in FR-038 (Silver Tier), extended with the following additional fields where applicable:

  ```json
  {
    "integration": "odoo | linkedin | facebook | instagram | twitter | email | internal",
    "operation": "named operation (e.g., fetch_invoices, publish_post)",
    "retry_context": {
      "attempt": 1,
      "max_attempts": 3,
      "delay_ms": 2000
    },
    "approval_threshold": "auto | approval_required | policy_reference",
    "cross_domain_task_id": "reference if part of multi-integration task",
    "ralph_wiggum_tag": "[RALPH_WIGGUM] | null",
    "degraded": false
  }
  ```

- **FR-G047**: Ralph Wiggum entries MUST use a distinct log file: `/Logs/RalphWiggum_Review_YYYY-MM-DD.json` — they MUST NOT be mixed into the daily operational log.

- **FR-G048**: Social media publish events MUST log the approval record ID as a required field. A publish event without a corresponding approval record ID MUST be flagged as an integrity violation.

- **FR-G049**: All financial action log entries (Odoo writes, payment creation) MUST include the approval record ID as a required field. Odoo write events without approval record IDs MUST be flagged as integrity violations.

### Key Entities

- **Odoo Record Event**: A vault item created by the Odoo watcher. Contains: Odoo model name, record ID, record summary (no raw credentials), watcher poll timestamp, and detected change type (created/updated/overdue).

- **Social Draft**: A vault item in `/Pending_Approval` representing a proposed social post. Contains: platform name, post text, character count, media references, source trigger (what prompted the draft), and approved-text hash (computed at approval, verified at publish).

- **CEO Briefing Document**: A structured markdown report in `/Reports`. Contains all sections defined in FR-G017. Generated by the CEO Briefing Skill from audit logs and integration data.

- **Subscription Anomaly Item**: A vault item in `/Needs_Action` created by the Subscription Audit Skill. Contains: anomaly type, Odoo subscription ID, customer reference, amount at risk, and recommended action.

- **Ralph Wiggum Proposal**: A vault item in `/Needs_Action` created by the self-review loop. Contains: identified failure pattern, supporting log evidence, severity, and proposed correction. Requires human approval before any effect.

- **Integration Registry**: A runtime state object (persisted in `/Config/integration_registry.json`) tracking: integration name, health status (`healthy | degraded | down`), last successful contact timestamp, last error message, and retry state.

- **Retry Record**: A structured entry within a vault item's metadata tracking: integration, operation, total attempts, timestamps of each attempt, error types per attempt, final outcome.

- **Approval Policy**: A JSON configuration file at `/Config/approval_policy.json` defining the approval thresholds table (FR-G009). Governs which operations require human approval.

### Assumptions

- Silver Tier is fully operational. Gold Tier is additive only — it does not replace or modify any Silver Tier component.

- The user has an Odoo instance (self-hosted or cloud) with API access enabled. The system connects via Odoo's external API (JSON-RPC), using credentials provided by the user.

- Social media platforms are connected via their official APIs or authorised integration layers. The user provides API credentials for each platform they wish to activate. Platforms without credentials are silently skipped.

- The system runs on a machine with internet connectivity to reach Odoo and social media APIs. All operations degrade gracefully when connectivity is lost.

- The existing Silver Tier retry logic (FR-044 to FR-046) is superseded by the Gold Tier retry handler (FR-G029 to FR-G032), which is a unified implementation applied to all tiers.

- `DRY_RUN=true` is the default for all new integrations until the user explicitly switches each integration to live mode via its `/Config` entry.

- The Ralph Wiggum loop analyses the AI's own operational behaviour — it does NOT rewrite code or configuration files directly. All proposed changes are described in natural language for human implementation.

- The CEO Briefing email delivery reuses the Silver Tier email MCP server. If that server is unavailable, the briefing is still written to `/Reports` and the email delivery is treated as a degraded component.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-G001**: The AI employee detects and triages Odoo events (new invoices, orders, contacts) within 90 seconds of them occurring in Odoo, under normal network conditions.

- **SC-G002**: Zero Odoo invoices are auto-posted or payments committed without a recorded human approval in the vault audit trail — verified across any 30-day operating period.

- **SC-G003**: Zero social media posts are published without a corresponding approval record — verified across any 30-day operating period.

- **SC-G004**: The CEO Briefing is generated within 5 minutes of its scheduled trigger time, every week, regardless of whether external integrations are available.

- **SC-G005**: The Subscription Audit identifies 100% of the anomaly types defined in FR-G020 when test data containing those anomalies is present.

- **SC-G006**: The Ralph Wiggum loop produces at least one actionable improvement proposal per cycle after 30 days of system operation, when failures exist in the audit logs.

- **SC-G007**: A single integration failure (Odoo down, one social platform unavailable) does not prevent any other integration from processing — verified by integration failure simulation tests.

- **SC-G008**: All retry attempts are logged individually. Any vault item in `/Errors` can be fully diagnosed from its error record alone — without requiring external system inspection.

- **SC-G009**: No raw credentials, API keys, or sensitive tokens appear in any vault file, log entry, briefing, audit report, or dashboard — verified by automated credential-leak scan.

- **SC-G010**: The system operates in `DRY_RUN=true` mode by default for all Gold Tier integrations until explicitly switched to live. No accidental live operations during setup.
