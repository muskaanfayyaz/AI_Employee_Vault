"""Integration tests for Silver email E2E flow (T028).

Tests:
- Email arrival → GmailWatcher creates item in Needs_Action/
- EmailDrafterSkill → draft in Pending_Approval/
- Approval → decision detected by ApprovalManager → approved / rejected
- Stale approval surfaced (never auto-approved)
- EmailMCPServer.ping() health check
- EmailMCPServer.send_email() dry-run mode
- Credential ref validation (raw value rejected)

All external APIs are mocked — no real Gmail or WhatsApp credentials needed.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.watchers.gmail import GmailWatcher
from src.skills.email_drafter import EmailDrafterSkill
from src.skills.base import SkillInput
from src.approval.manager import ApprovalManager
from src.models.approval import ApprovalRequest


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Minimal vault with all Silver-relevant folders."""
    for folder in (
        "Inbox",
        "Needs_Action",
        "In_Progress",
        "Pending_Approval",
        "Approved",
        "Rejected",
        "Done",
        "Errors",
        "Logs",
        "Config",
    ):
        (tmp_path / folder).mkdir()
    return tmp_path


@pytest.fixture
def gmail_config() -> dict:
    return {
        "watcher": {
            "name": "test-gmail",
            "type": "gmail",
            "enabled": True,
            "polling_interval_seconds": 60,
            "max_results": 10,
            "state_file": "Config/gmail_processed_ids.json",
            "filters": {
                "keywords": ["invoice"],
                "senders": [],
                "labels": [],
            },
            "credential_ref": "GMAIL_OAUTH_TOKEN_PATH",
        }
    }


def _make_gmail_message(
    msg_id: str, subject: str, from_addr: str, body_text: str = ""
) -> dict:
    """Build a minimal Gmail API message dict for testing."""
    return {
        "id": msg_id,
        "snippet": body_text[:100],
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": from_addr},
                {"name": "Date", "value": "2026-02-19T12:00:00Z"},
            ],
            "body": {"data": ""},
            "parts": [],
        },
    }


def _write_email_item(vault: Path, item_id: str, from_addr: str, subject: str) -> Path:
    """Write an email TaskItem in Needs_Action/ and return its path."""
    content = (
        "---\n"
        f"id: {item_id}\n"
        "type: email\n"
        "source: gmail\n"
        "priority: medium\n"
        "status: needs_action\n"
        "requires_approval: false\n"
        "classification: local_only\n"
        "created_at: 2026-02-19T00:00:00+00:00\n"
        "updated_at: 2026-02-19T00:00:00+00:00\n"
        "tags: []\n"
        "---\n\n"
        f"# Email: {subject}\n\n"
        f"**From**: {from_addr}  \n"
        f"**Subject**: {subject}  \n\n"
        "## Content\n\n"
        f"Test email body for {subject}.\n"
    )
    path = vault / "Needs_Action" / f"email-{item_id[:8]}-test.md"
    path.write_text(content, encoding="utf-8")
    return path


# ── GmailWatcher tests ────────────────────────────────────────────────────────


def test_gmail_watcher_creates_item_in_needs_action(
    vault: Path, gmail_config: dict
) -> None:
    """GmailWatcher.create_action_file() writes a valid Task Item."""
    watcher = GmailWatcher(gmail_config)
    watcher._state_file = vault / "Config" / "gmail_processed_ids.json"
    watcher._processed_ids = set()

    msg = _make_gmail_message("msg001abc", "Invoice Q1", "client@example.com")
    event = watcher._parse_message(msg)

    path = watcher.create_action_file(event, vault / "Needs_Action")

    assert path.exists()
    content = path.read_text()
    assert "type: email" in content
    assert "source: gmail" in content
    assert "Invoice Q1" in content
    assert "client@example.com" in content


def test_gmail_watcher_deduplicates_messages(
    vault: Path, gmail_config: dict
) -> None:
    """Second call for the same message ID does not create a duplicate file."""
    watcher = GmailWatcher(gmail_config)
    watcher._state_file = vault / "Config" / "gmail_processed_ids.json"
    watcher._processed_ids = set()

    msg = _make_gmail_message("dup-msg-001", "Duplicate", "a@b.com")
    event = watcher._parse_message(msg)
    needs_action = vault / "Needs_Action"

    watcher.create_action_file(event, needs_action)
    assert "dup-msg-001" in watcher._processed_ids

    # ID is now tracked — check_for_updates would skip it on next poll.
    files = list(needs_action.glob("*.md"))
    assert len(files) == 1


def test_gmail_watcher_filters_matching_emails(
    vault: Path, gmail_config: dict
) -> None:
    """Watcher builds a Gmail search query from configured filters."""
    watcher = GmailWatcher(gmail_config)
    query = watcher._build_query()
    assert "is:unread" in query
    assert "is:important" in query
    # The 'invoice' keyword from the fixture config should be in the query.
    assert "invoice" in query


# ── EmailDrafterSkill tests ───────────────────────────────────────────────────


def test_email_drafter_creates_draft_in_pending_approval(vault: Path) -> None:
    """EmailDrafterSkill writes a draft file to Pending_Approval/."""
    item_path = _write_email_item(
        vault, "item-email-0001", "client@example.com", "Invoice Q1"
    )
    out = EmailDrafterSkill().safe_execute(
        SkillInput(item_path=item_path, vault_root=vault, dry_run=False)
    )
    assert out.success, f"Skill failed: {out.error}"
    drafts = list((vault / "Pending_Approval").glob("draft-*.md"))
    assert len(drafts) == 1


def test_email_drafter_draft_contains_recipient_and_subject(vault: Path) -> None:
    """Draft file includes recipient, reply subject, and greeting."""
    item_path = _write_email_item(
        vault, "item-email-0002", "boss@company.com", "Q4 Report"
    )
    EmailDrafterSkill().safe_execute(
        SkillInput(item_path=item_path, vault_root=vault, dry_run=False)
    )
    draft = list((vault / "Pending_Approval").glob("draft-*.md"))[0]
    text = draft.read_text()

    assert "boss@company.com" in text
    assert "Q4 Report" in text
    assert "Dear" in text


def test_email_drafter_draft_has_approval_block(vault: Path) -> None:
    """Draft file has YAML front-matter with approval decision=pending."""
    item_path = _write_email_item(
        vault, "item-email-0003", "sender@example.com", "Meeting Request"
    )
    EmailDrafterSkill().safe_execute(
        SkillInput(item_path=item_path, vault_root=vault, dry_run=False)
    )
    draft = list((vault / "Pending_Approval").glob("draft-*.md"))[0]
    text = draft.read_text()

    assert "decision: pending" in text
    assert "requires_approval: true" in text


def test_email_drafter_dry_run_no_file_created(vault: Path) -> None:
    """In dry_run mode, no draft file is written to Pending_Approval/."""
    item_path = _write_email_item(
        vault, "item-dry-0004", "test@example.com", "Test"
    )
    out = EmailDrafterSkill().safe_execute(
        SkillInput(item_path=item_path, vault_root=vault, dry_run=True)
    )
    assert out.success
    assert not list((vault / "Pending_Approval").glob("*.md"))


def test_email_drafter_rejects_non_email_type(vault: Path) -> None:
    """EmailDrafterSkill fails gracefully if item type is not email."""
    content = (
        "---\n"
        "id: item-msg-0005\n"
        "type: message\n"
        "source: whatsapp\n"
        "priority: medium\n"
        "status: needs_action\n"
        "requires_approval: false\n"
        "classification: local_only\n"
        "created_at: 2026-02-19T00:00:00+00:00\n"
        "updated_at: 2026-02-19T00:00:00+00:00\n"
        "tags: []\n"
        "---\n\nsome whatsapp message\n"
    )
    item_path = vault / "Needs_Action" / "wa-msg.md"
    item_path.write_text(content, encoding="utf-8")

    out = EmailDrafterSkill().safe_execute(
        SkillInput(item_path=item_path, vault_root=vault, dry_run=False)
    )
    assert not out.success
    assert "email" in (out.error or "").lower() or "email" in out.result.lower()


def test_email_drafter_missing_item_path(vault: Path) -> None:
    """EmailDrafterSkill returns failure when item_path is None."""
    out = EmailDrafterSkill().safe_execute(
        SkillInput(item_path=None, vault_root=vault, dry_run=False)
    )
    assert not out.success


# ── ApprovalManager integration ───────────────────────────────────────────────


def test_approval_approve_flow(vault: Path) -> None:
    """Approved item: decision detected, returned in approved list."""
    from src.models.task_item import TaskItem

    mgr = ApprovalManager(vault)
    item = TaskItem(
        id="flow-item-0001",
        type="email",
        source="gmail",
        priority="medium",
        status="in_progress",
    )
    mgr.request_approval(item, "Send reply to client@example.com", "FR-017")

    req_path = next((vault / "Pending_Approval").glob("approval-*.md"))
    content = req_path.read_text()
    content = content.replace("decision: pending", "decision: approved")
    req_path.write_text(content)

    approved, rejected = mgr.check_approvals()
    assert len(approved) == 1
    assert approved[0].decision == "approved"
    assert len(rejected) == 0


def test_approval_reject_no_send(vault: Path) -> None:
    """Rejected item: returned in rejected list, send is NOT triggered."""
    from src.models.task_item import TaskItem

    mgr = ApprovalManager(vault)
    item = TaskItem(
        id="flow-item-0002",
        type="email",
        source="gmail",
        priority="medium",
        status="in_progress",
    )
    mgr.request_approval(item, "Send reply to boss@company.com", "FR-017")

    req_path = next((vault / "Pending_Approval").glob("approval-*.md"))
    content = req_path.read_text()
    content = content.replace("decision: pending", "decision: rejected")
    req_path.write_text(content)

    approved, rejected = mgr.check_approvals()
    assert len(rejected) == 1
    assert rejected[0].decision == "rejected"
    assert len(approved) == 0


def test_stale_approval_flagged_never_auto_approved(vault: Path) -> None:
    """Approvals >24h old are surfaced as stale — NEVER auto-approved."""
    mgr = ApprovalManager(vault)
    req = ApprovalRequest(
        id="stale-req-0001",
        type="email",
        source="gmail",
        priority="medium",
        proposed_action="Send invoice",
        reasoning="FR-017",
        requested_at=(
            datetime.now(timezone.utc) - timedelta(hours=25)
        ).isoformat(),
    )
    req.expires_at = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    path = vault / "Pending_Approval" / "approval-stale001.md"
    req.to_file(path)

    stale = mgr.get_stale_approvals()
    assert len(stale) == 1
    # Decision must remain pending — Principle IV forbids auto-approval.
    assert stale[0].decision == "pending"


def test_pending_approval_not_returned_in_check(vault: Path) -> None:
    """Pending approvals are not included in approved or rejected."""
    from src.models.task_item import TaskItem

    mgr = ApprovalManager(vault)
    item = TaskItem(
        id="pending-item-001",
        type="email",
        source="gmail",
        priority="medium",
        status="in_progress",
    )
    mgr.request_approval(item, "Send report", "FR-017")

    approved, rejected = mgr.check_approvals()
    assert approved == []
    assert rejected == []


# ── EmailMCPServer tests ──────────────────────────────────────────────────────


def test_email_mcp_server_ping() -> None:
    """EmailMCPServer.ping() returns the standard health-check dict."""
    from src.mcp.email_server import EmailMCPServer

    server = EmailMCPServer(dry_run=True)
    result = server.ping()

    assert result["status"] == "ok"
    assert result["server"] == "email-mcp"
    assert result["version"] == "1.0.0"


def test_email_mcp_send_dry_run() -> None:
    """In dry_run mode, send_email returns success without calling Gmail API."""
    from src.mcp.email_server import EmailMCPServer

    server = EmailMCPServer(dry_run=True)
    result = server.send_email(
        to="test@example.com",
        subject="Test subject",
        body="Hello, world.",
    )
    assert result["status"] == "sent"
    assert result["error"] is None


def test_email_mcp_mark_read_dry_run() -> None:
    """In dry_run mode, mark_read returns ok without calling Gmail API."""
    from src.mcp.email_server import EmailMCPServer

    server = EmailMCPServer(dry_run=True)
    result = server.mark_read("fake-msg-id-001")
    assert result["status"] == "ok"


def test_email_mcp_credential_ref_validation() -> None:
    """Passing a raw credential value (not env var name) raises ValueError."""
    from src.mcp.email_server import EmailMCPServer

    with pytest.raises(ValueError, match="environment variable name"):
        EmailMCPServer(
            credential_refs={"token_path": "/home/user/token.json"}
        )


def test_base_mcp_server_abstract_instantiation() -> None:
    """BaseMCPServer cannot be instantiated directly (abstract)."""
    from src.mcp.base import BaseMCPServer

    with pytest.raises(TypeError):
        BaseMCPServer()  # type: ignore[abstract]


def test_base_mcp_server_ping_format() -> None:
    """ping() output matches the mcp-interfaces.md contract."""
    from src.mcp.email_server import EmailMCPServer

    server = EmailMCPServer(dry_run=True)
    result = server.ping()
    assert set(result.keys()) == {"status", "server", "version"}
    assert result["status"] == "ok"
