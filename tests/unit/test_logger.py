"""Tests for src/engine/logger.py (T013)."""
import json
import pytest
from pathlib import Path
from src.engine.logger import AuditLogger, redact
from src.models.log_entry import LogEntry, ApprovalInfo


def make_entry(**kwargs) -> LogEntry:
    defaults = dict(actor="test-skill", action="test_action", outcome="success")
    defaults.update(kwargs)
    return LogEntry(**defaults)


# ── Schema compliance ─────────────────────────────────────────────────────────

def test_log_entry_schema(tmp_path):
    logger = AuditLogger(tmp_path)
    entry = make_entry(item_id="abc-123", from_state="Inbox", to_state="Needs_Action")
    log_file = logger.log(entry)
    data = json.loads(log_file.read_text())
    assert isinstance(data, list)
    assert len(data) == 1
    row = data[0]
    assert "timestamp" in row
    assert "actor" in row
    assert "outcome" in row
    assert "dry_run" in row


def test_append_only_multiple_writes(tmp_path):
    logger = AuditLogger(tmp_path)
    for i in range(3):
        logger.log(make_entry(action=f"action_{i}"))
    log_file = next(tmp_path.iterdir())
    data = json.loads(log_file.read_text())
    assert len(data) == 3
    assert data[0]["action"] == "action_0"
    assert data[2]["action"] == "action_2"


# ── Redaction ─────────────────────────────────────────────────────────────────

def test_redact_email():
    result = redact("Contact john.smith@example.com for details")
    assert "john.smith" not in result
    assert "@example.com" in result
    assert "j***@example.com" in result


def test_redact_financial_amount():
    result = redact("The total was $1,234.56")
    assert "$1,234.56" not in result
    assert "$***" in result


def test_dry_run_entries_flagged(tmp_path):
    logger = AuditLogger(tmp_path)
    entry = make_entry(action="[DRY_RUN] test", outcome="dry_run", dry_run=True)
    log_file = logger.log(entry)
    data = json.loads(log_file.read_text())
    assert data[0]["dry_run"] is True
    assert data[0]["outcome"] == "dry_run"


# ── Validation ────────────────────────────────────────────────────────────────

def test_invalid_outcome_raises():
    entry = make_entry(outcome="INVALID")
    with pytest.raises(ValueError, match="Invalid outcome"):
        entry.validate()


def test_invalid_timestamp_raises():
    entry = LogEntry(actor="x", action="y", outcome="success",
                     timestamp="not-a-timestamp")
    with pytest.raises(ValueError, match="Invalid timestamp"):
        entry.validate()
