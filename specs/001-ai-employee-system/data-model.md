# Data Model: AI Employee System

**Phase**: 1 — Design & Contracts
**Date**: 2026-02-17
**Branch**: `001-ai-employee-system`

## Entity: Task Item

A unit of work flowing through the vault. Represented as a markdown
file with YAML front-matter.

### Schema (YAML front-matter)

```yaml
---
id: "uuid-v4"
type: "file | email | message | social | erp | audit"
source: "filesystem | gmail | whatsapp | odoo | ralph_wiggum"
priority: "low | medium | high | urgent"
status: "inbox | needs_action | planned | in_progress | pending_approval | approved | rejected | done | error"
requires_approval: true | false
classification: "local_only | syncable | redacted_summary"
created_at: "ISO-8601"
updated_at: "ISO-8601"
tags: ["optional", "list"]
---
```

### Body (markdown)

Free-form markdown content representing the original input (email
body, file content, message text, etc.).

### Validation Rules

- `id` MUST be unique across the entire vault.
- `type` MUST be one of the enumerated values.
- `status` MUST match the folder the file currently resides in.
- `created_at` MUST be set on creation, never modified.
- `updated_at` MUST be set on every modification.
- `classification` defaults to `local_only` if not specified.

---

## Entity: Plan

A structured breakdown of a Task Item into executable steps.

### Schema (YAML front-matter + structured body)

```yaml
---
id: "plan-uuid-v4"
item_id: "reference to parent Task Item id"
created_at: "ISO-8601"
updated_at: "ISO-8601"
status: "pending | in_progress | done | failed"
---
```

### Body (markdown)

```markdown
## Context

[Original request and AI's reasoning]

## Steps

### Step 1: [Description]
- **Status**: pending | in_progress | done | failed
- **Requires Approval**: true | false
- **Expected Outcome**: [What success looks like]

### Step 2: [Description]
- **Status**: pending
- **Requires Approval**: true
- **Expected Outcome**: [What success looks like]

[... more steps ...]
```

### Validation Rules

- `item_id` MUST reference an existing Task Item.
- Steps MUST be executed in order (no step N+1 before step N).
- If a step requires approval, execution pauses at that step.
- A failed step prevents subsequent dependent steps from executing.

---

## Entity: Approval Request

A Task Item routed to `/Pending_Approval`. Same schema as Task Item
with additional approval metadata.

### Additional Front-Matter Fields

```yaml
approval:
  proposed_action: "Description of what will happen if approved"
  reasoning: "AI's rationale for this action"
  original_context: "Summary of the triggering event"
  requested_at: "ISO-8601"
  expires_at: "ISO-8601 (requested_at + 24h)"
  decision: "pending | approved | rejected"
  decided_at: "ISO-8601 | null"
  feedback: "Human's feedback text | null"
```

### Validation Rules

- `expires_at` is `requested_at` + 24 hours.
- Expired approvals MUST be flagged but NEVER auto-approved.
- `decision` can only transition: `pending → approved` or
  `pending → rejected`.

---

## Entity: Audit Log Entry

A JSON object in the daily log file.

### Schema (JSON)

```json
{
  "timestamp": "ISO-8601 datetime",
  "actor": "skill name or watcher name",
  "action": "description of what was done",
  "item_id": "reference to the vault item | null",
  "from_state": "folder name | null",
  "to_state": "folder name | null",
  "outcome": "success | failure | retry | dry_run",
  "duration_ms": 0,
  "details": "additional context string",
  "approval": {
    "required": false,
    "status": "auto | pending | approved | rejected | n/a",
    "approver": "human | system | null"
  },
  "dry_run": false
}
```

### Validation Rules

- `timestamp` MUST be ISO-8601 with timezone.
- `actor` MUST be a registered skill or watcher name.
- `outcome` MUST be one of the enumerated values.
- `dry_run` MUST match the global DRY_RUN config at time of logging.
- Log entries are append-only; modification is prohibited.

---

## Entity: Watcher Configuration

A JSON or YAML file in `/Config` defining a monitored source.

### Schema (YAML)

```yaml
watcher:
  name: "gmail-inbox"
  type: "filesystem | gmail | whatsapp | odoo"
  enabled: true
  polling_interval_seconds: 60
  filters:
    # Type-specific filter criteria
    keywords: ["urgent", "invoice"]
    senders: ["boss@company.com"]
    labels: ["IMPORTANT"]
  credential_ref: "GMAIL_OAUTH_TOKEN_PATH"
  stability_delay_seconds: 2  # filesystem only
```

### Validation Rules

- `type` MUST be one of the enumerated values.
- `credential_ref` MUST be an environment variable name, never a
  raw credential.
- `polling_interval_seconds` MUST be >= 10.

---

## Entity: Agent Skill

A named, versioned AI capability. Definition stored in `/Skills`.

### Schema (YAML)

```yaml
skill:
  name: "triage"
  version: "1.0.0"
  description: "Classify and prioritize incoming items"
  can_trigger_approval: false
  input:
    - field: "item_path"
      type: "string"
      required: true
  output:
    - field: "priority"
      type: "enum(low, medium, high, urgent)"
    - field: "type"
      type: "enum(file, email, message, social, erp, audit)"
    - field: "requires_approval"
      type: "boolean"
  error_contract:
    retryable: true
    max_retries: 3
```

---

## Entity: Dashboard State

Generated markdown file at `/Dashboard.md`.

### Schema (markdown)

```markdown
# AI Employee Dashboard

**Last Updated**: ISO-8601
**Mode**: LIVE | [DRY_RUN MODE]

## Queue Summary

| Folder            | Count |
|-------------------|-------|
| Inbox             | 0     |
| Needs_Action      | 0     |
| Plans             | 0     |
| In_Progress       | 0     |
| Pending_Approval  | 0     |
| Approved          | 0     |
| Rejected          | 0     |
| Done              | 0     |
| Errors            | 0     |

## Recent Activity (last 10)

| Time | Actor | Action | Outcome |
|------|-------|--------|---------|
| ...  | ...   | ...    | ...     |

## Component Health

| Component | Status | Last Check |
|-----------|--------|------------|
| Filesystem Watcher | OK | ISO-8601 |
| ...                 | ...| ...      |

## Stale Approvals (> 24h)

[List or "None"]
```

---

## Entity: Sync Manifest (Platinum)

Tracks bidirectional vault sync state between cloud and local instances.

### Schema (JSON)

```json
{
  "manifest_id": "uuid-v4",
  "sync_direction": "cloud_to_local | local_to_cloud",
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601 | null",
  "status": "in_progress | success | partial | failed | conflict",
  "items_synced": 0,
  "items_skipped_local_only": 0,
  "items_redacted": 0,
  "conflicts": [
    {
      "item_id": "uuid-v4",
      "cloud_hash": "sha256",
      "local_hash": "sha256",
      "resolution": "pending | cloud_wins | local_wins | manual"
    }
  ],
  "last_successful_sync": "ISO-8601",
  "error": "string | null"
}
```

### Validation Rules

- `sync_direction` MUST be one of the enumerated values.
- `items_skipped_local_only` counts items excluded by classification.
- Conflicts MUST default to `resolution: "pending"` (never auto-resolve).
- `last_successful_sync` is updated only when `status` is `success`.

---

## Entity: Health Report (Platinum)

Periodic component health snapshot from the cloud instance.

### Schema (JSON)

```json
{
  "report_id": "uuid-v4",
  "timestamp": "ISO-8601",
  "uptime_seconds": 0,
  "uptime_percentage": 0.0,
  "sync_success_rate": 0.0,
  "items_processed": 0,
  "items_pending_approval": 0,
  "error_count": 0,
  "components": [
    {
      "name": "filesystem_watcher | gmail_watcher | odoo_watcher | email_mcp | odoo_mcp | social_mcp | sync_daemon",
      "status": "ok | degraded | down | recovering",
      "last_check": "ISO-8601",
      "restart_count": 0,
      "error": "string | null"
    }
  ],
  "last_successful_sync": "ISO-8601 | null",
  "alerts_sent": 0
}
```

### Validation Rules

- `uptime_percentage` = (`uptime_seconds` / expected_uptime) * 100.
- `components[].status` transitions: `ok → degraded → recovering → ok`
  or `ok → degraded → down`.
- `restart_count` resets to 0 after a successful health check.
- `alerts_sent` is cumulative for the reporting period.

---

## Entity: Credential Proxy Config (Platinum)

Configuration for the cloud credential proxy service.

### Schema (YAML)

```yaml
credential_proxy:
  listen: "unix:///var/run/ai-employee/cred-proxy.sock"
  allowed_callers:
    - "email_mcp"
    - "odoo_mcp"
    - "social_mcp"
  credentials:
    - name: "GMAIL_OAUTH_TOKEN_PATH"
      source: "env_encrypted"
    - name: "ODOO_API_KEY"
      source: "env_encrypted"
  log_access: true
  max_idle_timeout_seconds: 300
```

### Validation Rules

- `listen` MUST be a Unix socket or localhost-only TCP address.
- `allowed_callers` MUST list only registered MCP server names.
- `source` MUST be `env_encrypted` (raw plaintext prohibited on cloud).
- Access is logged to the audit trail (Principle VI).

---

## State Transition Diagram

```
                    ┌──────────┐
                    │  Inbox   │
                    └────┬─────┘
                         │ Triage
                    ┌────▼──────────┐
                    │ Needs_Action  │◄───────────────┐
                    └────┬──────────┘                │
                         │ AI Plans                  │ Manual Retry
                    ┌────▼─────┐                     │
                    │  Plans   │                     │
                    └────┬─────┘                     │
                         │ Execute              ┌────┴─────┐
                    ┌────▼──────────┐           │  Errors  │
                    │ In_Progress   ├──────────►│          │
                    └──┬─────┬──┘              └──────────┘
           Approval?   │     │ All Done
              YES      │     │
         ┌─────▼───────────┐ │        ┌──────┐
         │Pending_Approval │ └───────►│ Done │
         └──┬──────┬───────┘          └──────┘
            │      │
     Approve│      │Reject
    ┌───▼──────┐ ┌─▼────────┐
    │ Approved │ │ Rejected │
    └────┬─────┘ └──────────┘
         │ Resume
         └──► In_Progress
```
