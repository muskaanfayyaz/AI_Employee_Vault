"""Unit tests for ApprovalRequest model (T030)."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.models.approval import ApprovalRequest

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fresh_request(**kwargs) -> ApprovalRequest:
    """Return a minimal valid ApprovalRequest."""
    defaults = dict(
        id="test-uuid-1234",
        type="email",
        source="gmail",
        priority="medium",
        proposed_action="Send reply to John",
        reasoning="FR-017 — outbound email requires approval",
        original_context="John asked for invoice",
    )
    defaults.update(kwargs)
    return ApprovalRequest(**defaults)


def _past_iso(hours: float) -> str:
    """ISO-8601 timestamp *hours* in the past."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _future_iso(hours: float) -> str:
    """ISO-8601 timestamp *hours* in the future."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


# ── expires_at auto-calculation ───────────────────────────────────────────────

def test_expires_at_auto_set_24h_after_requested_at():
    req = _fresh_request()
    requested = datetime.fromisoformat(req.requested_at)
    expires = datetime.fromisoformat(req.expires_at)
    if requested.tzinfo is None:
        requested = requested.replace(tzinfo=timezone.utc)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    delta = expires - requested
    assert abs(delta.total_seconds() - 86400) < 1  # exactly 24 hours


def test_expires_at_respected_when_provided():
    custom_expires = _future_iso(48)
    req = _fresh_request(expires_at=custom_expires)
    assert req.expires_at == custom_expires


# ── is_expired ────────────────────────────────────────────────────────────────

def test_is_expired_false_for_fresh_request():
    req = _fresh_request()
    assert not req.is_expired()


def test_is_expired_true_when_expires_at_in_past():
    req = _fresh_request()
    req.expires_at = _past_iso(0.001)  # 1 ms in the past
    assert req.is_expired()


def test_is_expired_handles_naive_datetime():
    """expires_at without tzinfo is treated as UTC."""
    req = _fresh_request()
    # Strip timezone info to simulate naive datetime
    naive = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None).isoformat()
    req.expires_at = naive
    assert req.is_expired()


# ── approve ───────────────────────────────────────────────────────────────────

def test_approve_sets_decision_to_approved():
    req = _fresh_request()
    req.approve()
    assert req.decision == "approved"


def test_approve_sets_decided_at():
    req = _fresh_request()
    req.approve()
    assert req.decided_at is not None
    dt = datetime.fromisoformat(req.decided_at)
    assert abs((dt - datetime.now(timezone.utc)).total_seconds()) < 5


def test_approve_stores_feedback():
    req = _fresh_request()
    req.approve(feedback="Looks good, send it.")
    assert req.feedback == "Looks good, send it."


def test_approve_raises_if_already_approved():
    req = _fresh_request()
    req.approve()
    with pytest.raises(ValueError, match="already set"):
        req.approve()


def test_approve_raises_if_already_rejected():
    req = _fresh_request()
    req.reject()
    with pytest.raises(ValueError, match="already set"):
        req.approve()


# ── reject ────────────────────────────────────────────────────────────────────

def test_reject_sets_decision_to_rejected():
    req = _fresh_request()
    req.reject()
    assert req.decision == "rejected"


def test_reject_sets_decided_at():
    req = _fresh_request()
    req.reject()
    assert req.decided_at is not None


def test_reject_stores_feedback():
    req = _fresh_request()
    req.reject(feedback="Not the right time.")
    assert req.feedback == "Not the right time."


def test_reject_raises_if_already_decided():
    req = _fresh_request()
    req.reject()
    with pytest.raises(ValueError, match="already set"):
        req.reject()


# ── invalid decision ─────────────────────────────────────────────────────────

def test_invalid_decision_raises_value_error():
    with pytest.raises(ValueError, match="Invalid decision"):
        _fresh_request(decision="maybe")


# ── serialization round-trip ──────────────────────────────────────────────────

def test_to_markdown_contains_approval_block():
    req = _fresh_request()
    md = req.to_markdown()
    assert "approval:" in md
    assert "proposed_action:" in md
    assert "decision: pending" in md
    assert "expires_at:" in md


def test_from_markdown_roundtrip():
    req = _fresh_request()
    req.approve(feedback="Approved by test")
    md = req.to_markdown()
    restored = ApprovalRequest.from_markdown(md)

    assert restored.id == req.id
    assert restored.type == req.type
    assert restored.source == req.source
    assert restored.proposed_action == req.proposed_action
    assert restored.reasoning == req.reasoning
    assert restored.decision == "approved"
    assert restored.feedback == "Approved by test"
    assert restored.decided_at is not None


def test_from_markdown_null_fields_become_none():
    req = _fresh_request()
    md = req.to_markdown()
    restored = ApprovalRequest.from_markdown(md)
    assert restored.decided_at is None
    assert restored.feedback is None


def test_to_file_and_from_file_roundtrip(tmp_path: Path):
    req = _fresh_request()
    req.reject(feedback="Not now.")
    out = tmp_path / "approval-test.md"
    req.to_file(out)

    loaded = ApprovalRequest.from_file(out)
    assert loaded.decision == "rejected"
    assert loaded.feedback == "Not now."
    assert loaded.id == req.id
    assert loaded.proposed_action == req.proposed_action


def test_from_file_preserves_body(tmp_path: Path):
    req = _fresh_request()
    req.body = "## Original email\n\nPlease review."
    out = tmp_path / "approval-body.md"
    req.to_file(out)

    loaded = ApprovalRequest.from_file(out)
    assert "Original email" in loaded.body


def test_to_markdown_tags_serialized(tmp_path: Path):
    req = _fresh_request(tags=["urgent", "billing"])
    out = tmp_path / "approval-tags.md"
    req.to_file(out)
    loaded = ApprovalRequest.from_file(out)
    assert "urgent" in loaded.tags
    assert "billing" in loaded.tags
