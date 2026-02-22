"""Tests for src/engine/state_machine.py (T011)."""
import pytest
from pathlib import Path
from src.engine.state_machine import move, InvalidTransitionError, VALID_TRANSITIONS


# ── Valid transitions ─────────────────────────────────────────────────────────

VALID_CASES = [
    ("Inbox", "Needs_Action"),
    ("Inbox", "Errors"),
    ("Needs_Action", "Plans"),
    ("Needs_Action", "In_Progress"),
    ("Needs_Action", "Errors"),
    ("Plans", "In_Progress"),
    ("Plans", "Errors"),
    ("In_Progress", "Done"),
    ("In_Progress", "Errors"),
    ("Pending_Approval", "Approved"),
    ("Pending_Approval", "Rejected"),
]


@pytest.mark.parametrize("from_folder,to_folder", VALID_CASES)
def test_valid_transition_dry_run(tmp_path, from_folder, to_folder):
    src = tmp_path / from_folder / "item.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("test")
    dest = move(src, from_folder, to_folder, dry_run=True)
    assert src.exists()  # not actually moved
    assert dest.parent.name == to_folder


# ── Invalid transitions ───────────────────────────────────────────────────────

INVALID_CASES = [
    ("Done", "Inbox"),
    ("Done", "Needs_Action"),
    ("Inbox", "Done"),
    ("Needs_Action", "Approved"),
    ("Approved", "Done"),
]


@pytest.mark.parametrize("from_folder,to_folder", INVALID_CASES)
def test_invalid_transition_raises(tmp_path, from_folder, to_folder):
    src = tmp_path / from_folder / "item.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("test")
    with pytest.raises(InvalidTransitionError):
        move(src, from_folder, to_folder, dry_run=True)


# ── DRY_RUN ───────────────────────────────────────────────────────────────────

def test_dry_run_does_not_move_file(tmp_path):
    src = tmp_path / "Inbox" / "item.md"
    src.parent.mkdir()
    src.write_text("test")
    move(src, "Inbox", "Needs_Action", dry_run=True)
    assert src.exists()
    assert not (tmp_path / "Needs_Action" / "item.md").exists()


# ── Live move ─────────────────────────────────────────────────────────────────

def test_live_move_is_atomic(tmp_path):
    src = tmp_path / "Inbox" / "item.md"
    src.parent.mkdir()
    src.write_text("content")
    dest = move(src, "Inbox", "Needs_Action", dry_run=False)
    assert not src.exists()
    assert dest.exists()
    assert dest.read_text() == "content"


def test_unknown_source_folder_raises(tmp_path):
    src = tmp_path / "UNKNOWN" / "item.md"
    src.parent.mkdir()
    src.write_text("x")
    with pytest.raises(InvalidTransitionError, match="Unknown source folder"):
        move(src, "UNKNOWN", "Done", dry_run=True)
