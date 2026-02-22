# Skill Interface Contracts

**Date**: 2026-02-17

## Base Skill Interface

All skills implement this interface:

```
SkillInterface:
  name: string
  version: string (semver)
  execute(input: SkillInput) -> SkillOutput
  health_check() -> bool
```

```
SkillInput:
  item_path: string        # Path to the vault item
  config: dict             # Skill-specific config
  dry_run: bool            # Global DRY_RUN flag

SkillOutput:
  success: bool
  result: dict             # Skill-specific output
  actions_taken: list[str] # Description of each action
  error: string | null
```

---

## Bronze Skills

### Triage Skill

```
Input:
  item_path: string        # Path to file in /Inbox

Output:
  priority: "low" | "medium" | "high" | "urgent"
  type: "file" | "email" | "message" | "social" | "erp" | "audit"
  requires_approval: bool
  destination: "/Needs_Action"

Side Effects:
  - Updates item front-matter with priority, type, requires_approval
  - Moves item from /Inbox to /Needs_Action (unless DRY_RUN)
  - Writes audit log entry
```

### Planning Skill

```
Input:
  item_path: string        # Path to file in /Needs_Action

Output:
  plan_path: string        # Path to created Plan.md in /Plans
  step_count: int
  approval_required_steps: list[int]

Side Effects:
  - Creates Plan.md in /Plans
  - Writes audit log entry

Claude Prompt Contract:
  System: "You are a task planner. Decompose the following request
           into sequenced steps. For each step, indicate if it
           requires human approval based on the approval policy."
  Input: Item content + approval policy from Config/
  Output: Structured step list (parsed into Plan.md format)
```

### Executor Skill

```
Input:
  plan_path: string        # Path to Plan.md in /Plans

Output:
  completed_steps: int
  failed_step: int | null
  final_status: "done" | "failed" | "pending_approval"

Side Effects:
  - Moves item to /In_Progress during execution
  - Updates step statuses in Plan.md
  - Moves to /Pending_Approval if step requires approval
  - Moves to /Done on completion (unless DRY_RUN)
  - Moves to /Errors on failure after retries
  - Writes audit log entry per step
```

### Dashboard Skill

```
Input:
  vault_root: string       # Path to vault root

Output:
  folder_counts: dict[str, int]
  recent_activity: list[LogEntry]  # Last 10
  stale_approvals: list[str]       # Items > 24h in /Pending_Approval

Side Effects:
  - Writes /Dashboard.md (always, even in DRY_RUN)
```

---

## Silver Skills

### Email Drafter Skill

```
Input:
  item_path: string        # Path to email item in /Needs_Action

Output:
  draft_path: string       # Path to draft in /Pending_Approval
  draft_body: string       # The drafted reply text
  recipient: string
  subject: string

Side Effects:
  - Creates draft file in /Pending_Approval
  - Writes audit log entry

Claude Prompt Contract:
  System: "You are an email assistant. Draft a professional reply
           to the following email. Match the tone and formality of
           the original."
  Input: Email sender, subject, body, any prior thread context
  Output: Draft reply text
```

---

## Gold Skills

### CEO Briefing Skill

```
Input:
  period_days: int         # Default: 7
  log_dir: string          # Path to /Logs

Output:
  report_path: string      # /Reports/CEO_Briefing_YYYY-MM-DD.md
  metrics: dict            # tasks_completed, tasks_pending, errors, etc.

Side Effects:
  - Reads audit logs for the period
  - Queries Odoo MCP for financial summary (if connected)
  - Queries Social MCP for activity summary (if connected)
  - Writes report to /Reports
  - Writes audit log entry
```

### Accounting Audit Skill

```
Input:
  period: string           # e.g., "2026-02" (month)
  thresholds: dict         # unusual_amount, duplicate_window

Output:
  report_path: string      # /Reports/Accounting_Audit_YYYY-MM-DD.md
  anomalies_found: int
  flagged_items: list[dict]

Side Effects:
  - Reads entries via Odoo MCP server
  - Writes report to /Reports
  - Creates action items in /Needs_Action for flagged entries
  - Writes audit log entry
```

### Social Media Draft Skill

```
Input:
  item_path: string        # Item triggering the post
  platform: "linkedin" | "facebook" | "instagram" | "twitter"
  context: string          # What to post about

Output:
  draft_path: string       # Path in /Pending_Approval
  platform: string
  draft_text: string
  character_count: int

Side Effects:
  - ALWAYS routes to /Pending_Approval (never auto-posts)
  - Writes audit log entry
```

### Ralph Wiggum Self-Review Skill

```
Input:
  period_days: int         # Default: 7
  log_dir: string          # Path to /Logs

Output:
  review_path: string      # Log entry with [RALPH_WIGGUM] tag
  patterns_found: list[dict]
  improvement_items: list[str]  # New items in /Needs_Action

Side Effects:
  - Reads audit logs for the period
  - Identifies: failure patterns, rejected drafts, high-retry ops
  - Creates improvement items in /Needs_Action tagged [RALPH_WIGGUM]
  - NEVER self-approves its own proposals
  - Writes audit log entry with [RALPH_WIGGUM] tag
```

---

## Platinum Skills

### Data Classifier Skill

```
Input:
  item_path: string        # Path to any vault item

Output:
  classification: "local_only" | "syncable" | "redacted_summary"
  confidence: float        # 0.0-1.0
  matched_rules: list[str] # Which classification rules triggered
  sensitive_fields: list[str] # Fields that contain sensitive data

Side Effects:
  - Updates item front-matter with classification tag
  - Defaults to local_only if no rules match (fail-safe, FR-053)
  - Writes audit log entry

Classification Rules:
  local_only (default):
    - Contains credentials, API keys, tokens
    - Contains financial account numbers
    - Contains PII (SSN, passport, etc.)
    - Contains health records
    - User explicitly marked as sensitive
  syncable:
    - Task items with no sensitive content
    - Plans with no sensitive context
    - Dashboard state
    - Audit log entries (redacted)
  redacted_summary:
    - Email items (body redacted, metadata kept)
    - Financial reports (totals only, no account details)
    - Approval requests (action summary, no sensitive context)
```

### Health Monitor Skill

```
Input:
  config_path: string      # Path to Config/health_monitor.yaml

Output:
  report_path: string      # /Reports/Health_YYYY-MM-DD_HH.json
  all_healthy: bool
  components: list[dict]   # Per-component status
  alerts_triggered: int

Side Effects:
  - Polls each component (watchers, MCP servers, sync daemon)
  - Attempts auto-recovery for failed components:
    - Restart up to 3 times with exponential backoff
    - Log each restart attempt
  - Writes health report to /Reports
  - Alerts user within 5 minutes of unrecoverable failure (FR-059)
  - Writes audit log entry

Recovery Protocol:
  1. Detect component down (health check fails)
  2. Log failure with component name and error
  3. Restart attempt 1 (immediate)
  4. Restart attempt 2 (after 30s backoff)
  5. Restart attempt 3 (after 60s backoff)
  6. If still down: mark "down", alert user, continue with
     degraded functionality
```

### Sync Skill

```
Input:
  vault_root: string       # Path to vault root
  sync_config_path: string # Path to Config/sync.yaml
  direction: "push" | "pull" | "bidirectional"

Output:
  manifest_path: string    # Path to sync manifest JSON
  items_synced: int
  items_skipped: int       # local_only items excluded
  items_redacted: int      # redacted_summary items processed
  conflicts: list[dict]    # Items modified on both sides

Side Effects:
  - Reads classification tags on all items
  - Excludes local_only items from sync payload
  - Sends syncable items in full
  - Sends redacted_summary items with sensitive values masked
  - Detects conflicts (same item_id modified on both sides)
  - Keeps both versions on conflict, flags for human resolution
  - Writes sync manifest
  - Syncs cloud audit logs to local /Logs (FR-063)
  - Writes audit log entry

Sync Protocol:
  1. Authenticate both endpoints (FR-062)
  2. Exchange sync manifests (last sync timestamps)
  3. Compute delta (items changed since last sync)
  4. Filter by classification (exclude local_only)
  5. Detect conflicts (same item_id in both deltas)
  6. Transfer non-conflicting items
  7. Flag conflicting items for human resolution
  8. Update sync manifest on both sides
  9. Sync audit logs (cloud → local)
```
