"""Health monitor — detects stale agent heartbeats and raises alerts.

The monitor reads every ``Logs/heartbeats/*.json`` file every
``HEALTH_CHECK_INTERVAL_SECONDS`` (default 60) and compares the
``timestamp`` field against the current UTC time.

If ``now - timestamp > HEARTBEAT_STALE_MINUTES * 60``:
  - Agent is marked **DOWN** → ``agent_down`` alert written to
    ``Logs/health-alerts.jsonl``.

If a previously downed agent produces a fresh heartbeat:
  - Agent is marked **RECOVERED** → ``agent_recovered`` alert written.

The monitor also checks ``In_Progress/<agent_id>/`` for orphaned tasks
(files older than ``CLAIM_TIMEOUT_MINUTES``) and returns them to
``Needs_Action/``.

Usage::

    from src.health.monitor import HealthMonitor

    monitor = HealthMonitor(vault_root=Path("/vault"))
    events = monitor.check_all()    # one-shot
    monitor.run_forever()           # blocking loop (PM2 process)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_STALE_MINUTES = int(os.getenv("HEARTBEAT_STALE_MINUTES", "5"))
_DEFAULT_CLAIM_TIMEOUT = int(os.getenv("CLAIM_TIMEOUT_MINUTES", "30"))
_DEFAULT_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "60"))


@dataclass
class HealthEvent:
    timestamp: str
    event_type: str
    agent_id: str
    extra: dict = field(default_factory=dict)

    def to_jsonl(self) -> str:
        payload = {
            "timestamp": self.timestamp,
            "type": self.event_type,
            "agent_id": self.agent_id,
            **self.extra,
        }
        return json.dumps(payload)


class HealthMonitor:
    """Monitor agent heartbeats and orphaned task files.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root directory.
    stale_minutes:
        Minutes after which a heartbeat is considered stale.
    claim_timeout_minutes:
        Minutes after which an in-progress task is considered orphaned.
    dry_run:
        When ``True`` no files are written or moved.
    """

    def __init__(
        self,
        vault_root: Path,
        *,
        stale_minutes: int = _DEFAULT_STALE_MINUTES,
        claim_timeout_minutes: int = _DEFAULT_CLAIM_TIMEOUT,
        dry_run: bool = False,
    ) -> None:
        self.vault_root = vault_root
        self.stale_minutes = stale_minutes
        self.claim_timeout_minutes = claim_timeout_minutes
        self.dry_run = dry_run

        self._heartbeat_dir = vault_root / "Logs" / "heartbeats"
        self._alert_log = vault_root / "Logs" / "health-alerts.jsonl"
        self._in_progress_dir = vault_root / "In_Progress"
        self._inbox = vault_root / "Needs_Action"

        # Track which agents are currently considered down.
        self._down_agents: dict[str, str] = {}  # agent_id → last_seen ISO

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_all(self) -> list[HealthEvent]:
        """Run one full health check cycle.

        Returns
        -------
        list[HealthEvent]
            New events generated in this cycle (down, recovered, orphaned).
        """
        events: list[HealthEvent] = []
        events.extend(self._check_heartbeats())
        events.extend(self._check_orphans())

        for event in events:
            self._write_alert(event)

        return events

    def run_forever(self, interval: int = _DEFAULT_CHECK_INTERVAL) -> None:
        """Check health on *interval*-second cycles until interrupted."""
        _running = True

        def _stop(sig: int, frame: object) -> None:
            nonlocal _running
            logger.info("HealthMonitor shutting down (signal %d)", sig)
            _running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        logger.info(
            "HealthMonitor started | stale=%dm | orphan=%dm | interval=%ds",
            self.stale_minutes, self.claim_timeout_minutes, interval,
        )

        while _running:
            events = self.check_all()
            if events:
                logger.info("Health check: %d new event(s)", len(events))
            for _ in range(interval):
                if not _running:
                    break
                time.sleep(1)

        logger.info("HealthMonitor stopped.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_heartbeats(self) -> list[HealthEvent]:
        events: list[HealthEvent] = []
        if not self._heartbeat_dir.exists():
            return events

        now_ts = datetime.now(timezone.utc)
        threshold_seconds = self.stale_minutes * 60

        for hb_file in self._heartbeat_dir.glob("*.json"):
            agent_id = hb_file.stem
            try:
                data = json.loads(hb_file.read_text(encoding="utf-8"))
                last_seen_str = data.get("timestamp", "")
                last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                stale_seconds = (now_ts - last_seen).total_seconds()
            except Exception as exc:
                logger.warning("Cannot parse heartbeat for %s: %s", agent_id, exc)
                continue

            if stale_seconds > threshold_seconds:
                if agent_id not in self._down_agents:
                    self._down_agents[agent_id] = last_seen_str
                    event = HealthEvent(
                        timestamp=now_ts.isoformat().replace("+00:00", "Z"),
                        event_type="agent_down",
                        agent_id=agent_id,
                        extra={
                            "last_seen": last_seen_str,
                            "stale_seconds": int(stale_seconds),
                        },
                    )
                    logger.warning(
                        "ALERT: agent %s is DOWN (last seen %s, %.0fs ago)",
                        agent_id, last_seen_str, stale_seconds,
                    )
                    events.append(event)
            else:
                if agent_id in self._down_agents:
                    down_since = self._down_agents.pop(agent_id)
                    try:
                        down_dt = datetime.fromisoformat(down_since.replace("Z", "+00:00"))
                        downtime = int((now_ts - down_dt).total_seconds())
                    except Exception:
                        downtime = 0
                    event = HealthEvent(
                        timestamp=now_ts.isoformat().replace("+00:00", "Z"),
                        event_type="agent_recovered",
                        agent_id=agent_id,
                        extra={"downtime_seconds": downtime},
                    )
                    logger.info("Agent %s RECOVERED (downtime ~%ds)", agent_id, downtime)
                    events.append(event)

        return events

    def _check_orphans(self) -> list[HealthEvent]:
        events: list[HealthEvent] = []
        if not self._in_progress_dir.exists():
            return events

        now = time.time()
        cutoff_age = self.claim_timeout_minutes * 60

        for agent_dir in self._in_progress_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name

            for task_file in agent_dir.iterdir():
                if not task_file.is_file() or task_file.suffix != ".md":
                    continue

                age = now - task_file.stat().st_mtime
                if age < cutoff_age:
                    continue

                dest = self._inbox / task_file.name
                ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                if self.dry_run:
                    logger.warning(
                        "[DRY_RUN] orphan: %s in In_Progress/%s/ for %.0fm — would recover",
                        task_file.name, agent_id, age / 60,
                    )
                else:
                    try:
                        self._inbox.mkdir(parents=True, exist_ok=True)
                        if dest.exists():
                            dest = self._inbox / f"{task_file.stem}-r-{int(now)}{task_file.suffix}"
                        task_file.rename(dest)
                        logger.warning(
                            "Orphan recovered: %s from In_Progress/%s/ (%.0fm old) → Needs_Action/",
                            task_file.name, agent_id, age / 60,
                        )
                    except OSError as exc:
                        logger.error("Orphan recovery error for %s: %s", task_file.name, exc)
                        continue

                events.append(HealthEvent(
                    timestamp=ts,
                    event_type="task_orphaned",
                    agent_id=agent_id,
                    extra={
                        "task_id": task_file.name,
                        "returned_to": "Needs_Action/",
                        "age_minutes": round(age / 60, 1),
                    },
                ))

        return events

    def _write_alert(self, event: HealthEvent) -> None:
        if self.dry_run:
            logger.debug("[DRY_RUN] alert: %s", event.to_jsonl())
            return
        try:
            self._alert_log.parent.mkdir(parents=True, exist_ok=True)
            with self._alert_log.open("a", encoding="utf-8") as fh:
                fh.write(event.to_jsonl() + "\n")
        except OSError as exc:
            logger.warning("Could not write health alert: %s", exc)


# ---------------------------------------------------------------------------
# Standalone entry point (PM2 health-monitor process)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os as _os
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load_dotenv  # type: ignore[import]

    _env_path = _Path.home() / ".ai-employee.env"
    if not _env_path.exists():
        _env_path = _Path.cwd() / ".env"
    _load_dotenv(_env_path, override=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    _vault = _Path(_os.getenv("VAULT_ROOT", str(_Path.cwd()))).resolve()
    _dry_run = _os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
    _interval = int(_os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "60"))

    monitor = HealthMonitor(vault_root=_vault, dry_run=_dry_run)
    monitor.run_forever(interval=_interval)
