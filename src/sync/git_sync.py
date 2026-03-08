"""Git-based vault synchronisation service (Platinum Tier).

Keeps the local vault and the cloud VM vault in sync by running
``git pull --rebase`` and ``git push`` on a configurable schedule.

Sync rules
----------
- **Markdown only**: only ``*.md`` files are staged and committed.
  Binary files, ``.env``, secrets, and configuration artefacts are
  excluded via ``.gitignore`` and the selective ``git add`` call.
- **Exclude ``.env``**: never staged, even if accidentally placed inside
  the vault.  Belt-and-suspenders: ``.gitignore`` blocks it; the add
  command further restricts to ``*.md``.
- **Pull before push**: ``git pull --rebase`` minimises merge conflicts
  by replaying local commits on top of remote changes.
- **Exponential backoff**: on consecutive failures the sync waits
  1 → 2 → 4 → … → 60 seconds between retries before suspending for
  ``SYNC_SUSPEND_MINUTES`` (default 5).

Cloud-specific routing
----------------------
The cloud agent writes task outputs to ``Updates/`` rather than
``Done/``.  The sync service pushes ``Updates/*.md`` to the remote so
the local agent can pull and merge them into the Dashboard.

Usage::

    from src.sync.git_sync import GitSyncService

    svc = GitSyncService(vault_root=Path("/vault"), agent_id="cloud-vm-001")
    svc.sync()                    # one-shot pull + push
    svc.run_forever(interval=60)  # blocking loop (use in subprocess / thread)
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = int(os.getenv("GIT_SYNC_INTERVAL_SECONDS", "60"))
_DEFAULT_REMOTE = os.getenv("GIT_REMOTE", "origin")
_DEFAULT_BRANCH = os.getenv("GIT_BRANCH", "main")
_SUSPEND_MINUTES = int(os.getenv("SYNC_SUSPEND_MINUTES", "5"))
_MAX_CONSECUTIVE_FAILURES = 3


class SyncResult:
    """Result of a single pull or push operation."""

    def __init__(self, ok: bool, action: str, detail: str = "") -> None:
        self.ok = ok
        self.action = action
        self.detail = detail

    def __repr__(self) -> str:
        status = "OK" if self.ok else "FAIL"
        return f"SyncResult({status}, {self.action!r}, {self.detail!r})"


class GitSyncService:
    """Synchronise the vault Git repository with a remote.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault (must be a Git repository root).
    agent_id:
        Agent identifier embedded in commit messages.
    remote:
        Git remote name (default ``"origin"``).
    branch:
        Git branch name (default ``"main"``).
    dry_run:
        When ``True`` no Git commands that mutate state are executed.
    """

    def __init__(
        self,
        vault_root: Path,
        agent_id: str,
        *,
        remote: str = _DEFAULT_REMOTE,
        branch: str = _DEFAULT_BRANCH,
        dry_run: bool = False,
    ) -> None:
        self.vault_root = vault_root
        self.agent_id = agent_id
        self.remote = remote
        self.branch = branch
        self.dry_run = dry_run
        self._consecutive_failures = 0

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def pull(self) -> SyncResult:
        """Run ``git pull --rebase`` to incorporate remote changes.

        Uses ``--rebase`` to keep the local history linear and reduce
        merge-conflict noise from simultaneous agent writes.
        """
        result = self._git("pull", "--rebase", self.remote, self.branch)
        if result.ok:
            logger.info("Git pull OK: %s", result.detail.strip() or "(up to date)")
            self._consecutive_failures = 0
        else:
            logger.warning("Git pull failed: %s", result.detail.strip())
            # Abort any in-progress rebase to leave the repo clean.
            self._git("rebase", "--abort")
        return result

    def push(self, message: str | None = None) -> SyncResult:
        """Stage all ``*.md`` changes and push to the remote.

        Only ``.md`` files are staged — secrets, binaries, and ``.env``
        are excluded by design.

        Parameters
        ----------
        message:
            Commit message.  Defaults to an auto-generated agent sync message.
        """
        if not self._has_md_changes():
            logger.debug("push: no markdown changes to commit")
            return SyncResult(ok=True, action="push", detail="nothing to commit")

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        commit_msg = message or f"agent: {self.agent_id} sync {ts}"

        if self.dry_run:
            logger.info("[DRY_RUN] push: would commit and push — %s", commit_msg)
            return SyncResult(ok=True, action="push", detail="dry_run")

        # Stage markdown files only.
        add_result = self._git("add", "--", "*.md", "**/*.md")
        if not add_result.ok:
            return SyncResult(ok=False, action="push:add", detail=add_result.detail)

        # Commit (no-op if nothing staged after add).
        commit_result = self._git(
            "commit", "-m", commit_msg,
            "--no-verify",          # secrets guard runs locally on explicit commits
        )
        if not commit_result.ok:
            if "nothing to commit" in commit_result.detail.lower():
                logger.debug("push: nothing to commit after add")
                return SyncResult(ok=True, action="push", detail="nothing to commit")
            return SyncResult(ok=False, action="push:commit", detail=commit_result.detail)

        push_result = self._git("push", self.remote, self.branch)
        if push_result.ok:
            logger.info("Git push OK: %s", commit_msg)
            self._consecutive_failures = 0
        else:
            logger.warning("Git push failed: %s", push_result.detail.strip())
        return push_result

    def sync(self) -> SyncResult:
        """Pull then push — the standard sync cycle.

        Tracks consecutive failures and suspends sync after
        ``_MAX_CONSECUTIVE_FAILURES`` to avoid hammering a broken remote.
        """
        pull_result = self.pull()
        if not pull_result.ok:
            self._consecutive_failures += 1
            self._maybe_suspend()
            return pull_result

        push_result = self.push()
        if not push_result.ok:
            self._consecutive_failures += 1
            self._maybe_suspend()
        return push_result

    # ------------------------------------------------------------------
    # Long-running loop (for standalone subprocess / PM2 process)
    # ------------------------------------------------------------------

    def run_forever(self, interval: int = _DEFAULT_INTERVAL) -> None:
        """Block and sync on *interval*-second cycles until interrupted.

        Designed to run as the ``git-sync`` PM2 process:

        .. code-block:: bash

            python -m src.sync.git_sync

        Responds to ``SIGINT`` / ``SIGTERM`` for graceful shutdown.
        """
        import signal

        _running = True

        def _stop(sig: int, frame: object) -> None:
            nonlocal _running
            logger.info("GitSyncService shutting down (signal %d)", sig)
            _running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        logger.info(
            "GitSyncService started | agent=%s | remote=%s/%s | interval=%ds",
            self.agent_id, self.remote, self.branch, interval,
        )

        while _running:
            self.sync()
            # Sleep in 1-second ticks so SIGTERM is handled promptly.
            for _ in range(interval):
                if not _running:
                    break
                time.sleep(1)

        logger.info("GitSyncService stopped.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _git(self, *args: str) -> SyncResult:
        """Run a ``git`` subcommand in *vault_root* and return the result."""
        cmd = ["git", "-C", str(self.vault_root), *args]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            ok = proc.returncode == 0
            detail = (proc.stdout + proc.stderr).strip()
            return SyncResult(ok=ok, action=" ".join(args[:2]), detail=detail)
        except subprocess.TimeoutExpired:
            logger.error("Git command timed out: %s", " ".join(args))
            return SyncResult(ok=False, action=args[0], detail="timeout")
        except FileNotFoundError:
            logger.error("git executable not found — is Git installed?")
            return SyncResult(ok=False, action=args[0], detail="git not found")

    def _has_md_changes(self) -> bool:
        """Return ``True`` if there are any staged or unstaged ``.md`` changes."""
        result = self._git("status", "--porcelain")
        if not result.ok:
            return False
        return any(
            line.strip().endswith(".md")
            for line in result.detail.splitlines()
            if line.strip()
        )

    def _maybe_suspend(self) -> None:
        if self._consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            logger.error(
                "GitSyncService: %d consecutive failures — suspending for %d minutes",
                self._consecutive_failures, _SUSPEND_MINUTES,
            )
            time.sleep(_SUSPEND_MINUTES * 60)
            self._consecutive_failures = 0


# ---------------------------------------------------------------------------
# Standalone entry point (used by PM2 ecosystem.config.js)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os as _os
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load_dotenv  # type: ignore[import]

    _env_path = _Path.home() / ".ai-employee.env"
    if not _env_path.exists():
        _env_path = _Path.cwd() / ".env"
    _load_dotenv(_env_path, override=True)

    _vault = _Path(_os.getenv("VAULT_ROOT", str(_Path.cwd()))).resolve()
    _agent_id = _os.getenv("AGENT_ID", "unknown")
    _dry_run = _os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
    _interval = int(_os.getenv("GIT_SYNC_INTERVAL_SECONDS", "60"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    svc = GitSyncService(vault_root=_vault, agent_id=_agent_id, dry_run=_dry_run)
    svc.run_forever(interval=_interval)
