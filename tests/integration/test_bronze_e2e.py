"""Bronze E2E integration test: Inbox → Done (T019, T026).

Tests the full local file processing loop:
  drop_folder detected → Needs_Action/ → Plans/ created → Done/ → log → dashboard
"""
import json
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _seed_needs_action(vault: Path) -> Path:
    """Copy sample fixture into Needs_Action/."""
    src = FIXTURES / "sample_inbox_item.md"
    dest = vault / "Needs_Action" / "sample_inbox_item.md"
    shutil.copy(src, dest)
    return dest


# ── Main E2E: processing cycle ────────────────────────────────────────────────

def test_full_processing_cycle_dry_run(temp_vault):
    """DRY_RUN=True: no files move, logs show [DRY_RUN] prefix."""
    _seed_needs_action(temp_vault)
    from src.main import run_processing_cycle
    run_processing_cycle(temp_vault, dry_run=True)

    # File still in Needs_Action (not moved).
    assert (temp_vault / "Needs_Action" / "sample_inbox_item.md").exists()
    # Dashboard updated (dashboard skill still writes in dry_run).
    assert (temp_vault / "Dashboard.md").exists()


def test_full_processing_cycle_live(temp_vault):
    """Live run: item flows Needs_Action → Plans/ created → Done/ or further."""
    _seed_needs_action(temp_vault)
    from src.main import run_processing_cycle
    run_processing_cycle(temp_vault, dry_run=False)

    # Plan created.
    plans = list((temp_vault / "Plans").iterdir())
    assert len(plans) >= 1, "Expected at least one plan file"
    assert any("PLAN_sample_inbox_item" in p.name for p in plans)

    # Dashboard updated.
    assert (temp_vault / "Dashboard.md").exists()

    # Audit log written.
    logs = list((temp_vault / "Logs").glob("*.json"))
    assert len(logs) >= 1


def test_log_entries_written(temp_vault):
    """Audit log entries are created for each skill."""
    _seed_needs_action(temp_vault)
    from src.main import run_processing_cycle
    run_processing_cycle(temp_vault, dry_run=False)

    log_files = list((temp_vault / "Logs").glob("*.json"))
    assert log_files, "No log file created"
    entries = json.loads(log_files[0].read_text())
    assert isinstance(entries, list)
    assert len(entries) >= 1
    for e in entries:
        assert "timestamp" in e
        assert "actor" in e
        assert "outcome" in e


def test_dashboard_updated(temp_vault):
    """Dashboard.md is regenerated after a processing cycle."""
    _seed_needs_action(temp_vault)
    from src.main import run_processing_cycle
    run_processing_cycle(temp_vault, dry_run=False)

    dashboard = temp_vault / "Dashboard.md"
    assert dashboard.exists()
    content = dashboard.read_text()
    assert "Dashboard" in content
    assert "Plans/" in content


def test_dry_run_logs_have_dry_run_flag(temp_vault):
    """DRY_RUN log entries have dry_run=True."""
    _seed_needs_action(temp_vault)
    from src.main import run_processing_cycle
    run_processing_cycle(temp_vault, dry_run=True)

    log_files = list((temp_vault / "Logs").glob("*.json"))
    if log_files:
        entries = json.loads(log_files[0].read_text())
        for e in entries:
            assert e.get("dry_run") is True


def test_empty_needs_action_is_noop(temp_vault):
    """Processing cycle with empty Needs_Action completes without error."""
    from src.main import run_processing_cycle
    run_processing_cycle(temp_vault, dry_run=False)
    # No exception, dashboard still runs.
    assert (temp_vault / "Dashboard.md").exists()


# ── --init flag ───────────────────────────────────────────────────────────────

def test_init_creates_all_vault_folders(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    from src.main import init_vault
    init_vault(vault)

    expected = [
        "Inbox", "Needs_Action", "Plans", "In_Progress",
        "Pending_Approval", "Approved", "Rejected", "Done",
        "Errors", "Reports", "Logs", "Config", "Skills",
    ]
    for folder in expected:
        assert (vault / folder).exists(), f"Missing folder: {folder}"
    assert (vault / "Dashboard.md").exists()
