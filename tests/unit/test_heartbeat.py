"""Unit tests for src.health.heartbeat — HeartbeatWriter (Platinum Tier)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.health.heartbeat import HeartbeatWriter


@pytest.fixture
def vault(tmp_path) -> Path:
    return tmp_path / "vault"


@pytest.fixture
def writer(vault) -> HeartbeatWriter:
    return HeartbeatWriter(vault, "test-agent", "cloud")


class TestHeartbeatWriter:
    def test_creates_heartbeat_file(self, vault, writer):
        ok = writer.write(status="idle")
        assert ok is True
        hb_path = vault / "Logs" / "heartbeats" / "test-agent.json"
        assert hb_path.exists()

    def test_heartbeat_content(self, vault, writer):
        writer.write(status="processing", tasks_in_progress=1)
        hb_path = vault / "Logs" / "heartbeats" / "test-agent.json"
        data = json.loads(hb_path.read_text())
        assert data["agent_id"] == "test-agent"
        assert data["agent_env"] == "cloud"
        assert data["status"] == "processing"
        assert data["tasks_in_progress"] == 1
        assert "timestamp" in data
        assert data["timestamp"].endswith("Z")

    def test_heartbeat_overwrites_previous(self, vault, writer):
        writer.write(status="idle")
        writer.write(status="processing")
        hb_path = vault / "Logs" / "heartbeats" / "test-agent.json"
        data = json.loads(hb_path.read_text())
        assert data["status"] == "processing"

    def test_creates_heartbeat_dir(self, vault, writer):
        assert not (vault / "Logs" / "heartbeats").exists()
        writer.write()
        assert (vault / "Logs" / "heartbeats").is_dir()

    def test_dry_run_does_not_write(self, vault):
        writer = HeartbeatWriter(vault, "dry-agent", "local", dry_run=True)
        ok = writer.write(status="idle")
        assert ok is True
        assert not (vault / "Logs" / "heartbeats" / "dry-agent.json").exists()

    def test_increment_tasks(self, vault, writer):
        writer.increment_tasks()
        writer.increment_tasks()
        writer.write(status="idle")
        hb_path = vault / "Logs" / "heartbeats" / "test-agent.json"
        data = json.loads(hb_path.read_text())
        assert data["tasks_completed_session"] == 2

    def test_uptime_increases(self, vault, writer):
        writer.write(status="idle")
        hb_path = vault / "Logs" / "heartbeats" / "test-agent.json"
        d1 = json.loads(hb_path.read_text())
        time.sleep(0.05)
        writer.write(status="idle")
        d2 = json.loads(hb_path.read_text())
        assert d2["uptime_seconds"] >= d1["uptime_seconds"]
