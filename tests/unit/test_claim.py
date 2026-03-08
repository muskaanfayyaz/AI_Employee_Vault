"""Unit tests for src.agents.claim — ClaimService (Platinum Tier)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.agents.claim import ClaimService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vault(tmp_path) -> Path:
    v = tmp_path / "vault"
    (v / "Needs_Action").mkdir(parents=True)
    (v / "Done").mkdir()
    (v / "Updates").mkdir()
    (v / "Errors").mkdir()
    return v


@pytest.fixture
def task_file(vault) -> Path:
    f = vault / "Needs_Action" / "task-001.md"
    f.write_text("# Task 001\n\nDo something.", encoding="utf-8")
    return f


def _local_svc(vault: Path, **kw) -> ClaimService:
    return ClaimService(vault, "local-dev", is_cloud=False, dry_run=False, **kw)


def _cloud_svc(vault: Path, **kw) -> ClaimService:
    return ClaimService(vault, "cloud-vm-001", is_cloud=True, dry_run=False, **kw)


# ---------------------------------------------------------------------------
# list_unclaimed
# ---------------------------------------------------------------------------

class TestListUnclaimed:
    def test_returns_md_files(self, vault, task_file):
        svc = _local_svc(vault)
        files = svc.list_unclaimed()
        assert task_file in files

    def test_excludes_hidden_files(self, vault):
        (vault / "Needs_Action" / ".hidden").write_text("x")
        svc = _local_svc(vault)
        names = [f.name for f in svc.list_unclaimed()]
        assert ".hidden" not in names

    def test_excludes_non_md_files(self, vault):
        (vault / "Needs_Action" / "data.json").write_text("{}")
        svc = _local_svc(vault)
        names = [f.name for f in svc.list_unclaimed()]
        assert "data.json" not in names

    def test_empty_inbox(self, vault):
        svc = _local_svc(vault)
        assert svc.list_unclaimed() == []

    def test_no_inbox_directory(self, tmp_path):
        svc = ClaimService(tmp_path, "agent", dry_run=False)
        assert svc.list_unclaimed() == []


# ---------------------------------------------------------------------------
# claim
# ---------------------------------------------------------------------------

class TestClaim:
    def test_successful_claim_moves_file(self, vault, task_file):
        svc = _local_svc(vault)
        claimed = svc.claim(task_file)
        assert claimed is True
        assert not task_file.exists()
        claimed_path = vault / "In_Progress" / "local-dev" / "task-001.md"
        assert claimed_path.exists()

    def test_claim_already_gone_returns_false(self, vault, task_file):
        svc = _local_svc(vault)
        task_file.unlink()
        assert svc.claim(task_file) is False

    def test_claim_race_second_agent_fails(self, vault, task_file):
        """Simulates two agents racing: the second should return False."""
        svc_a = _local_svc(vault)
        svc_b = _cloud_svc(vault)

        ok_a = svc_a.claim(task_file)
        ok_b = svc_b.claim(task_file)  # file already gone

        assert ok_a is True
        assert ok_b is False

    def test_claim_creates_agent_subdirectory(self, vault, task_file):
        svc = _cloud_svc(vault)
        svc.claim(task_file)
        assert (vault / "In_Progress" / "cloud-vm-001").is_dir()

    def test_dry_run_does_not_move(self, vault, task_file):
        svc = ClaimService(vault, "local-dev", dry_run=True)
        result = svc.claim(task_file)
        assert result is True
        assert task_file.exists()  # file NOT moved in dry-run


# ---------------------------------------------------------------------------
# complete — local routes to Done/, cloud routes to Updates/
# ---------------------------------------------------------------------------

class TestComplete:
    def test_local_routes_to_done(self, vault, task_file):
        svc = _local_svc(vault)
        svc.claim(task_file)
        in_progress = vault / "In_Progress" / "local-dev" / "task-001.md"
        dest = svc.complete(in_progress)
        assert dest is not None
        assert dest.parent == vault / "Done"
        assert dest.exists()

    def test_cloud_routes_to_updates(self, vault, task_file):
        svc = _cloud_svc(vault)
        svc.claim(task_file)
        in_progress = vault / "In_Progress" / "cloud-vm-001" / "task-001.md"
        dest = svc.complete(in_progress)
        assert dest is not None
        assert dest.parent == vault / "Updates"
        assert dest.exists()

    def test_dry_run_returns_none(self, vault, task_file):
        svc = ClaimService(vault, "local-dev", dry_run=True)
        result = svc.complete(task_file)
        assert result is None


# ---------------------------------------------------------------------------
# fail
# ---------------------------------------------------------------------------

class TestFail:
    def test_moves_to_errors(self, vault, task_file):
        svc = _local_svc(vault)
        svc.claim(task_file)
        in_progress = vault / "In_Progress" / "local-dev" / "task-001.md"
        dest = svc.fail(in_progress)
        assert dest is not None
        assert dest.parent == vault / "Errors"
        assert dest.exists()


# ---------------------------------------------------------------------------
# recover_orphans
# ---------------------------------------------------------------------------

class TestRecoverOrphans:
    def test_fresh_task_not_recovered(self, vault, task_file):
        svc = ClaimService(vault, "local-dev", timeout_minutes=30, dry_run=False)
        svc.claim(task_file)
        recovered = svc.recover_orphans()
        assert recovered == []

    def test_old_task_recovered(self, vault, task_file):
        svc = ClaimService(vault, "local-dev", timeout_minutes=0, dry_run=False)
        svc.claim(task_file)
        in_progress = vault / "In_Progress" / "local-dev" / "task-001.md"
        # Force old mtime (already 0 minutes, so any age triggers recovery).
        assert in_progress.exists()
        recovered = svc.recover_orphans()
        assert len(recovered) == 1
        assert recovered[0].parent == vault / "Needs_Action"
        assert not in_progress.exists()

    def test_dry_run_does_not_move_orphan(self, vault, task_file):
        svc = ClaimService(vault, "local-dev", timeout_minutes=0, dry_run=True)
        svc_live = ClaimService(vault, "local-dev", timeout_minutes=0, dry_run=False)
        # Use live claim to place file in In_Progress.
        svc_live_claim = ClaimService(vault, "local-dev", timeout_minutes=30, dry_run=False)
        svc_live_claim.claim(task_file)
        in_progress = vault / "In_Progress" / "local-dev" / "task-001.md"
        assert in_progress.exists()

        # dry-run svc should not move it.
        svc.recover_orphans()
        assert in_progress.exists()
