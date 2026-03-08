"""Unit tests for src.health.monitor — HealthMonitor (Platinum Tier)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.health.heartbeat import HeartbeatWriter
from src.health.monitor import HealthMonitor


@pytest.fixture
def vault(tmp_path) -> Path:
    v = tmp_path / "vault"
    (v / "Logs" / "heartbeats").mkdir(parents=True)
    (v / "Needs_Action").mkdir()
    (v / "In_Progress").mkdir()
    return v


def _write_stale_heartbeat(vault: Path, agent_id: str, minutes_ago: int) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
    payload = {
        "agent_id": agent_id,
        "agent_env": "cloud",
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "status": "idle",
    }
    hb_path = vault / "Logs" / "heartbeats" / f"{agent_id}.json"
    hb_path.write_text(json.dumps(payload), encoding="utf-8")


def _write_fresh_heartbeat(vault: Path, agent_id: str) -> None:
    writer = HeartbeatWriter(vault, agent_id, "cloud")
    writer.write(status="idle")


class TestCheckHeartbeats:
    def test_fresh_heartbeat_no_alert(self, vault):
        _write_fresh_heartbeat(vault, "cloud-vm-001")
        monitor = HealthMonitor(vault, stale_minutes=5)
        events = monitor.check_all()
        assert not any(e.event_type == "agent_down" for e in events)

    def test_stale_heartbeat_raises_down_event(self, vault):
        _write_stale_heartbeat(vault, "cloud-vm-001", minutes_ago=10)
        monitor = HealthMonitor(vault, stale_minutes=5)
        events = monitor.check_all()
        down_events = [e for e in events if e.event_type == "agent_down"]
        assert len(down_events) == 1
        assert down_events[0].agent_id == "cloud-vm-001"

    def test_down_event_only_raised_once(self, vault):
        _write_stale_heartbeat(vault, "cloud-vm-001", minutes_ago=10)
        monitor = HealthMonitor(vault, stale_minutes=5)
        events1 = monitor.check_all()
        events2 = monitor.check_all()
        assert len([e for e in events1 if e.event_type == "agent_down"]) == 1
        assert len([e for e in events2 if e.event_type == "agent_down"]) == 0

    def test_recovery_event_after_down(self, vault):
        _write_stale_heartbeat(vault, "cloud-vm-001", minutes_ago=10)
        monitor = HealthMonitor(vault, stale_minutes=5)
        monitor.check_all()  # agent goes down

        _write_fresh_heartbeat(vault, "cloud-vm-001")
        events = monitor.check_all()
        recovered = [e for e in events if e.event_type == "agent_recovered"]
        assert len(recovered) == 1

    def test_no_heartbeat_dir(self, tmp_path):
        vault = tmp_path / "empty-vault"
        vault.mkdir()
        monitor = HealthMonitor(vault, stale_minutes=5)
        events = monitor.check_all()
        assert events == []


class TestCheckOrphans:
    def test_fresh_task_not_orphaned(self, vault):
        agent_dir = vault / "In_Progress" / "cloud-vm-001"
        agent_dir.mkdir(parents=True)
        (agent_dir / "task-001.md").write_text("# Task", encoding="utf-8")
        monitor = HealthMonitor(vault, claim_timeout_minutes=30)
        events = monitor.check_all()
        assert not any(e.event_type == "task_orphaned" for e in events)

    def test_old_task_orphaned_and_returned(self, vault):
        agent_dir = vault / "In_Progress" / "cloud-vm-001"
        agent_dir.mkdir(parents=True)
        task = agent_dir / "task-001.md"
        task.write_text("# Task", encoding="utf-8")

        monitor = HealthMonitor(vault, claim_timeout_minutes=0)
        events = monitor.check_all()
        orphaned = [e for e in events if e.event_type == "task_orphaned"]
        assert len(orphaned) == 1
        assert not task.exists()
        assert (vault / "Needs_Action" / "task-001.md").exists()

    def test_dry_run_does_not_move_orphan(self, vault):
        agent_dir = vault / "In_Progress" / "cloud-vm-001"
        agent_dir.mkdir(parents=True)
        task = agent_dir / "task-001.md"
        task.write_text("# Task", encoding="utf-8")

        monitor = HealthMonitor(vault, claim_timeout_minutes=0, dry_run=True)
        monitor.check_all()
        assert task.exists()  # not moved in dry-run


class TestAlertLog:
    def test_alert_written_to_jsonl(self, vault):
        _write_stale_heartbeat(vault, "cloud-vm-001", minutes_ago=10)
        monitor = HealthMonitor(vault, stale_minutes=5)
        monitor.check_all()
        alert_log = vault / "Logs" / "health-alerts.jsonl"
        assert alert_log.exists()
        line = json.loads(alert_log.read_text().strip().splitlines()[0])
        assert line["type"] == "agent_down"
        assert line["agent_id"] == "cloud-vm-001"

    def test_alert_log_is_append_only(self, vault):
        _write_stale_heartbeat(vault, "agent-a", minutes_ago=10)
        _write_stale_heartbeat(vault, "agent-b", minutes_ago=10)
        monitor = HealthMonitor(vault, stale_minutes=5)
        monitor.check_all()
        alert_log = vault / "Logs" / "health-alerts.jsonl"
        lines = alert_log.read_text().strip().splitlines()
        assert len(lines) == 2
