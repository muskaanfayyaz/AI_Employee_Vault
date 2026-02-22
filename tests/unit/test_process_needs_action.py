"""Unit tests for src/skills/process_needs_action.py."""
import json
from pathlib import Path

import pytest

from src.skills.base import SkillInput
from src.skills.process_needs_action import (
    ProcessNeedsActionSkill,
    _analyse_content,
    _collect_items,
    _generate_steps,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def vault(tmp_path):
    """Minimal vault with required folders."""
    for folder in ("Needs_Action", "Plans", "Done", "Logs"):
        (tmp_path / folder).mkdir()
    return tmp_path


@pytest.fixture()
def skill():
    return ProcessNeedsActionSkill()


# ── _analyse_content ──────────────────────────────────────────────────────────

def test_analyse_content_default_priority():
    result = _analyse_content("Some generic content.", {})
    assert result["priority"] == "medium"
    assert isinstance(result["steps"], list)
    assert len(result["steps"]) >= 1


def test_analyse_content_urgent_keyword():
    result = _analyse_content("This is URGENT — need it ASAP.", {})
    assert result["priority"] == "urgent"


def test_analyse_content_requires_approval_keyword():
    result = _analyse_content("Please send email to the client.", {})
    assert result["requires_approval"] is True


def test_analyse_content_requires_approval_metadata():
    result = _analyse_content("Regular content.", {"requires_approval": True})
    assert result["requires_approval"] is True


def test_analyse_content_metadata_priority_overridden_by_keyword():
    # Keyword "urgent" wins over metadata priority "low".
    result = _analyse_content("Urgent task!", {"priority": "low"})
    assert result["priority"] == "urgent"


def test_analyse_content_extracts_existing_tasks():
    content = "Some text.\n- [ ] Do thing A\n- [ ] Do thing B\n"
    result = _analyse_content(content, {})
    assert "Do thing A" in result["steps"]
    assert "Do thing B" in result["steps"]


def test_analyse_content_long_doc_gets_read_step():
    long_content = "word " * 600
    result = _analyse_content(long_content, {})
    assert any("Read full document" in s for s in result["steps"])


# ── _collect_items ────────────────────────────────────────────────────────────

def test_collect_items_empty_dir(tmp_path):
    na = tmp_path / "Needs_Action"
    na.mkdir()
    assert _collect_items(na) == []


def test_collect_items_standalone_md(tmp_path):
    na = tmp_path / "Needs_Action"
    na.mkdir()
    f = na / "my_task.md"
    f.write_text("# My Task\nDo something.", encoding="utf-8")
    items = _collect_items(na)
    assert len(items) == 1
    assert items[0]["stem"] == "my_task"
    assert f in items[0]["files"]


def test_collect_items_metadata_with_md_companion(tmp_path):
    na = tmp_path / "Needs_Action"
    na.mkdir()
    meta = na / "task1-metadata.md"
    meta.write_text("---\nid: abc\n---\n# Body", encoding="utf-8")
    content = na / "task1.md"
    content.write_text("# Task 1\nDo it.", encoding="utf-8")

    items = _collect_items(na)
    assert len(items) == 1
    assert items[0]["stem"] == "task1"
    assert meta in items[0]["files"]
    assert content in items[0]["files"]


def test_collect_items_metadata_with_txt_companion(tmp_path):
    """Non-.md companion file is included in the files list for moving."""
    na = tmp_path / "Needs_Action"
    na.mkdir()
    meta = na / "task1-metadata.md"
    meta.write_text("---\nid: abc\n---\n# Body\n- [ ] Review", encoding="utf-8")
    txt = na / "task1.txt"
    txt.write_text("raw task content", encoding="utf-8")

    items = _collect_items(na)
    assert len(items) == 1
    assert items[0]["stem"] == "task1"
    assert meta in items[0]["files"]
    assert txt in items[0]["files"]


# ── ProcessNeedsActionSkill.execute — dry_run ─────────────────────────────────

def test_execute_dry_run_does_not_move_files(vault, skill):
    item = vault / "Needs_Action" / "note.md"
    item.write_text("# Note\nReview this.", encoding="utf-8")

    out = skill.safe_execute(SkillInput(vault_root=vault, dry_run=True))

    assert out.success
    assert item.exists(), "File must NOT move in dry_run mode"
    assert not (vault / "Plans" / "PLAN_note.md").exists()
    assert any("[DRY_RUN]" in a for a in out.actions_taken)


# ── ProcessNeedsActionSkill.execute — live ────────────────────────────────────

def test_execute_live_creates_plan(vault, skill):
    item = vault / "Needs_Action" / "note.md"
    item.write_text("# Note\nReview this.", encoding="utf-8")

    out = skill.safe_execute(SkillInput(vault_root=vault, dry_run=False))

    assert out.success
    plan = vault / "Plans" / "PLAN_note.md"
    assert plan.exists(), "Plan file must be created"
    plan_text = plan.read_text()
    assert "## Steps" in plan_text


def test_execute_live_moves_item_to_done(vault, skill):
    item = vault / "Needs_Action" / "note.md"
    item.write_text("# Note\nDo something.", encoding="utf-8")

    skill.safe_execute(SkillInput(vault_root=vault, dry_run=False))

    assert not item.exists(), "Item must be moved out of Needs_Action"
    assert any((vault / "Done").iterdir()), "Item must appear in Done/"


def test_execute_live_writes_audit_log(vault, skill):
    item = vault / "Needs_Action" / "note.md"
    item.write_text("# Note\nLog this.", encoding="utf-8")

    skill.safe_execute(SkillInput(vault_root=vault, dry_run=False))

    logs = list((vault / "Logs").glob("*.json"))
    assert logs, "Audit log must be created"
    entries = json.loads(logs[0].read_text())
    assert isinstance(entries, list)
    assert len(entries) >= 1
    assert entries[0]["actor"] == "process_needs_action"


def test_execute_live_updates_dashboard(vault, skill):
    item = vault / "Needs_Action" / "note.md"
    item.write_text("# Note\nUpdate dashboard.", encoding="utf-8")

    skill.safe_execute(SkillInput(vault_root=vault, dry_run=False))

    dashboard = vault / "Dashboard.md"
    assert dashboard.exists()
    assert "process_needs_action" in dashboard.read_text()


def test_execute_empty_needs_action(vault, skill):
    out = skill.safe_execute(SkillInput(vault_root=vault, dry_run=False))
    assert out.success
    assert "empty" in out.result.lower() or "nothing" in out.result.lower()


def test_execute_txt_companion_moved_to_done(vault, skill):
    """task1.txt companion must be moved alongside task1-metadata.md."""
    meta = vault / "Needs_Action" / "task1-metadata.md"
    meta.write_text("---\nid: abc\n---\n# Body\n- [ ] Review file content\n", encoding="utf-8")
    txt = vault / "Needs_Action" / "task1.txt"
    txt.write_text("raw task content", encoding="utf-8")

    skill.safe_execute(SkillInput(vault_root=vault, dry_run=False))

    assert not txt.exists(), "task1.txt must be moved to Done/"
    assert not meta.exists(), "task1-metadata.md must be moved to Done/"
    assert (vault / "Plans" / "PLAN_task1.md").exists()


# ── Skill metadata ────────────────────────────────────────────────────────────

def test_skill_name(skill):
    assert skill.name == "process_needs_action"


def test_skill_version(skill):
    assert skill.version == "1.0.0"


def test_health_check(skill):
    assert skill.health_check() is True
