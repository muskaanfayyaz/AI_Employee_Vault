# Tasks: AI Employee System

**Input**: Design documents from `/specs/001-ai-employee-system/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/skill-interfaces.md, contracts/mcp-interfaces.md, quickstart.md

**Tests**: Included — the user requested test cases per task.

**Organization**: Tasks are grouped by tier (Bronze = US1/P1, Silver = US2/P2, Gold = US3/P3, Platinum = US4/P4).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1=Bronze, US2=Silver, US3=Gold, US4=Platinum)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, packaging, environment config

- [x] T001 Create pyproject.toml with project metadata, Python 3.12 requirement, and dependency groups: core (watchdog, pyyaml, python-dotenv), silver (google-api-python-client, google-auth, schedule), gold (jinja2, tweepy, facebook-sdk), platinum (cryptography, paramiko, psutil), dev (pytest, pytest-mock)
  - **File**: `pyproject.toml`
  - **Command**: `pip install -e ".[dev]"`
  - **Expected**: Package installs successfully, `python -c "import src"` works
  - **Test**: `pip install -e ".[dev]" && python -c "import src"`

- [x] T002 Create .env.example with all configuration variables and DRY_RUN=true default
  - **File**: `.env.example`
  - **Expected**: Contains DRY_RUN=true, VAULT_ROOT, LOG_RETENTION_DAYS=90, and placeholder sections for Silver/Gold/Platinum credentials
  - **Test**: Verify no actual credentials present, DRY_RUN defaults to true

- [x] T003 [P] Create src/__init__.py and all subpackage __init__.py files per project structure
  - **Files**: `src/__init__.py`, `src/models/__init__.py`, `src/watchers/__init__.py`, `src/skills/__init__.py`, `src/mcp/__init__.py`, `src/engine/__init__.py`, `src/approval/__init__.py`
  - **Command**: `python -c "from src import models, watchers, skills, mcp, engine, approval"`
  - **Expected**: All subpackages importable
  - **Test**: Import succeeds without error

- [x] T004 [P] Create test fixtures directory and sample files
  - **Files**: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/fixtures/sample_inbox_item.md`, `tests/fixtures/sample_plan.md`, `tests/fixtures/sample_log.json`
  - **Expected**: sample_inbox_item.md has valid YAML front-matter (id, type, source, priority, status, created_at, updated_at), sample_plan.md has Plan structure, sample_log.json has FR-038 schema entry
  - **Test**: `python -c "import yaml; yaml.safe_load(open('tests/fixtures/sample_inbox_item.md').read().split('---')[1])"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that ALL tiers depend on. MUST complete before any user story.

- [x] T005 Implement src/config.py — load .env, expose DRY_RUN flag, vault paths, and credential_leak_check()
  - **File**: `src/config.py`
  - **Objective**: Load .env via python-dotenv, expose DRY_RUN (default True), VAULT_ROOT, LOG_RETENTION_DAYS. Include `credential_leak_check(content: str) -> bool` that scans text for any .env values and raises ValueError if found (FR-035).
  - **Expected**: `config.DRY_RUN` is True by default, `config.VAULT_ROOT` resolves to absolute path, `credential_leak_check()` catches leaked secrets
  - **Test**: `pytest tests/unit/test_config.py`

- [x] T006 Write tests/unit/test_config.py — config loading and credential leak detection
  - **File**: `tests/unit/test_config.py`
  - **Objective**: Test DRY_RUN default=True, DRY_RUN=false override, vault path resolution, credential_leak_check raises on leaked value, credential_leak_check passes on clean content
  - **Expected**: All tests pass
  - **Test**: `pytest tests/unit/test_config.py -v`

- [x] T007 Implement src/models/task_item.py — Task Item entity with YAML front-matter parse/write
  - **File**: `src/models/task_item.py`
  - **Objective**: Dataclass with fields from data-model.md (id, type, source, priority, status, requires_approval, classification, created_at, updated_at, tags). Methods: `from_file(path) -> TaskItem`, `to_file(path)`, `update_frontmatter(**fields)`. Validate enums for type, source, priority, status, classification.
  - **Expected**: Round-trip parse/write preserves front-matter and body content
  - **Test**: `pytest tests/unit/test_task_item.py`

- [x] T008 Write tests/unit/test_task_item.py — YAML front-matter parsing and validation
  - **File**: `tests/unit/test_task_item.py`
  - **Objective**: Test parse from fixture, write back and re-parse (round-trip), invalid type raises error, invalid status raises error, created_at immutable on update, updated_at changes on update, classification defaults to local_only
  - **Expected**: All tests pass
  - **Test**: `pytest tests/unit/test_task_item.py -v`

- [x] T009 Implement src/models/log_entry.py — Audit log entry dataclass matching FR-038 schema
  - **File**: `src/models/log_entry.py`
  - **Objective**: Dataclass with fields: timestamp (ISO-8601), actor, action, item_id, from_state, to_state, outcome (success|failure|retry|dry_run), duration_ms, details, approval (nested: required, status, approver), dry_run. Method: `to_dict() -> dict`, `validate() -> bool`.
  - **Expected**: Validates all enum fields, timestamp is ISO-8601 with timezone
  - **Test**: `pytest tests/unit/test_logger.py` (tested via logger tests)

- [x] T010 Implement src/engine/state_machine.py — vault folder state transitions with atomic moves
  - **File**: `src/engine/state_machine.py`
  - **Objective**: Encode FR-006 transition table. Method: `move(item_path, from_folder, to_folder, dry_run=False) -> str`. Validates transition is legal, performs `os.rename()` atomically, returns new path. Raises `InvalidTransitionError` for illegal moves. In DRY_RUN mode, logs but does not move.
  - **Expected**: Only valid transitions succeed, invalid transitions raise error, DRY_RUN skips actual move
  - **Test**: `pytest tests/unit/test_state_machine.py`

- [x] T011 Write tests/unit/test_state_machine.py — transition validation and DRY_RUN
  - **File**: `tests/unit/test_state_machine.py`
  - **Objective**: Test all 10 valid transitions from FR-006, test 5+ invalid transitions raise error, test DRY_RUN mode returns path but doesn't move file, test atomic move (file exists at destination, not at source)
  - **Expected**: All tests pass
  - **Test**: `pytest tests/unit/test_state_machine.py -v`

- [x] T012 Implement src/engine/logger.py — JSON audit log writer with redaction
  - **File**: `src/engine/logger.py`
  - **Objective**: `AuditLogger` class. Method: `log(entry: LogEntry)` — appends to `/Logs/YYYY-MM-DD.json`. Maintains JSON array format. Includes `redact(text: str) -> str` that masks emails (j***@example.com), amounts, PII. Validates entry schema before writing. Append-only (FR-039).
  - **Expected**: Log file is valid JSON array after multiple writes, redaction masks sensitive data
  - **Test**: `pytest tests/unit/test_logger.py`

- [x] T013 Write tests/unit/test_logger.py — log schema compliance and redaction
  - **File**: `tests/unit/test_logger.py`
  - **Objective**: Test log entry matches FR-038 schema, test append-only (multiple writes produce valid JSON array), test redact() masks email addresses, test redact() masks financial amounts, test DRY_RUN entries have correct prefix and flag
  - **Expected**: All tests pass
  - **Test**: `pytest tests/unit/test_logger.py -v`

- [x] T014 Implement src/models/plan.py — Plan entity with step parsing and status tracking
  - **File**: `src/models/plan.py`
  - **Objective**: Dataclass with YAML front-matter (id, item_id, created_at, updated_at, status) and structured body (context, steps). Each step: description, status, requires_approval, expected_outcome. Methods: `from_file(path)`, `to_file(path)`, `update_step(step_num, status)`, `next_pending_step() -> Step|None`.
  - **Expected**: Parse sample_plan.md fixture correctly, step updates persist
  - **Test**: Unit test validates parse/write round-trip

- [x] T015 Implement src/watchers/base.py — abstract watcher interface
  - **File**: `src/watchers/base.py`
  - **Objective**: Abstract base class `BaseWatcher` with methods: `start()`, `stop()`, `health_check() -> bool`, `on_event(event)`. Properties: `name`, `watcher_type`, `enabled`. Constructor takes config dict.
  - **Expected**: Cannot instantiate directly, subclasses must implement abstract methods
  - **Test**: Verify abstract instantiation raises TypeError

- [x] T016 Implement src/skills/base.py — abstract skill interface matching contracts
  - **File**: `src/skills/base.py`
  - **Objective**: Abstract base class `BaseSkill` with: `name`, `version` (semver), `execute(input: SkillInput) -> SkillOutput`, `health_check() -> bool`. Dataclasses: `SkillInput(item_path, config, dry_run)`, `SkillOutput(success, result, actions_taken, error)`.
  - **Expected**: Cannot instantiate directly, SkillInput/SkillOutput are importable dataclasses
  - **Test**: Verify abstract instantiation raises TypeError, dataclasses validate

- [x] T017 Create tests/conftest.py — shared fixtures for temp vault and mock skills
  - **File**: `tests/conftest.py`
  - **Objective**: Pytest fixtures: `temp_vault` (creates temporary directory with all vault folders from FR-001), `mock_skill` (returns a BaseSkill mock), `sample_task_item` (returns TaskItem parsed from fixture), `sample_log_entry` (returns LogEntry), `config_override` (sets DRY_RUN and VAULT_ROOT for test)
  - **Expected**: `temp_vault` fixture creates Inbox/, Needs_Action/, Plans/, In_Progress/, Pending_Approval/, Approved/, Rejected/, Done/, Errors/, Reports/, Logs/, Config/, Skills/ directories
  - **Test**: `pytest --collect-only` shows fixtures available

- [x] T018 Implement src/main.py — entry point with --init flag to create vault folder structure
  - **File**: `src/main.py`
  - **Objective**: CLI entry point. `--init` flag creates all vault folders from FR-001 and writes empty Dashboard.md. Without flags, starts the main processing loop (stubbed for now — actual watcher integration in Bronze tasks). Loads config, initializes logger.
  - **Command**: `python -m src.main --init`
  - **Expected**: All 13 vault folders created, Dashboard.md exists
  - **Test**: Run `--init` in temp directory, verify all folders exist

**Checkpoint**: Foundation ready — all models, state machine, logger, config, and base classes operational. User story implementation can begin.

---

## Phase 3: Bronze — Local File Processing Loop (Priority: P1) MVP

**Goal**: Drop a file in Inbox/, have it triaged, planned, executed, and moved to Done/ with full audit logging and dashboard — all locally with zero external APIs.

**Independent Test**: `cp tests/fixtures/sample_inbox_item.md Inbox/` → verify item reaches Done/ within 5 minutes, logs written, dashboard updated.

### Tests for Bronze

- [x] T019 [P] [US1] Write tests/integration/test_bronze_e2e.py — full Inbox→Done flow
  - **File**: `tests/integration/test_bronze_e2e.py`
  - **Objective**: Test file drop in Inbox/ → triage → Needs_Action/ → plan → Plans/ → execute → Done/. Test log entries written for each transition. Test Dashboard.md updated. Test DRY_RUN mode: no files move.
  - **Expected**: Tests defined but FAIL until implementation complete
  - **Test**: `pytest tests/integration/test_bronze_e2e.py -v` (expect failures)

### Implementation for Bronze

- [x] T020 [US1] Implement src/watchers/filesystem.py — watchdog-based /Inbox monitor
  - **File**: `src/watchers/filesystem.py`
  - **Objective**: Extends BaseWatcher. Uses `watchdog` to monitor Inbox/ for new .md files. Implements file stability check (no modifications for 2s configurable). On stable file detected, calls `on_event()` which creates a TaskItem and logs the detection. Handles DRY_RUN.
  - **Expected**: Detects new file within 30s, waits for stability, calls on_event
  - **Test**: Create temp file in watched dir, verify on_event called after stability delay

- [x] T021 [US1] Implement src/skills/triage.py — item classification and priority assignment
  - **File**: `src/skills/triage.py`
  - **Objective**: Extends BaseSkill. Reads item content, classifies type (file|email|message|social|erp|audit) and priority (low|medium|high|urgent) based on content keywords and metadata. Sets `requires_approval` flag based on approval policy. Updates item front-matter. Moves item to Needs_Action/ via state_machine (unless DRY_RUN).
  - **Expected**: Item front-matter updated with type, priority, requires_approval; item moved to Needs_Action/
  - **Test**: Pass sample_inbox_item, verify classification fields set and file in Needs_Action/

- [x] T022 [US1] Implement src/skills/planner.py — Plan.md creation from item
  - **File**: `src/skills/planner.py`
  - **Objective**: Extends BaseSkill. Reads item from Needs_Action/, uses Claude to decompose into steps, writes Plan.md to Plans/ with step list. Each step has: description, expected_outcome, requires_approval (based on approval policy), status=pending. Logs the plan creation.
  - **Expected**: Plan.md in Plans/ with valid front-matter and step list
  - **Test**: Pass sample item, verify Plan.md created with at least 1 step

- [x] T023 [US1] Implement src/skills/executor.py — plan step execution
  - **File**: `src/skills/executor.py`
  - **Objective**: Extends BaseSkill. Reads Plan from Plans/, moves item to In_Progress/, executes steps sequentially. Updates step status (pending→in_progress→done|failed). If step requires approval, moves item to Pending_Approval/ and pauses. On all steps done, moves to Done/. On failure after retries, moves to Errors/. Logs each step.
  - **Expected**: Steps execute in order, statuses update, item ends in Done/ or Errors/
  - **Test**: Execute plan with 3 steps, verify all marked done, item in Done/

- [x] T024 [US1] Implement src/skills/dashboard.py — Dashboard.md generation
  - **File**: `src/skills/dashboard.py`
  - **Objective**: Extends BaseSkill. Counts files per vault folder, reads last 10 log entries, identifies stale approvals (>24h in Pending_Approval/), checks component health. Writes Dashboard.md matching data-model.md schema. Shows DRY_RUN banner if active.
  - **Expected**: Dashboard.md with accurate folder counts, recent activity table, component health, stale approvals
  - **Test**: Create items in various folders, run dashboard, verify counts match

- [x] T025 [US1] Integrate Bronze components in src/main.py — watcher→triage→plan→execute→dashboard loop
  - **File**: `src/main.py`
  - **Objective**: Wire up the processing loop: filesystem watcher detects file → triage skill classifies → planner skill creates plan → executor skill runs plan → dashboard skill regenerates. Add signal handling (SIGINT/SIGTERM for graceful shutdown). Add `--init` vault creation. Log startup/shutdown events.
  - **Command**: `python -m src.main`
  - **Expected**: Full loop runs, file dropped in Inbox/ flows to Done/
  - **Test**: Run with DRY_RUN=true, drop file, verify log entries for each stage

- [x] T026 [US1] Run Bronze E2E test and verify quickstart checklist
  - **Objective**: Execute the Bronze demo scenario from quickstart.md. Verify all 6 Bronze checklist items pass.
  - **Command**: `python -m src.main --init && python -m src.main &` then `cp tests/fixtures/sample_inbox_item.md Inbox/`
  - **Expected**: Item detected, triaged, planned, executed, in Done/. Logs written. Dashboard updated. DRY_RUN mode works.
  - **Test**: All 6 Bronze verification checklist items pass

**Checkpoint**: Bronze tier complete — local file processing loop fully functional. MVP validated.

---

## Phase 4: Silver — Email, Messaging, and Scheduling (Priority: P2)

**Goal**: Monitor Gmail/WhatsApp, draft email replies, require human approval for outbound messages, run on cron schedule with retry logic.

**Independent Test**: Send test email → watcher detects → AI drafts reply → routes to Pending_Approval/ → approve → email sent via MCP → item in Done/ → full audit trail.

### Tests for Silver

- [x] T027 [P] [US2] Write tests/unit/test_retry.py — exponential backoff logic
  - **File**: `tests/unit/test_retry.py`
  - **Objective**: Test @with_retry decorator: success on first try, success on retry 2, failure after max retries (3), verify delays are 2s→4s→8s, verify item moves to Errors/ on exhaustion
  - **Expected**: Tests pass
  - **Test**: `pytest tests/unit/test_retry.py -v`

- [x] T028 [P] [US2] Write tests/integration/test_silver_email.py — email E2E flow
  - **File**: `tests/integration/test_silver_email.py`
  - **Objective**: Test email arrival → watcher creates item → triage → draft → Pending_Approval/ → approve → send via MCP → Done/. Test rejection → Rejected/, no send. Test stale approval flagged. Mock Gmail API and MCP server.
  - **Expected**: Tests defined, FAIL until implementation complete
  - **Test**: `pytest tests/integration/test_silver_email.py -v`

### Implementation for Silver

- [x] T029 [US2] Implement src/engine/retry.py — @with_retry decorator with exponential backoff
  - **File**: `src/engine/retry.py`
  - **Objective**: Decorator `@with_retry(base_delay=2, max_retries=3, multiplier=2)`. Catches exceptions, retries with exponential backoff. Logs each retry attempt. On exhaustion, raises `RetriesExhaustedError` with full context (error type, message, retry count, timestamps).
  - **Expected**: Retries 3 times with 2s, 4s, 8s delays before raising
  - **Test**: `pytest tests/unit/test_retry.py -v`

- [x] T030 [US2] Implement src/models/approval.py — approval request model
  - **File**: `src/models/approval.py`
  - **Objective**: Dataclass extending TaskItem front-matter with approval fields from data-model.md: proposed_action, reasoning, original_context, requested_at, expires_at (requested_at + 24h), decision (pending|approved|rejected), decided_at, feedback. Methods: `is_expired() -> bool`, `approve(feedback)`, `reject(feedback)`.
  - **Expected**: Approval fields serialize to/from YAML front-matter, expiry calculation correct
  - **Test**: Create approval, verify expires_at = requested_at + 24h

- [x] T031 [US2] Implement src/approval/manager.py — human-in-the-loop approval workflow
  - **File**: `src/approval/manager.py`
  - **Objective**: `ApprovalManager` class. Method: `request_approval(item, proposed_action, reasoning) -> ApprovalRequest` — creates approval file in Pending_Approval/. Method: `check_approvals()` — scans Pending_Approval/ for decisions (approved/rejected files), moves approved to Approved/, rejected to Rejected/. Method: `get_stale_approvals() -> list` — items >24h old.
  - **Expected**: Items route to Pending_Approval/, decisions detected, stale items flagged
  - **Test**: Create approval, mark approved, verify move to Approved/

- [x] T032 [P] [US2] Create Config/approval_policy.yaml — define what requires approval
  - **File**: `Config/approval_policy.yaml`
  - **Objective**: YAML config listing actions requiring approval (per FR-017): send_email, send_message, social_post, payment, delete_data, add_contact, odoo_write. List auto-approved actions (per FR-018): read_file, create_plan, generate_report, write_log, update_dashboard, odoo_read.
  - **Expected**: Valid YAML, all FR-017 actions listed as requiring approval
  - **Test**: `python -c "import yaml; yaml.safe_load(open('Config/approval_policy.yaml'))"`

- [x] T033 [US2] Implement src/mcp/base.py — abstract MCP server interface with health check
  - **File**: `src/mcp/base.py`
  - **Objective**: Abstract base class `BaseMCPServer`. Methods: `ping() -> dict` (health check returning {status, server, version}), abstract tool methods. Properties: `name`, `version`, `transport` (stdio). Constructor validates credential refs are env var names (never raw values).
  - **Expected**: ping() returns standard health response, subclasses must implement tools
  - **Test**: Verify abstract instantiation raises TypeError, ping() format correct

- [x] T034 [US2] Implement src/mcp/email_server.py — Gmail MCP server with send/search/read
  - **File**: `src/mcp/email_server.py`
  - **Objective**: Extends BaseMCPServer. Tools: `send_email(to, subject, body, cc, bcc, reply_to_message_id)`, `search_emails(query, max_results)`, `get_email(message_id)`, `mark_read(message_id)`. Uses `google-api-python-client` with OAuth2 from GMAIL_OAUTH_TOKEN_PATH env ref. send_email requires approval (FR-017). All tools wrapped in @with_retry.
  - **Expected**: Tools match mcp-interfaces.md contract, send_email has approval gate
  - **Test**: Mock Gmail API, verify send_email returns message_id, search returns list

- [x] T034b [US2] Implement mcp-servers/email/ — Node.js Gmail MCP server (TypeScript, stdio)
  - **Files**: `mcp-servers/email/src/{types,gmail,tools,index}.ts`, `tests/tools.test.ts`, `package.json`, `tsconfig.json`
  - **Objective**: Node.js TypeScript MCP server (stdio) with tools: `send_email`, `draft_email`, `search_email`, `ping`. DRY_RUN env var short-circuits all writes. Structured JSON response: `{success, dry_run, data, error}`. Injectable GmailClientInterface for testability. Zod input validation.
  - **Expected**: Tools match mcp-interfaces.md contract. 26/26 unit tests pass. `npm run build` clean.
  - **Test**: `cd mcp-servers/email && npm test` → 26 passed

- [x] T035 [US2] Implement src/watchers/gmail.py — Gmail API polling watcher
  - **File**: `src/watchers/gmail.py`
  - **Objective**: Extends BaseWatcher. Polls Gmail inbox at configurable interval (from Config/gmail_watcher.yaml). Filters by keywords, senders, labels. Creates TaskItem in Inbox/ with type=email, source=gmail. Deduplicates by message_id. Marks processed emails as read via MCP.
  - **Expected**: Detects matching emails, creates action items, no duplicates
  - **Test**: Mock Gmail API with 3 emails (2 matching filter, 1 not), verify 2 items created

- [x] T036 [P] [US2] Create Config/gmail_watcher.yaml — Gmail watcher configuration
  - **File**: `Config/gmail_watcher.yaml`
  - **Objective**: YAML config matching data-model.md Watcher Configuration schema: name, type=gmail, enabled=true, polling_interval_seconds=60, filters (keywords, senders, labels), credential_ref=GMAIL_OAUTH_TOKEN_PATH.
  - **Expected**: Valid YAML matching watcher schema, interval >= 10s
  - **Test**: `python -c "import yaml; c=yaml.safe_load(open('Config/gmail_watcher.yaml')); assert c['watcher']['polling_interval_seconds'] >= 10"`

- [x] T037 [US2] Implement src/watchers/whatsapp.py — WhatsApp message watcher
  - **File**: `src/watchers/whatsapp.py`
  - **Objective**: Extends BaseWatcher. Monitors configured contacts/groups via WhatsApp Business API. Creates TaskItem in Inbox/ with type=message, source=whatsapp. Polls at configurable interval.
  - **Expected**: Detects messages, creates items with whatsapp channel identifier
  - **Test**: Mock WhatsApp API, verify item creation with correct metadata

- [x] T038 [P] [US2] Create Config/whatsapp_watcher.yaml — WhatsApp watcher configuration
  - **File**: `Config/whatsapp_watcher.yaml`
  - **Objective**: YAML config: name, type=whatsapp, enabled=true, polling_interval_seconds=30, filters (contacts, groups), credential_ref=WHATSAPP_API_TOKEN.
  - **Expected**: Valid YAML matching watcher schema
  - **Test**: Parse and validate YAML

- [x] T039 [US2] Implement src/skills/email_drafter.py — email response drafting skill
  - **File**: `src/skills/email_drafter.py`
  - **Objective**: Extends BaseSkill. Reads email item from Needs_Action/, uses Claude to draft contextual reply (matching tone/formality of original). Creates draft file in Pending_Approval/ with: recipient, subject, draft body, original thread context. Always routes to approval (FR-017).
  - **Expected**: Draft in Pending_Approval/ with email metadata and reply body
  - **Test**: Pass email item, verify draft created with recipient, subject, body

- [x] T040 [US2] Implement src/engine/scheduler.py — cron-based orchestrator
  - **File**: `src/engine/scheduler.py`
  - **Objective**: Uses `schedule` library. Configurable intervals for: watcher polling, processing cycle, dashboard regeneration. Method: `start()` runs scheduler in loop, `stop()` for graceful shutdown. Integrates with main.py via `--schedule` flag.
  - **Expected**: Tasks trigger at configured intervals, graceful shutdown on SIGINT
  - **Test**: Configure 1-second interval, verify callback fires within 2 seconds

- [x] T041 [US2] Integrate Silver components in src/main.py — add --schedule flag, watchers, approval loop
  - **File**: `src/main.py`
  - **Objective**: Add `--schedule` CLI flag. When set: start Gmail/WhatsApp watchers alongside filesystem watcher, run scheduler, check approvals each cycle. Wire email drafter skill into processing pipeline. Add MCP server startup/shutdown.
  - **Command**: `python -m src.main --schedule`
  - **Expected**: All watchers running, scheduler active, approvals checked each cycle
  - **Test**: Start with --schedule, verify scheduler logs show periodic execution

- [x] T042 [US2] Run Silver E2E test and verify quickstart checklist
  - **Objective**: Execute Silver demo scenario from quickstart.md. Verify all 6 Silver checklist items pass.
  - **Expected**: Gmail watcher detects email, draft in Pending_Approval/, approve sends, reject does not send, scheduler runs
  - **Test**: All 6 Silver verification checklist items pass

**Checkpoint**: Silver tier complete — email, messaging, scheduling, approval, and retry all functional.

---

## Phase 5: Gold — Business Integration and Autonomous Loop (Priority: P3)

**Goal**: Integrate Odoo ERP, social media, CEO Briefing, accounting audit, and Ralph Wiggum self-improvement loop with multi-MCP orchestration.

**Independent Test**: Create Odoo sales order → watcher detects → social post drafted → approved → CEO Briefing includes activity → Ralph Wiggum reviews logs and proposes improvement.

### Tests for Gold

- [ ] T043 [P] [US3] Write tests/integration/test_gold_briefing.py — CEO Briefing E2E
  - **File**: `tests/integration/test_gold_briefing.py`
  - **Objective**: Test 7-day log aggregation, test report includes all required sections (tasks, errors, approvals, financial, social), test report written to Reports/. Mock Odoo and Social MCP data.
  - **Expected**: Tests defined
  - **Test**: `pytest tests/integration/test_gold_briefing.py -v`

- [ ] T044 [P] [US3] Write tests/integration/test_gold_ralph.py — Ralph Wiggum loop E2E
  - **File**: `tests/integration/test_gold_ralph.py`
  - **Objective**: Test failure pattern detection from logs, test improvement items created in Needs_Action/ with [RALPH_WIGGUM] tag, test proposals do NOT self-approve
  - **Expected**: Tests defined
  - **Test**: `pytest tests/integration/test_gold_ralph.py -v`

### Implementation for Gold

- [ ] T045 [US3] Implement src/mcp/odoo_server.py — Odoo JSON-RPC MCP server
  - **File**: `src/mcp/odoo_server.py`
  - **Objective**: Extends BaseMCPServer. Tools: `search_records(model, domain, fields, limit)`, `read_record(model, record_id, fields)`, `create_record(model, values)`, `update_record(model, record_id, values)`. Uses xmlrpc.client (stdlib). Creds from ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY env refs. Write operations require approval (FR-017).
  - **Expected**: Tools match mcp-interfaces.md contract, reads auto-approved, writes need approval
  - **Test**: Mock xmlrpc, verify search returns records, create returns ID

- [ ] T046 [US3] Implement src/watchers/odoo.py — Odoo JSON-RPC polling watcher
  - **File**: `src/watchers/odoo.py`
  - **Objective**: Extends BaseWatcher. Polls Odoo for new sales orders, invoices, contacts via Odoo MCP search_records. Configurable interval and record types via Config/odoo_watcher.yaml. Creates TaskItem with type=erp, source=odoo, including record_type and record_id in body.
  - **Expected**: Detects new Odoo records, creates items with correct metadata
  - **Test**: Mock Odoo MCP, create test records, verify items created

- [ ] T047 [P] [US3] Create Config/odoo_watcher.yaml — Odoo watcher configuration
  - **File**: `Config/odoo_watcher.yaml`
  - **Objective**: YAML config: name=odoo-watcher, type=odoo, enabled=true, polling_interval_seconds=120, models to watch (sale.order, account.move, res.partner), credential_refs (ODOO_URL, ODOO_DB, etc.)
  - **Expected**: Valid YAML matching watcher schema
  - **Test**: Parse and validate YAML

- [ ] T048 [US3] Implement src/mcp/social_server.py — Social Media MCP server
  - **File**: `src/mcp/social_server.py`
  - **Objective**: Extends BaseMCPServer. Tools: `draft_post(platform, text, media_url)`, `publish_post(platform, draft_id)`, `get_mentions(platform, since)`, `get_analytics(platform, period_days)`. Adapter pattern: LinkedIn, Facebook, Instagram, Twitter via platform-specific API clients. All post/publish require approval. Creds from platform-specific env refs.
  - **Expected**: Tools match mcp-interfaces.md contract, draft/publish require approval
  - **Test**: Mock platform APIs, verify draft returns character count, publish returns post_url

- [ ] T049 [P] [US3] Create Config/social_media.yaml — social media platform configs
  - **File**: `Config/social_media.yaml`
  - **Objective**: YAML config with platform entries (linkedin, facebook, instagram, twitter), each with: enabled flag, character_limit, credential_ref, default_hashtags.
  - **Expected**: Valid YAML with all 4 platforms configured
  - **Test**: Parse and validate YAML

- [ ] T050 [US3] Implement src/skills/social_media.py — social media draft skill
  - **File**: `src/skills/social_media.py`
  - **Objective**: Extends BaseSkill. Drafts platform-appropriate posts using Claude. Checks character limits per platform. ALWAYS routes to Pending_Approval/ (never auto-posts, FR-017). Creates draft file with platform, text, character_count, within_limit.
  - **Expected**: Draft in Pending_Approval/ with platform metadata, never auto-sends
  - **Test**: Draft a LinkedIn post, verify in Pending_Approval/, verify char count correct

- [ ] T051 [P] [US3] Create templates/ceo_briefing.md.j2 — Jinja2 briefing template
  - **File**: `templates/ceo_briefing.md.j2`
  - **Objective**: Jinja2 template for CEO Briefing report. Sections: Period, Tasks Summary (completed/pending counts and list), Error Summary, Approval Summary (approved/rejected ratio), Financial Activity (if Odoo connected), Social Media Activity (if connected), Recommendations.
  - **Expected**: Valid Jinja2 with all required sections from FR-031
  - **Test**: Render with sample data, verify all sections present

- [ ] T052 [P] [US3] Create templates/audit_report.md.j2 — Jinja2 accounting audit template
  - **File**: `templates/audit_report.md.j2`
  - **Objective**: Jinja2 template for accounting audit. Sections: Period, Summary, Anomalies Found (count and list), Duplicates, Unusual Amounts, Missing References, Recommendations.
  - **Expected**: Valid Jinja2 with all required sections from FR-032
  - **Test**: Render with sample data, verify all sections present

- [ ] T053 [US3] Implement src/skills/ceo_briefing.py — weekly CEO Briefing generator
  - **File**: `src/skills/ceo_briefing.py`
  - **Objective**: Extends BaseSkill. Aggregates audit logs for period_days (default 7). Queries Odoo MCP for financial summary (if connected). Queries Social MCP for activity summary (if connected). Renders ceo_briefing.md.j2 template. Writes to Reports/CEO_Briefing_YYYY-MM-DD.md.
  - **Expected**: Report in Reports/ with accurate data from logs and MCP queries
  - **Test**: Create 7 days of sample logs, run skill, verify report has correct counts

- [ ] T054 [US3] Implement src/skills/accounting.py — accounting audit skill
  - **File**: `src/skills/accounting.py`
  - **Objective**: Extends BaseSkill. Reads Odoo accounting entries via MCP for specified period. Checks for: duplicate entries (same amount/date/partner), unusual amounts (configurable threshold), missing references, unbalanced transactions. Renders audit_report.md.j2. Writes to Reports/. Creates action items in Needs_Action/ for flagged entries.
  - **Expected**: Audit report in Reports/, flagged items in Needs_Action/
  - **Test**: Mock Odoo with duplicate entry, verify it's detected and flagged

- [ ] T055 [P] [US3] Create Config/ceo_briefing.yaml — briefing schedule and options
  - **File**: `Config/ceo_briefing.yaml`
  - **Objective**: YAML config: schedule (day=monday, time=08:00), period_days=7, include_financial=true, include_social=true.
  - **Expected**: Valid YAML
  - **Test**: Parse and validate YAML

- [ ] T056 [US3] Implement src/skills/ralph_wiggum.py — self-review loop skill
  - **File**: `src/skills/ralph_wiggum.py`
  - **Objective**: Extends BaseSkill. Reviews audit logs for period_days (default 7). Identifies: failure patterns (>2 failures on same operation), rejected drafts (patterns in rejections), high-retry operations (>1 retry average), slow processing (>5min). Creates improvement items in Needs_Action/ tagged [RALPH_WIGGUM]. Logs with [RALPH_WIGGUM] tag. NEVER self-approves (FR-030).
  - **Expected**: Improvement items in Needs_Action/ with tag, self-review logged, no self-approval
  - **Test**: Create logs with repeated failures, verify pattern detected and item created

- [ ] T057 [P] [US3] Create Config/ralph_wiggum.yaml — self-review schedule and criteria
  - **File**: `Config/ralph_wiggum.yaml`
  - **Objective**: YAML config: schedule (day=friday, time=17:00), period_days=7, thresholds (failure_count=2, retry_avg=1, slow_processing_minutes=5), max_improvement_items=5.
  - **Expected**: Valid YAML
  - **Test**: Parse and validate YAML

- [ ] T058 [US3] Implement src/engine/orchestrator.py — multi-MCP coordinator
  - **File**: `src/engine/orchestrator.py`
  - **Objective**: `MCPOrchestrator` class. Manages multiple MCP server instances. Method: `execute_multi(tasks: list[MCPTask]) -> list[MCPResult]` — sequences MCP calls, handles partial failure (one succeeds, one fails), logs combined outcome. Does NOT silently drop successful results on partial failure (FR-026).
  - **Expected**: Partial failures logged with both success and failure results preserved
  - **Test**: Mock 2 MCP calls (1 success, 1 fail), verify both results returned

- [ ] T059 [US3] Integrate Gold components in src/main.py — add --gold flag, Odoo/social watchers, scheduled reports
  - **File**: `src/main.py`
  - **Objective**: Add `--gold` CLI flag. When set: start Odoo watcher, wire social media skill, schedule CEO Briefing and Ralph Wiggum loop per config. Add `--briefing` flag to trigger CEO Briefing manually. Add `--ralph-wiggum` flag to trigger self-review manually. Wire orchestrator for multi-MCP tasks.
  - **Command**: `python -m src.main --schedule --gold`
  - **Expected**: All Gold features active alongside Bronze/Silver
  - **Test**: Start with --gold, verify Odoo watcher logs, briefing schedule set

- [ ] T060 [US3] Run Gold E2E test and verify quickstart checklist
  - **Objective**: Execute Gold demo scenario from quickstart.md. Verify all 5 Gold checklist items pass.
  - **Expected**: Odoo watcher detects record, social draft routes to approval, CEO Briefing generates, Ralph Wiggum creates proposals, multi-MCP handles partial failure
  - **Test**: All 5 Gold verification checklist items pass

**Checkpoint**: Gold tier complete — full business integration, reporting, and self-improvement loop operational.

---

## Phase 6: Platinum — Always-On Cloud + Local Executive (Priority: P4)

**Goal**: Deploy to cloud 24/7, sync vault bidirectionally with local, classify data sensitivity, monitor health, enable zero-downtime deployments.

**Independent Test**: Deploy cloud instance → take local offline → cloud processes event → bring local online → sync within 5 minutes → approve locally → cloud executes → no local_only data leaked.

### Tests for Platinum

- [ ] T061 [P] [US4] Write tests/unit/test_data_classifier.py — classification rule tests
  - **File**: `tests/unit/test_data_classifier.py`
  - **Objective**: Test credentials tagged local_only, test financials tagged local_only, test PII tagged local_only, test operational data tagged syncable, test unrecognized items default to local_only (fail-safe), test user-marked sensitive items tagged local_only
  - **Expected**: Tests pass
  - **Test**: `pytest tests/unit/test_data_classifier.py -v`

- [ ] T062 [P] [US4] Write tests/unit/test_sync_manifest.py — sync manifest model tests
  - **File**: `tests/unit/test_sync_manifest.py`
  - **Objective**: Test manifest creation, test conflict detection fields, test status transitions, test items_skipped_local_only counter, test last_successful_sync only updates on success
  - **Expected**: Tests pass
  - **Test**: `pytest tests/unit/test_sync_manifest.py -v`

- [ ] T063 [P] [US4] Write tests/unit/test_health_monitor.py — health check and recovery tests
  - **File**: `tests/unit/test_health_monitor.py`
  - **Objective**: Test component health check polling, test auto-recovery restart (up to 3x), test backoff delays (immediate, 30s, 60s), test alert after 3 failed recoveries, test health report generation with all required fields
  - **Expected**: Tests pass
  - **Test**: `pytest tests/unit/test_health_monitor.py -v`

- [ ] T064 [P] [US4] Write tests/unit/test_credential_proxy.py — proxy auth and redaction tests
  - **File**: `tests/unit/test_credential_proxy.py`
  - **Objective**: Test proxy responds to allowed callers only, test proxy returns credential by reference name, test proxy rejects unknown callers, test no raw credentials stored on disk after startup, test access logging
  - **Expected**: Tests pass
  - **Test**: `pytest tests/unit/test_credential_proxy.py -v`

- [ ] T065 [P] [US4] Write tests/integration/test_platinum_sync.py — end-to-end sync flow
  - **File**: `tests/integration/test_platinum_sync.py`
  - **Objective**: Test sync excludes local_only items, test sync transmits syncable items in full, test sync sends redacted_summary with masked values, test conflict detection (dual-modified item), test sync resumes after interruption, test cloud audit logs sync to local
  - **Expected**: Tests defined
  - **Test**: `pytest tests/integration/test_platinum_sync.py -v`

- [ ] T066 [P] [US4] Write tests/integration/test_platinum_health.py — health monitoring E2E
  - **File**: `tests/integration/test_platinum_health.py`
  - **Objective**: Test health monitor detects simulated watcher crash, test auto-recovery restarts component, test alert after unrecoverable failure, test health report written to Reports/
  - **Expected**: Tests defined
  - **Test**: `pytest tests/integration/test_platinum_health.py -v`

- [ ] T067 [P] [US4] Write tests/integration/test_platinum_deploy.py — zero-downtime deploy test
  - **File**: `tests/integration/test_platinum_deploy.py`
  - **Objective**: Test deployment manager runs blue-green swap, test no items lost during transition, test no approvals dropped, test transition logged
  - **Expected**: Tests defined
  - **Test**: `pytest tests/integration/test_platinum_deploy.py -v`

### Implementation for Platinum

- [ ] T068 [US4] Implement src/models/sync_manifest.py — sync manifest entity
  - **File**: `src/models/sync_manifest.py`
  - **Objective**: Dataclass matching data-model.md Sync Manifest schema: manifest_id, sync_direction, started_at, completed_at, status, items_synced, items_skipped_local_only, items_redacted, conflicts (list with item_id, cloud_hash, local_hash, resolution), last_successful_sync, error. Methods: `to_json()`, `from_json()`, `add_conflict()`, `mark_complete()`.
  - **Expected**: Serialize/deserialize JSON, conflict resolution defaults to pending
  - **Test**: `pytest tests/unit/test_sync_manifest.py -v`

- [ ] T069 [US4] Implement src/models/health_report.py — health report entity
  - **File**: `src/models/health_report.py`
  - **Objective**: Dataclass matching data-model.md Health Report schema: report_id, timestamp, uptime_seconds, uptime_percentage, sync_success_rate, items_processed, items_pending_approval, error_count, components (list with name, status, last_check, restart_count, error), last_successful_sync, alerts_sent. Methods: `to_json()`, `from_json()`.
  - **Expected**: Serialize/deserialize JSON, uptime_percentage calculated correctly
  - **Test**: `pytest tests/unit/test_health_monitor.py -v`

- [ ] T070 [US4] Implement src/skills/data_classifier.py — item sensitivity classification
  - **File**: `src/skills/data_classifier.py`
  - **Objective**: Extends BaseSkill. Reads item content, assigns classification tag (local_only, syncable, redacted_summary) based on rules from Config/data_classification_rules.yaml. Pattern matching for: credentials/API keys, financial account numbers, PII (SSN, passport), health records. Default: local_only (fail-safe, FR-053). Updates item front-matter with classification tag.
  - **Expected**: Items classified correctly, unknown items default to local_only
  - **Test**: `pytest tests/unit/test_data_classifier.py -v`

- [ ] T071 [P] [US4] Create Config/data_classification_rules.yaml — classification keyword rules
  - **File**: `Config/data_classification_rules.yaml`
  - **Objective**: YAML config with rules: local_only patterns (password, api_key, ssn, passport, account_number, etc.), syncable patterns (task items without sensitive content, plans, dashboards), redacted_summary patterns (emails, financial reports). Default classification: local_only.
  - **Expected**: Valid YAML with comprehensive classification rules
  - **Test**: Parse and validate YAML

- [ ] T072 [US4] Implement src/skills/health_monitor.py — component health polling and recovery
  - **File**: `src/skills/health_monitor.py`
  - **Objective**: Extends BaseSkill. Polls all registered components (watchers, MCP servers, sync daemon) via health_check(). Recovery protocol: detect down → restart attempt 1 (immediate) → attempt 2 (30s) → attempt 3 (60s) → mark down + alert. Generates Health Report JSON to Reports/. Alerts user within 5 minutes via configured channel (FR-059).
  - **Expected**: Failed components detected, auto-recovery attempted, alerts sent, report generated
  - **Test**: `pytest tests/unit/test_health_monitor.py -v`

- [ ] T073 [P] [US4] Create Config/health_monitor.yaml — health check intervals and thresholds
  - **File**: `Config/health_monitor.yaml`
  - **Objective**: YAML config: check_interval_seconds=60, alert_channel=email, alert_recipient, auto_recovery_max_attempts=3, report_interval=hourly, component list with individual thresholds.
  - **Expected**: Valid YAML
  - **Test**: Parse and validate YAML

- [ ] T074 [US4] Implement src/engine/credential_proxy.py — secure credential proxy for cloud
  - **File**: `src/engine/credential_proxy.py`
  - **Objective**: `CredentialProxy` class. Listens on Unix socket (or localhost TCP). Loads credentials from encrypted .env.cloud at startup (in memory only, no disk persistence). Method: `get_credential(caller_name, credential_ref) -> str` — validates caller is in allowed_callers list, returns credential value. Logs all access to audit trail. Config from Config/credential_proxy.yaml or passed at startup.
  - **Expected**: Only allowed callers get credentials, access logged, no disk persistence
  - **Test**: `pytest tests/unit/test_credential_proxy.py -v`

- [ ] T075 [US4] Implement src/skills/sync.py — bidirectional vault sync skill
  - **File**: `src/skills/sync.py`
  - **Objective**: Extends BaseSkill. Sync protocol: authenticate endpoints (FR-062), exchange manifests, compute delta, filter by classification (exclude local_only), detect conflicts (same item_id in both deltas), transfer non-conflicting items, flag conflicts for human resolution, update manifests, sync audit logs cloud→local (FR-063). Uses rsync over SSH for file transfer. Encrypted in transit (FR-060).
  - **Expected**: local_only excluded, syncable transferred, conflicts flagged, logs synced
  - **Test**: `pytest tests/integration/test_platinum_sync.py -v`

- [ ] T076 [US4] Implement src/watchers/sync.py — sync staging directory watcher
  - **File**: `src/watchers/sync.py`
  - **Objective**: Extends BaseWatcher. Monitors a local sync staging directory for inbound payloads from cloud. On new payload detected, triggers sync skill to merge into local vault. Detects conflicts and flags for human resolution.
  - **Expected**: Inbound sync payloads trigger vault merge
  - **Test**: Place payload in staging dir, verify merge triggered

- [ ] T077 [P] [US4] Create Config/sync.yaml — sync interval, direction, conflict policy
  - **File**: `Config/sync.yaml`
  - **Objective**: YAML config: enabled=true, cloud_url, interval_seconds=300, direction=bidirectional, conflict_policy=flag_for_human, auth (method=ssh_key, key_ref=SYNC_SSH_KEY_PATH).
  - **Expected**: Valid YAML
  - **Test**: Parse and validate YAML

- [ ] T078 [US4] Implement src/engine/deployment.py — zero-downtime deployment manager
  - **File**: `src/engine/deployment.py`
  - **Objective**: `DeploymentManager` class. Blue-green deployment: start new container alongside old, verify health, switch (stop old), log transition. Vault is shared Docker volume (items preserved). Method: `deploy(new_image) -> DeployResult`. Rollback on health check failure.
  - **Expected**: New container starts, health verified, old stopped, no items lost
  - **Test**: `pytest tests/integration/test_platinum_deploy.py -v`

- [ ] T079 [P] [US4] Create Config/deployment.yaml — deployment strategy and rollback config
  - **File**: `Config/deployment.yaml`
  - **Objective**: YAML config: strategy=blue_green, health_check_timeout_seconds=30, rollback_on_failure=true, shared_volume=/opt/ai-employee/vault.
  - **Expected**: Valid YAML
  - **Test**: Parse and validate YAML

- [ ] T080 [US4] Create Dockerfile for cloud deployment
  - **File**: `Dockerfile`
  - **Objective**: Multi-stage build. Base: Python 3.12 slim. Install dependencies from pyproject.toml [platinum] extras. Copy src/. Set VAULT_ROOT env. Expose health check endpoint. Entrypoint: `python -m src.main --schedule --gold --sync`. Health check: call health monitor endpoint.
  - **Expected**: `docker build -t ai-employee .` succeeds, container starts and passes health check
  - **Test**: `docker build -t ai-employee . && docker run --rm ai-employee python -c "import src"`

- [ ] T081 [US4] Create docker-compose.yml for multi-service cloud orchestration
  - **File**: `docker-compose.yml`
  - **Objective**: Services: ai-employee (main loop), credential-proxy (sidecar). Shared vault volume. Network isolation. Health checks. Environment from .env.cloud. Restart policy: unless-stopped.
  - **Expected**: `docker-compose up -d` starts both services, health checks pass
  - **Test**: `docker-compose config` validates, `docker-compose up -d` starts services

- [ ] T082 [P] [US4] Create scripts/deploy.sh — cloud deployment script
  - **File**: `scripts/deploy.sh`
  - **Objective**: Bash script: pull new image, run deployment manager blue-green swap, verify health, report success/failure. Usage: `./scripts/deploy.sh --image ai-employee:v2.0.0`.
  - **Expected**: Script executable, performs blue-green deployment
  - **Test**: `bash -n scripts/deploy.sh` (syntax check)

- [ ] T083 [P] [US4] Create scripts/sync-daemon.sh — sync daemon start/stop script
  - **File**: `scripts/sync-daemon.sh`
  - **Objective**: Bash script: start/stop/status for the sync daemon. Usage: `./scripts/sync-daemon.sh start|stop|status`.
  - **Expected**: Script executable, manages sync daemon lifecycle
  - **Test**: `bash -n scripts/sync-daemon.sh` (syntax check)

- [ ] T084 [P] [US4] Create templates/health_report.md.j2 — Jinja2 health report template
  - **File**: `templates/health_report.md.j2`
  - **Objective**: Jinja2 template for health report markdown view. Sections: Timestamp, Uptime, Sync Status, Items Summary, Component Health Table, Alerts, Last Sync.
  - **Expected**: Valid Jinja2, renders with sample HealthReport data
  - **Test**: Render with sample data, verify all sections present

- [ ] T085 [P] [US4] Create tests/fixtures/sample_sync_manifest.json — test fixture
  - **File**: `tests/fixtures/sample_sync_manifest.json`
  - **Objective**: Sample sync manifest with: 2 items synced, 1 item skipped (local_only), 1 conflict, status=partial.
  - **Expected**: Valid JSON matching sync manifest schema
  - **Test**: `python -c "import json; json.load(open('tests/fixtures/sample_sync_manifest.json'))"`

- [ ] T086 [US4] Integrate Platinum components in src/main.py — add --sync and --health flags
  - **File**: `src/main.py`
  - **Objective**: Add `--sync` CLI flag (enables vault sync). Add `--health` flag (runs health check and prints report). Wire data classifier into processing pipeline (classify before sync eligibility). Start sync watcher. Schedule health monitor. Start credential proxy on cloud instance.
  - **Command**: `python -m src.main --schedule --gold --sync`
  - **Expected**: All Platinum features active alongside Bronze/Silver/Gold
  - **Test**: Start with --sync, verify sync watcher logs, health monitor active

- [ ] T087 [US4] Run Platinum E2E test and verify quickstart checklist
  - **Objective**: Execute Platinum demo scenario from quickstart.md. Verify all 16 Platinum checklist items pass.
  - **Expected**: Cloud processes events while local offline, sync works, no local_only data leaked, health monitoring active, zero-downtime deploy works
  - **Test**: All 16 Platinum verification checklist items pass

**Checkpoint**: Platinum tier complete — cloud deployment, sync, data classification, health monitoring, and zero-downtime deployments all operational.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, security hardening, and validation across all tiers

- [ ] T088 [P] Validate credential_leak_check() runs on every vault file write across all skills
  - **Objective**: Audit all skills and watchers to ensure config.credential_leak_check() is called before writing any file to the vault. Add guard if missing.
  - **Test**: Grep all file write calls, verify credential_leak_check precedes each

- [ ] T089 [P] Validate DRY_RUN mode works end-to-end across all 4 tiers
  - **Objective**: Run full system with DRY_RUN=true, verify: no files moved, no emails sent, no MCP writes, no social posts, no sync transfers. All logs show [DRY_RUN] prefix.
  - **Test**: Start with DRY_RUN=true, trigger events for each tier, check logs

- [ ] T090 [P] Validate audit logging covers every state transition and skill execution
  - **Objective**: Audit all state_machine.move() and skill.execute() calls to ensure logger.log() is called. Verify FR-038 schema compliance across all log entries.
  - **Test**: Run Bronze E2E, count log entries, verify matches expected transition count

- [ ] T091 Run full test suite and fix any failures
  - **Command**: `pytest tests/ -v --tb=short`
  - **Expected**: All unit and integration tests pass
  - **Test**: `pytest tests/ -v`

- [ ] T092 Run quickstart.md full verification checklist across all 4 tiers
  - **Objective**: Execute all verification checklists from quickstart.md: Bronze (6 items), Silver (6 items), Gold (5 items), Platinum (16 items).
  - **Expected**: All 33 checklist items pass
  - **Test**: Manual verification per quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **Bronze (Phase 3)**: Depends on Phase 2 — MVP, must complete first
- **Silver (Phase 4)**: Depends on Phase 3 (Bronze) — builds on Bronze processing loop
- **Gold (Phase 5)**: Depends on Phase 4 (Silver) — requires MCP infrastructure and approval workflow
- **Platinum (Phase 6)**: Depends on Phase 5 (Gold) — requires all prior tiers stable
- **Polish (Phase 7)**: Depends on all desired tiers being complete

### Within Each Phase

- Test tasks (marked [P]) can run in parallel within a phase
- Config file tasks (marked [P]) can run in parallel
- Model tasks before skill tasks
- Skills before integration tasks
- Core implementation before main.py integration
- Integration task last in each phase

### Parallel Opportunities

**Phase 1 Setup** — all 4 tasks can run in parallel:
```
T001 (pyproject.toml) || T002 (.env.example) || T003 (__init__.py) || T004 (fixtures)
```

**Phase 2 Foundational** — models and tests can run in parallel:
```
T005 (config) || T007 (task_item) || T009 (log_entry) || T014 (plan) || T015 (base watcher) || T016 (base skill)
T006 (test_config) || T008 (test_task_item) || T011 (test_state_machine) || T013 (test_logger)
```

**Phase 3 Bronze** — skills can partially parallelize:
```
T021 (triage) || T024 (dashboard)  -- different files, no deps on each other
```

**Phase 4 Silver** — configs and tests in parallel:
```
T036 (gmail config) || T038 (whatsapp config) || T032 (approval policy)
T027 (test_retry) || T028 (test_silver_email)
```

**Phase 5 Gold** — configs and templates in parallel:
```
T047 (odoo config) || T049 (social config) || T055 (briefing config) || T057 (ralph config)
T051 (briefing template) || T052 (audit template)
T043 (test_briefing) || T044 (test_ralph)
```

**Phase 6 Platinum** — all 7 test files in parallel, all configs in parallel:
```
T061-T067 (all test files) — fully parallel
T071 || T073 || T077 || T079 (all configs) — fully parallel
T082 || T083 || T084 || T085 (scripts, templates, fixtures) — fully parallel
```

---

## Implementation Strategy

### MVP First (Bronze Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks everything)
3. Complete Phase 3: Bronze
4. **STOP and VALIDATE**: Test Bronze independently per quickstart.md
5. Deploy/demo if ready — a working local AI employee

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add Bronze → Test → Demo (MVP! File processing loop works)
3. Add Silver → Test → Demo (Email, messaging, scheduling, approvals)
4. Add Gold → Test → Demo (Odoo, social, CEO briefing, Ralph Wiggum)
5. Add Platinum → Test → Demo (Cloud deployment, sync, health monitoring)
6. Each tier adds value without breaking previous tiers

---

## Summary

| Phase | Tasks | Test Tasks | Impl Tasks | Config Tasks |
|-------|-------|------------|------------|--------------|
| Setup | 4 | 0 | 4 | 0 |
| Foundational | 14 | 4 | 10 | 0 |
| Bronze (US1) | 8 | 1 | 7 | 0 |
| Silver (US2) | 16 | 2 | 10 | 4 |
| Gold (US3) | 18 | 2 | 11 | 5 |
| Platinum (US4) | 27 | 7 | 14 | 6 |
| Polish | 5 | 0 | 5 | 0 |
| **Total** | **92** | **16** | **61** | **15** |

## Notes

- [P] tasks = different files, no dependencies on each other
- [USn] label maps task to user story for traceability
- Each tier is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate tier independently
- DRY_RUN=true for all development and testing
