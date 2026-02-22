"""Shared pytest fixtures (T017)."""
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

import pytest

_VAULT_FOLDERS = [
    "Inbox", "Needs_Action", "Plans", "In_Progress",
    "Pending_Approval", "Approved", "Rejected", "Done",
    "Errors", "Reports", "Logs", "Config", "Skills",
]

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_vault(tmp_path) -> Path:
    """Create a temporary vault with all required folders."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for folder in _VAULT_FOLDERS:
        (vault / folder).mkdir()
    (vault / "drop_folder").mkdir()
    return vault


@pytest.fixture
def sample_task_item(temp_vault) -> Path:
    """Copy the sample_inbox_item.md fixture into temp vault's Needs_Action."""
    src = FIXTURES_DIR / "sample_inbox_item.md"
    dest = temp_vault / "Needs_Action" / "sample_inbox_item.md"
    shutil.copy(src, dest)
    return dest


@pytest.fixture
def sample_log_entry():
    """Return a minimal valid LogEntry."""
    from src.models.log_entry import LogEntry
    return LogEntry(
        actor="test-fixture",
        action="test_action",
        outcome="success",
        item_id="aaaaaaaa-0000-0000-0000-000000000001",
    )


@pytest.fixture
def config_override(temp_vault, monkeypatch):
    """Override DRY_RUN and VAULT_ROOT for tests."""
    import src.config as cfg
    monkeypatch.setattr(cfg, "DRY_RUN", True)
    monkeypatch.setattr(cfg, "VAULT_ROOT", temp_vault)
    return {"DRY_RUN": True, "VAULT_ROOT": temp_vault}
