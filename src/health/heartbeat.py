"""Heartbeat writer — each agent signals it is alive by updating a JSON file.

Each agent process writes a timestamped JSON record to
``Logs/heartbeats/<agent_id>.json`` every ``HEARTBEAT_INTERVAL_SECONDS``
(default 60).  The ``HealthMonitor`` reads these records and raises an
alert when any agent's heartbeat goes stale.

The write is atomic: content is written to a ``.tmp`` file first, then
renamed into place.

Usage::

    from src.health.heartbeat import HeartbeatWriter

    writer = HeartbeatWriter(vault_root=Path("/vault"), agent_id="cloud-vm-001")
    writer.write(status="idle")                   # one-shot
    writer.run_forever(interval=60)               # blocking loop
"""
from __future__ import annotations

import json
import logging
import os
import signal
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "60"))


class HeartbeatWriter:
    """Periodically writes a JSON heartbeat file for this agent.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root directory.
    agent_id:
        Unique agent identifier (e.g. ``"cloud-vm-001"``).
    agent_env:
        Deployment environment: ``"cloud"`` or ``"local"``.
    dry_run:
        When ``True`` the heartbeat file is not written.
    """

    def __init__(
        self,
        vault_root: Path,
        agent_id: str,
        agent_env: str = "local",
        *,
        dry_run: bool = False,
    ) -> None:
        self.vault_root = vault_root
        self.agent_id = agent_id
        self.agent_env = agent_env
        self.dry_run = dry_run

        self._heartbeat_dir = vault_root / "Logs" / "heartbeats"
        self._heartbeat_path = self._heartbeat_dir / f"{agent_id}.json"
        self._start_time = time.monotonic()
        self._tasks_completed = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        status: str = "idle",
        *,
        tasks_in_progress: int = 0,
        last_task_id: str | None = None,
        last_task_completed: str | None = None,
        git_sync_last_pull: str | None = None,
        git_sync_last_push: str | None = None,
    ) -> bool:
        """Write (overwrite) the heartbeat file for this agent.

        Parameters
        ----------
        status:
            One of ``"idle"``, ``"processing"``, ``"waiting"``, ``"error"``.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.
        """
        if self.dry_run:
            logger.debug("[DRY_RUN] heartbeat: would write %s", self._heartbeat_path)
            return True

        payload = {
            "agent_id": self.agent_id,
            "agent_env": self.agent_env,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "uptime_seconds": int(time.monotonic() - self._start_time),
            "tasks_completed_session": self._tasks_completed,
            "tasks_in_progress": tasks_in_progress,
            "last_task_id": last_task_id,
            "last_task_completed": last_task_completed,
            "status": status,
            "git_sync_last_pull": git_sync_last_pull,
            "git_sync_last_push": git_sync_last_push,
        }

        try:
            self._heartbeat_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._heartbeat_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.rename(self._heartbeat_path)
            logger.debug("Heartbeat written: status=%s uptime=%ds", status, payload["uptime_seconds"])
            return True
        except OSError as exc:
            logger.warning("Heartbeat write failed: %s", exc)
            return False

    def increment_tasks(self) -> None:
        """Increment the session task counter (call after each completed task)."""
        self._tasks_completed += 1

    def run_forever(self, interval: int = _DEFAULT_INTERVAL) -> None:
        """Write heartbeats on *interval*-second cycles until interrupted."""
        _running = True

        def _stop(sig: int, frame: object) -> None:
            nonlocal _running
            logger.info("HeartbeatWriter shutting down (signal %d)", sig)
            _running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        logger.info(
            "HeartbeatWriter started | agent=%s | interval=%ds",
            self.agent_id, interval,
        )

        while _running:
            self.write(status="idle")
            for _ in range(interval):
                if not _running:
                    break
                time.sleep(1)

        logger.info("HeartbeatWriter stopped.")
