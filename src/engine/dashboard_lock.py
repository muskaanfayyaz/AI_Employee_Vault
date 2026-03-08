"""Single-writer lock for Dashboard.md (Platinum Tier).

Ensures that only one agent writes to ``Dashboard.md`` at a time, even
when multiple agents run concurrently.  Uses ``fcntl.flock`` on POSIX
systems (Linux, macOS) with a stale-lock fallback for crash recovery.

On Windows (where ``fcntl`` is unavailable), the lock degrades to a
best-effort file-presence check with a warning.  Cloud agents always run
on Linux so the hard guarantee holds in production.

Usage::

    from src.engine.dashboard_lock import DashboardLock

    with DashboardLock(vault_root) as acquired:
        if acquired:
            # write Dashboard.md here
            ...
        # else: lock was held, skip this cycle

Or non-context-manager::

    lock = DashboardLock(vault_root)
    if lock.acquire():
        try:
            ...
        finally:
            lock.release()
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from types import TracebackType
from typing import Type

logger = logging.getLogger(__name__)

_DEFAULT_STALE_SECONDS = int(os.getenv("DASHBOARD_LOCK_STALE_SECONDS", "60"))

try:
    import fcntl as _fcntl
    _FCNTL_AVAILABLE = True
except ImportError:
    _fcntl = None  # type: ignore[assignment]
    _FCNTL_AVAILABLE = False


class DashboardLock:
    """POSIX exclusive lock protecting Dashboard.md writes.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root directory.
    stale_seconds:
        Seconds after which a lock file is considered stale (left by a
        crashed agent).  Any agent may force-release a stale lock.
    """

    def __init__(self, vault_root: Path, stale_seconds: int = _DEFAULT_STALE_SECONDS) -> None:
        self.vault_root = vault_root
        self.stale_seconds = stale_seconds
        self._lock_path = vault_root / ".Dashboard.lock"
        self._lock_file: "open | None" = None  # type: ignore[type-arg]
        self._acquired = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self) -> bool:
        """Try to acquire the dashboard write lock.

        Returns
        -------
        bool
            ``True`` if the lock was acquired successfully.
            ``False`` if the lock is held by another agent (skip this cycle).
        """
        if not _FCNTL_AVAILABLE:
            return self._acquire_fallback()

        for attempt in range(2):
            try:
                lock_file = open(self._lock_path, "w")  # noqa: WPS515
                _fcntl.flock(lock_file, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                self._lock_file = lock_file
                self._acquired = True
                logger.debug("DashboardLock acquired by this agent")
                return True
            except BlockingIOError:
                if attempt == 0 and self._is_stale():
                    logger.warning(
                        "Stale dashboard lock detected (>%ds old) — force-releasing",
                        self.stale_seconds,
                    )
                    self._force_release_stale()
                    # retry once
                    continue
                logger.debug("DashboardLock held by another agent — skipping write cycle")
                return False
            except OSError as exc:
                logger.warning("DashboardLock.acquire() error: %s", exc)
                return False

        return False  # both attempts failed

    def release(self) -> None:
        """Release the lock and remove the lock file."""
        if not _FCNTL_AVAILABLE:
            self._release_fallback()
            return

        if self._lock_file is not None:
            try:
                _fcntl.flock(self._lock_file, _fcntl.LOCK_UN)
                self._lock_file.close()
            except OSError:
                pass
            finally:
                self._lock_file = None
                self._acquired = False

        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._acquired:
            self.release()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_stale(self) -> bool:
        try:
            mtime = self._lock_path.stat().st_mtime
            return (time.time() - mtime) > self.stale_seconds
        except FileNotFoundError:
            return False

    def _force_release_stale(self) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove stale lock file: %s", exc)

    # ------------------------------------------------------------------
    # Windows fallback (best-effort, no hard guarantee)
    # ------------------------------------------------------------------

    def _acquire_fallback(self) -> bool:
        if self._lock_path.exists() and not self._is_stale():
            logger.warning(
                "DashboardLock: fcntl unavailable (Windows?). "
                "Lock file present — skipping write cycle."
            )
            return False
        try:
            self._lock_path.write_text("lock", encoding="utf-8")
            self._acquired = True
            logger.warning(
                "DashboardLock: using best-effort file-presence lock (fcntl unavailable)."
            )
            return True
        except OSError as exc:
            logger.warning("DashboardLock fallback acquire failed: %s", exc)
            return False

    def _release_fallback(self) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError:
            pass
        finally:
            self._acquired = False
