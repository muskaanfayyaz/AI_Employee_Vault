"""Tests for src/models/task_item.py (T008)."""
import pytest
from pathlib import Path
from src.models.task_item import TaskItem


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_inbox_item.md"


def test_parse_from_fixture():
    item = TaskItem.from_file(FIXTURE)
    assert item.id == "aaaaaaaa-0000-0000-0000-000000000001"
    assert item.type == "file"
    assert item.source == "filesystem"
    assert item.priority == "medium"
    assert item.status == "needs_action"


def test_round_trip(tmp_path):
    item = TaskItem.from_file(FIXTURE)
    out = tmp_path / "out.md"
    item.to_file(out)
    item2 = TaskItem.from_file(out)
    assert item.id == item2.id
    assert item.type == item2.type
    assert item.priority == item2.priority
    assert item.status == item2.status


def test_invalid_type_raises():
    with pytest.raises(ValueError, match="Invalid type"):
        TaskItem(id="x", type="INVALID", source="filesystem",
                 priority="medium", status="needs_action")


def test_invalid_status_raises():
    with pytest.raises(ValueError, match="Invalid status"):
        TaskItem(id="x", type="file", source="filesystem",
                 priority="medium", status="INVALID")


def test_created_at_immutable():
    item = TaskItem.from_file(FIXTURE)
    original = item.created_at
    with pytest.raises(ValueError, match="immutable"):
        item.update_frontmatter(created_at="2099-01-01T00:00:00+00:00")
    assert item.created_at == original


def test_updated_at_changes_on_update():
    item = TaskItem.from_file(FIXTURE)
    old_updated = item.updated_at
    item.update_frontmatter(priority="high")
    assert item.updated_at != old_updated
    assert item.priority == "high"


def test_classification_defaults_to_local_only():
    item = TaskItem(id="x", type="file", source="filesystem",
                    priority="medium", status="needs_action")
    assert item.classification == "local_only"
