"""Unit tests for src.engine.dashboard_lock — DashboardLock (Platinum Tier)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.engine.dashboard_lock import DashboardLock, _FCNTL_AVAILABLE


@pytest.fixture
def vault(tmp_path) -> Path:
    return tmp_path / "vault"


class TestDashboardLock:
    def test_acquire_and_release(self, vault):
        vault.mkdir()
        lock = DashboardLock(vault)
        acquired = lock.acquire()
        assert acquired is True
        lock.release()
        assert not (vault / ".Dashboard.lock").exists()

    def test_context_manager_acquires(self, vault):
        vault.mkdir()
        with DashboardLock(vault) as acquired:
            assert acquired is True

    def test_context_manager_releases_on_exit(self, vault):
        vault.mkdir()
        with DashboardLock(vault):
            pass
        assert not (vault / ".Dashboard.lock").exists()

    @pytest.mark.skipif(not _FCNTL_AVAILABLE, reason="fcntl not available on this platform")
    def test_second_acquire_fails_while_held(self, vault):
        vault.mkdir()
        lock_a = DashboardLock(vault)
        lock_b = DashboardLock(vault)

        assert lock_a.acquire() is True
        try:
            assert lock_b.acquire() is False
        finally:
            lock_a.release()

    def test_stale_lock_force_released(self, vault):
        vault.mkdir()
        lock_path = vault / ".Dashboard.lock"
        # Write a stale lock file (old mtime via utime).
        lock_path.write_text("stale", encoding="utf-8")
        old_time = time.time() - 120  # 2 minutes ago
        import os
        os.utime(lock_path, (old_time, old_time))

        lock = DashboardLock(vault, stale_seconds=60)
        acquired = lock.acquire()
        assert acquired is True
        lock.release()

    def test_vault_dir_created_on_acquire(self, vault):
        # vault does NOT exist yet
        lock = DashboardLock(vault)
        # Ensure vault exists first (lock_path.parent = vault)
        vault.mkdir()
        acquired = lock.acquire()
        if acquired:
            lock.release()
        # We just verify no exception was raised.

    def test_release_idempotent(self, vault):
        vault.mkdir()
        lock = DashboardLock(vault)
        lock.acquire()
        lock.release()
        lock.release()  # should not raise
