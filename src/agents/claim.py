"""Claim-by-move task claiming for multi-agent vault coordination.

The claim-by-move protocol guarantees that each task in ``Needs_Action/``
is processed by exactly one agent, even when multiple agents poll
simultaneously.

Protocol
--------
1. Agent spots ``Needs_Action/<task>.md``.
2. Agent calls ``ClaimService.claim(task_path)``.
3. ``claim()`` atomically renames the file to
   ``In_Progress/<agent_id>/<task>.md`` via ``os.rename()`` (wraps the
   POSIX ``rename(2)`` syscall — atomic within one filesystem partition).
4. If another agent already claimed the file, ``rename()`` raises
   ``FileNotFoundError``; the caller silently skips this task.
5. After completing work the agent moves the file from
   ``In_Progress/<agent_id>/`` to ``Done/`` or ``Errors/``.

Orphan recovery
---------------
If an agent crashes mid-task, the file stays in ``In_Progress/`` forever.
``recover_orphans()`` detects files older than ``timeout_minutes`` and
returns them to ``Needs_Action/`` for re-claiming.

Cloud vs local output routing
------------------------------
Cloud agents route their completed output files to ``Updates/`` rather
than directly to ``Done/``.  Local agents later merge ``Updates/`` into
the Dashboard and archive to ``Done/``.  This separation is enforced by
passing ``is_cloud=True`` to ``ClaimService``.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_MINUTES = int(os.getenv("CLAIM_TIMEOUT_MINUTES", "30"))


class ClaimService:
    """Atomic task-claim and lifecycle management for one agent.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root directory.
    agent_id:
        Unique identifier for this agent (e.g. ``"cloud-vm-001"``).
    is_cloud:
        When ``True``, completed tasks are routed to ``Updates/`` instead
        of ``Done/`` so the local agent can merge them into the Dashboard.
    timeout_minutes:
        Number of minutes after which an uncompleted ``In_Progress`` claim
        is considered orphaned and eligible for recovery.
    dry_run:
        When ``True``, no filesystem mutations are performed.
    """

    def __init__(
        self,
        vault_root: Path,
        agent_id: str,
        *,
        is_cloud: bool = False,
        timeout_minutes: int = _DEFAULT_TIMEOUT_MINUTES,
        dry_run: bool = False,
    ) -> None:
        self.vault_root = vault_root
        self.agent_id = agent_id
        self.is_cloud = is_cloud
        self.timeout_minutes = timeout_minutes
        self.dry_run = dry_run

        self.inbox = vault_root / "Needs_Action"
        self.in_progress = vault_root / "In_Progress" / agent_id
        self.done = vault_root / "Done"
        self.updates = vault_root / "Updates"
        self.errors = vault_root / "Errors"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_unclaimed(self) -> list[Path]:
        """Return all unclaimed ``.md`` task files in ``Needs_Action/``."""
        if not self.inbox.exists():
            return []
        return sorted(
            f for f in self.inbox.iterdir()
            if f.is_file() and f.suffix == ".md" and not f.name.startswith(".")
        )

    def claim(self, task_path: Path) -> bool:
        """Atomically claim *task_path* by moving it to ``In_Progress/<agent_id>/``.

        Returns
        -------
        bool
            ``True``  — claim succeeded; caller should process the task.
            ``False`` — claim failed (already taken by another agent or file
                        disappeared); caller should skip this task silently.
        """
        if not task_path.exists():
            logger.debug("claim: %s already gone — skipping", task_path.name)
            return False

        dest_dir = self.in_progress
        dest = dest_dir / task_path.name

        if self.dry_run:
            logger.info(
                "[DRY_RUN] claim: would move %s → In_Progress/%s/",
                task_path.name, self.agent_id,
            )
            return True

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            task_path.rename(dest)
            logger.info(
                "Claimed %s → In_Progress/%s/", task_path.name, self.agent_id
            )
            return True
        except FileNotFoundError:
            logger.debug(
                "Claim race lost for %s — another agent claimed it first",
                task_path.name,
            )
            return False
        except OSError as exc:
            logger.warning("Claim failed for %s: %s", task_path.name, exc)
            return False

    def complete(self, task_path: Path) -> Path | None:
        """Mark *task_path* as complete by moving it to the output folder.

        Cloud agents route to ``Updates/``; local agents route to ``Done/``.

        Returns the destination path, or ``None`` on dry-run / failure.
        """
        dest_dir = self.updates if self.is_cloud else self.done
        dest = dest_dir / task_path.name

        if self.dry_run:
            target_label = "Updates/" if self.is_cloud else "Done/"
            logger.info(
                "[DRY_RUN] complete: would move %s → %s", task_path.name, target_label
            )
            return None

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = dest_dir / f"{task_path.stem}-{os.urandom(4).hex()}{task_path.suffix}"
            task_path.rename(dest)
            target_label = "Updates/" if self.is_cloud else "Done/"
            logger.info("Completed %s → %s", task_path.name, target_label)
            return dest
        except OSError as exc:
            logger.error("complete() failed for %s: %s", task_path.name, exc)
            return None

    def fail(self, task_path: Path) -> Path | None:
        """Move *task_path* to ``Errors/`` to signal processing failure."""
        dest = self.errors / task_path.name

        if self.dry_run:
            logger.info("[DRY_RUN] fail: would move %s → Errors/", task_path.name)
            return None

        try:
            self.errors.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = self.errors / f"{task_path.stem}-{os.urandom(4).hex()}{task_path.suffix}"
            task_path.rename(dest)
            logger.info("Failed task archived: %s → Errors/", task_path.name)
            return dest
        except OSError as exc:
            logger.error("fail() error for %s: %s", task_path.name, exc)
            return None

    def recover_orphans(self) -> list[Path]:
        """Return timed-out in-progress tasks to ``Needs_Action/`` for re-claiming.

        A task is orphaned when it has been in ``In_Progress/<agent_id>/``
        for longer than ``self.timeout_minutes`` without a corresponding
        completion or failure.

        Returns a list of paths that were returned to ``Needs_Action/``.
        """
        recovered: list[Path] = []

        if not self.in_progress.exists():
            return recovered

        cutoff = time.time() - self.timeout_minutes * 60

        for task_file in self.in_progress.iterdir():
            if not task_file.is_file() or task_file.suffix != ".md":
                continue

            age_seconds = time.time() - task_file.stat().st_mtime
            if age_seconds < self.timeout_minutes * 60:
                continue

            dest = self.inbox / task_file.name

            if self.dry_run:
                logger.warning(
                    "[DRY_RUN] orphan recovery: would return %s to Needs_Action/ "
                    "(age %.0fm > timeout %dm)",
                    task_file.name, age_seconds / 60, self.timeout_minutes,
                )
                continue

            try:
                self.inbox.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest = self.inbox / f"{task_file.stem}-recovered-{os.urandom(4).hex()}{task_file.suffix}"
                task_file.rename(dest)
                logger.warning(
                    "Orphan recovered: %s → Needs_Action/ (was in-progress %.0fm)",
                    task_file.name, age_seconds / 60,
                )
                recovered.append(dest)
            except OSError as exc:
                logger.error("Orphan recovery failed for %s: %s", task_file.name, exc)

        return recovered
