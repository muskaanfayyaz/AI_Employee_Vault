"""Unit tests for ApprovalManager (T031)."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.approval.manager import ApprovalManager
from src.models.approval import ApprovalRequest
from src.models.task_item import TaskItem

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Create a minimal vault with approval-related folders."""
    for folder in ("Pending_Approval", "Approved", "Rejected", "In_Progress", "Logs"):
        (tmp_path / folder).mkdir()
    return tmp_path


@pytest.fixture
def manager(vault: Path) -> ApprovalManager:
    return ApprovalManager(vault)


@pytest.fixture
def dry_manager(vault: Path) -> ApprovalManager:
    return ApprovalManager(vault, dry_run=True)


def _task_item(**kwargs) -> TaskItem:
    defaults = dict(
        id="item-uuid-abcd",
        type="email",
        source="gmail",
        priority="medium",
        status="in_progress",
    )
    defaults.update(kwargs)
    return TaskItem(**defaults)


def _write_pending(vault: Path, decision: str = "pending", **overrides) -> Path:
    """Write an ApprovalRequest file to Pending_Approval/ and return its path."""
    req = ApprovalRequest(
        id=overrides.get("id", "req-uuid-1234"),
        type="email",
        source="gmail",
        priority="medium",
        proposed_action="Send invoice reply",
        reasoning="FR-017",
        decision=decision,
    )
    if decision == "approved":
        object.__setattr__(req, "decision", "approved")
        req.decided_at = datetime.now(timezone.utc).isoformat()
    elif decision == "rejected":
        object.__setattr__(req, "decision", "rejected")
        req.decided_at = datetime.now(timezone.utc).isoformat()

    path = vault / "Pending_Approval" / f"approval-{req.id[:8]}.md"
    req.to_file(path)
    return path


# ── request_approval ─────────────────────────────────────────────────────────

def test_request_approval_creates_file_in_pending(vault: Path, manager: ApprovalManager):
    item = _task_item()
    req = manager.request_approval(item, "Send reply", "FR-017")

    pending_files = list((vault / "Pending_Approval").glob("*.md"))
    assert len(pending_files) == 1
    assert pending_files[0].name.startswith("approval-")


def test_request_approval_returns_approval_request(manager: ApprovalManager):
    item = _task_item()
    req = manager.request_approval(item, "Send reply", "FR-017", "Invoice query")
    assert isinstance(req, ApprovalRequest)
    assert req.decision == "pending"
    assert req.proposed_action == "Send reply"
    assert req.reasoning == "FR-017"
    assert req.original_context == "Invoice query"


def test_request_approval_file_content_matches(vault: Path, manager: ApprovalManager):
    item = _task_item()
    req = manager.request_approval(item, "Send reply to John", "Outbound email")
    pending = list((vault / "Pending_Approval").glob("*.md"))[0]
    loaded = ApprovalRequest.from_file(pending)
    assert loaded.proposed_action == "Send reply to John"
    assert loaded.decision == "pending"
    assert loaded.id == item.id


def test_request_approval_dry_run_no_file_created(vault: Path, dry_manager: ApprovalManager):
    item = _task_item()
    req = dry_manager.request_approval(item, "Send reply", "FR-017")
    pending_files = list((vault / "Pending_Approval").glob("*.md"))
    assert len(pending_files) == 0


def test_request_approval_dry_run_still_returns_request(dry_manager: ApprovalManager):
    item = _task_item()
    req = dry_manager.request_approval(item, "Send reply", "FR-017")
    assert isinstance(req, ApprovalRequest)
    assert req.decision == "pending"


def test_request_approval_propagates_item_fields(vault: Path, manager: ApprovalManager):
    item = _task_item(type="email", source="gmail", priority="urgent", tags=["billing"])
    req = manager.request_approval(item, "Send urgent reply", "High priority")
    loaded = ApprovalRequest.from_file(
        next((vault / "Pending_Approval").glob("*.md"))
    )
    assert loaded.type == "email"
    assert loaded.source == "gmail"
    assert loaded.priority == "urgent"
    assert "billing" in loaded.tags


# ── check_approvals — Pattern A (in-place edit) ───────────────────────────────

def test_check_approvals_moves_approved_to_approved_folder(vault: Path, manager: ApprovalManager):
    _write_pending(vault, decision="approved")
    approved, rejected = manager.check_approvals()

    assert len(approved) == 1
    assert len(rejected) == 0
    assert approved[0].decision == "approved"
    assert not list((vault / "Pending_Approval").glob("*.md"))  # file gone
    assert any((vault / "Approved").glob("*.md"))


def test_check_approvals_moves_rejected_to_rejected_folder(vault: Path, manager: ApprovalManager):
    _write_pending(vault, decision="rejected")
    approved, rejected = manager.check_approvals()

    assert len(approved) == 0
    assert len(rejected) == 1
    assert rejected[0].decision == "rejected"
    assert any((vault / "Rejected").glob("*.md"))


def test_check_approvals_ignores_pending_decisions(vault: Path, manager: ApprovalManager):
    _write_pending(vault, decision="pending")
    approved, rejected = manager.check_approvals()

    assert len(approved) == 0
    assert len(rejected) == 0
    assert any((vault / "Pending_Approval").glob("*.md"))


def test_check_approvals_multiple_decisions(vault: Path, manager: ApprovalManager):
    _write_pending(vault, decision="approved", id="req-aaaa-1111")
    _write_pending(vault, decision="rejected", id="req-bbbb-2222")
    _write_pending(vault, decision="pending", id="req-cccc-3333")

    approved, rejected = manager.check_approvals()
    assert len(approved) == 1
    assert len(rejected) == 1
    # Pending file must remain
    assert len(list((vault / "Pending_Approval").glob("*.md"))) == 1


# ── check_approvals — Pattern B (manual move to Approved/) ───────────────────

def test_check_approvals_picks_up_manually_moved_file(vault: Path, manager: ApprovalManager):
    """Human drags file directly to Approved/ — still detected as approved."""
    req = ApprovalRequest(
        id="req-manual-0001",
        type="email",
        source="gmail",
        priority="medium",
        proposed_action="Send reply",
        reasoning="FR-017",
        decision="pending",
    )
    path = vault / "Approved" / "approval-req-manu.md"
    req.to_file(path)

    approved, rejected = manager.check_approvals()
    assert len(approved) == 1
    # The manager calls req.approve() on manually moved files, so decision becomes "approved"
    assert approved[0].decision == "approved"


def test_check_approvals_already_approved_file_in_approved_folder(vault: Path, manager: ApprovalManager):
    """Files in Approved/ with decision=approved are also returned."""
    req = ApprovalRequest(
        id="req-already-0002",
        type="email",
        source="gmail",
        priority="medium",
        proposed_action="Send reply",
        reasoning="FR-017",
    )
    req.approve(feedback="done")
    path = vault / "Approved" / "approval-req-alre.md"
    req.to_file(path)

    approved, rejected = manager.check_approvals()
    assert len(approved) == 1


# ── check_approvals — dry_run ─────────────────────────────────────────────────

def test_check_approvals_dry_run_does_not_move_files(vault: Path, dry_manager: ApprovalManager):
    _write_pending(vault, decision="approved")
    approved, rejected = dry_manager.check_approvals()

    assert len(approved) == 1
    # File must still be in Pending_Approval/ (dry_run = no actual move)
    assert any((vault / "Pending_Approval").glob("*.md"))


# ── check_approvals — empty / missing dirs ────────────────────────────────────

def test_check_approvals_empty_pending_dir(manager: ApprovalManager):
    approved, rejected = manager.check_approvals()
    assert approved == []
    assert rejected == []


def test_check_approvals_missing_dirs_no_crash(tmp_path: Path):
    """Manager with no folders created must not raise."""
    mgr = ApprovalManager(tmp_path)
    approved, rejected = mgr.check_approvals()
    assert approved == []
    assert rejected == []


# ── get_stale_approvals ───────────────────────────────────────────────────────

def test_get_stale_approvals_returns_expired_pending(vault: Path, manager: ApprovalManager):
    req = ApprovalRequest(
        id="req-stale-0001",
        type="email",
        source="gmail",
        priority="medium",
        proposed_action="Send invoice",
        reasoning="FR-017",
        requested_at=(datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
    )
    # Force expires_at in the past
    req.expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    path = vault / "Pending_Approval" / "approval-stale.md"
    req.to_file(path)

    stale = manager.get_stale_approvals()
    assert len(stale) == 1
    assert stale[0].id == "req-stale-0001"


def test_get_stale_approvals_ignores_fresh_requests(vault: Path, manager: ApprovalManager):
    _write_pending(vault, decision="pending")
    stale = manager.get_stale_approvals()
    assert len(stale) == 0


def test_get_stale_approvals_ignores_decided_items(vault: Path, manager: ApprovalManager):
    """Expired-but-decided approvals are NOT returned as stale."""
    req = ApprovalRequest(
        id="req-decided-0001",
        type="email",
        source="gmail",
        priority="medium",
        proposed_action="Send reply",
        reasoning="FR-017",
        requested_at=(datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
    )
    req.expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    req.approve()  # already decided
    path = vault / "Pending_Approval" / "approval-decided.md"
    req.to_file(path)

    stale = manager.get_stale_approvals()
    assert len(stale) == 0


def test_get_stale_approvals_empty_dir(manager: ApprovalManager):
    stale = manager.get_stale_approvals()
    assert stale == []


# ── audit logging ─────────────────────────────────────────────────────────────

def test_request_approval_calls_audit_logger(vault: Path):
    mock_logger = MagicMock()
    mgr = ApprovalManager(vault, audit_logger=mock_logger)
    item = _task_item()
    mgr.request_approval(item, "Send email", "FR-017")
    mock_logger.log.assert_called_once()


def test_check_approvals_calls_audit_logger_on_decision(vault: Path):
    _write_pending(vault, decision="approved")
    mock_logger = MagicMock()
    mgr = ApprovalManager(vault, audit_logger=mock_logger)
    mgr.check_approvals()
    mock_logger.log.assert_called_once()


def test_no_audit_logger_no_crash(vault: Path, manager: ApprovalManager):
    """Manager without audit logger must not raise."""
    item = _task_item()
    manager.request_approval(item, "Send reply", "FR-017")
    # No exception means pass
