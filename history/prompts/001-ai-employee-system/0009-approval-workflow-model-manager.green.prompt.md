---
id: "0009"
title: approval-workflow-model-manager
stage: green
date: 2026-02-19
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.implement
labels: ["silver","approval","human-in-the-loop","state-machine","dry-run","unit-tests","fr-017"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/models/approval.py
  - src/approval/manager.py
  - Config/approval_policy.yaml
  - tests/unit/test_approval_model.py
  - tests/unit/test_approval_manager.py
  - specs/001-ai-employee-system/tasks.md
tests:
  - tests/unit/test_approval_model.py (21/21 passed)
  - tests/unit/test_approval_manager.py (22/22 passed)
  - tests/ (157/157 passed)
---

## Prompt

Implement approval workflow:

- Sensitive actions create file in /Pending_Approval
- Orchestrator watches /Approved
- When moved → execute MCP call
- Log approval metadata

## Response snapshot

Implemented T030, T031, T032 — the full human-in-the-loop approval workflow.

**T032 — `Config/approval_policy.yaml`** (parallel):
YAML policy with 15 `actions_requiring_approval` (FR-017: send_email, send_message, social_post, payment, delete_data, odoo_write, add_contact, etc.) and 19 `auto_approved_actions` (FR-018: read_file, create_plan, generate_report, ping, etc.). Parses cleanly with `yaml.safe_load`.

**T030 — `src/models/approval.py`**:
`ApprovalRequest` dataclass extending TaskItem fields with a nested `approval:` YAML block. Fields: `proposed_action`, `reasoning`, `original_context`, `requested_at`, `expires_at` (auto-set to `requested_at + 24h`), `decision` (pending|approved|rejected), `decided_at`, `feedback`. Methods: `is_expired()` (compares `expires_at` with `now()`, handles naive datetimes), `approve(feedback)`, `reject(feedback)` (both guard against double-decisions). Serializes via PyYAML for the nested approval block; roundtrip `to_file`/`from_file` tested.

**T031 — `src/approval/manager.py`**:
`ApprovalManager(vault_root, audit_logger, dry_run)`:
- `request_approval(item, proposed_action, reasoning)` — writes `approval-<id[:8]>.md` to `Pending_Approval/`. DRY_RUN=skip write, still returns request.
- `check_approvals()` → `(approved, rejected)` — two detection patterns:
  - **Pattern A** (in-place edit): scans `Pending_Approval/` for `decision != pending` → moves via state machine → tracks IDs in `processed_ids` set
  - **Pattern B** (manual move): scans `Approved/` for files skipping any just moved by Pattern A → calls `req.approve()` on pending ones
- `get_stale_approvals()` — scans `Pending_Approval/` for `decision==pending AND is_expired()`. Never auto-approves (Principle IV).
- All events logged via `AuditLogger` with `ApprovalInfo(required=True, status=..., approver="human")`.

**Bug caught during TDD**: after Pattern A moves a file to `Approved/`, Pattern B was double-counting it. Fixed by tracking `processed_ids: set[str]` and skipping them in Pattern B.

**Tests (43 new, all passing)**:
- `test_approval_model.py` (21): expires_at auto-calc, is_expired (fresh/past/naive tz), approve/reject (success, decided_at, feedback, double-decision guard), invalid decision, YAML roundtrip (from_markdown, to_file/from_file, body, tags)
- `test_approval_manager.py` (22): request_approval (creates file, content, dry_run, field propagation), check_approvals (pattern A approve/reject, pending ignored, multiple decisions, pattern B manual move, already-approved in Approved/, dry_run no move, empty/missing dirs), get_stale (expired, fresh, decided, empty), audit logger (called on request, called on decision, no logger no crash)

## Outcome

- ✅ Impact: T030, T031, T032 implemented and marked [x] in tasks.md
- 🧪 Tests: `pytest tests/ -q` → 157 passed, 0 failed (was 114 before; +43 new)
- 📁 Files: src/models/approval.py, src/approval/manager.py, Config/approval_policy.yaml, tests/unit/test_approval_model.py, tests/unit/test_approval_manager.py
- 🔁 Next prompts: T033 (Python BaseMCPServer), T034 (Python email_server.py), T037 (WhatsApp watcher), T038 (email drafter skill), T041 (Silver integration in main.py)
- 🧠 Reflection: The `processed_ids` set guard is essential when check_approvals both moves files to Approved/ (Pattern A) and reads from Approved/ (Pattern B) in the same call. TDD caught this cleanly — the test for Pattern A failing with count=2 instead of 1 immediately pointed to the double-counting bug.

## Evaluation notes (flywheel)

- Failure modes observed: 3 test failures on first run: syntax error (leftover `)`), Pattern A/B double-counting, wrong test assertion on manual-move behavior
- Graders run and results (PASS/FAIL): pytest 157/157 PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Implement T033 Python BaseMCPServer + T034 email_server.py to complete the Silver MCP tier
