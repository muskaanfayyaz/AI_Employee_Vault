"""UpdatesMergeSkill — merge cloud Updates/ into Dashboard.md (Platinum Tier).

Workflow
--------
1. Cloud agent completes a task → writes output to ``Updates/<file>.md``.
2. Git sync pushes ``Updates/`` to the remote.
3. Local agent pulls from remote → sees new files in ``Updates/``.
4. Local agent runs ``UpdatesMergeSkill``:
   a. Reads every ``*.md`` file in ``Updates/``.
   b. Appends a summary of each to the ``## Cloud Updates`` section of
      ``Dashboard.md`` (protected by ``DashboardLock``).
   c. Moves processed files from ``Updates/`` to ``Done/``.

This keeps the Dashboard authoritative on the local machine while the
cloud agent can write outputs without needing Dashboard write access.

Usage::

    from src.skills.updates_merge import UpdatesMergeSkill
    from src.skills.base import SkillInput

    skill = UpdatesMergeSkill()
    out = skill.safe_execute(SkillInput(vault_root=Path("/vault"), dry_run=False))
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from src.engine.dashboard_lock import DashboardLock
from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)


class UpdatesMergeSkill(BaseSkill):
    """Merge cloud agent outputs from ``Updates/`` into ``Dashboard.md``."""

    @property
    def name(self) -> str:
        return "updates_merge"

    @property
    def version(self) -> str:
        return "1.0.0"

    def health_check(self) -> bool:
        return True

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        vault_root = skill_input.vault_root
        dry_run = skill_input.dry_run

        updates_dir = vault_root / "Updates"
        done_dir = vault_root / "Done"
        dashboard_path = vault_root / "Dashboard.md"

        if not updates_dir.exists():
            return SkillOutput(
                success=True,
                result="Updates/ does not exist — nothing to merge",
            )

        pending = sorted(
            f for f in updates_dir.iterdir()
            if f.is_file() and f.suffix == ".md" and not f.name.startswith(".")
        )

        if not pending:
            return SkillOutput(
                success=True,
                result="No pending cloud updates to merge",
            )

        logger.info("UpdatesMergeSkill: %d cloud update(s) to merge", len(pending))

        summaries: list[str] = []
        for update_file in pending:
            content = _read_safe(update_file)
            title = _extract_title(content, update_file.name)
            first_para = _extract_first_paragraph(content)
            ts = datetime.fromtimestamp(update_file.stat().st_mtime, tz=timezone.utc)
            ts_str = ts.strftime("%Y-%m-%d %H:%M UTC")
            summaries.append(f"| {ts_str} | {update_file.name} | {title} | {first_para} |")

        # Build the update block to inject into Dashboard.md.
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        update_block = (
            f"\n## Cloud Updates (merged {now_str})\n\n"
            "| Received | File | Title | Summary |\n"
            "|----------|------|-------|---------|\n"
            + "\n".join(summaries)
            + "\n"
        )

        # Acquire dashboard lock and write.
        lock = DashboardLock(vault_root)
        actions: list[str] = []

        with lock as acquired:
            if not acquired:
                return SkillOutput(
                    success=False,
                    result="Could not acquire Dashboard lock — will retry next cycle",
                    error="dashboard_lock_unavailable",
                )

            if dry_run:
                logger.info("[DRY_RUN] Would append cloud updates to Dashboard.md:\n%s", update_block)
                actions.append(f"[DRY_RUN] would append {len(summaries)} update(s) to Dashboard.md")
            else:
                _append_or_replace_section(dashboard_path, "## Cloud Updates", update_block)
                actions.append(f"Appended {len(summaries)} cloud update(s) to Dashboard.md")

        # Move processed files from Updates/ to Done/.
        for update_file in pending:
            dest = done_dir / update_file.name
            if dry_run:
                logger.info("[DRY_RUN] Would move %s → Done/", update_file.name)
                actions.append(f"[DRY_RUN] would archive {update_file.name} → Done/")
            else:
                try:
                    done_dir.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        dest = done_dir / f"{update_file.stem}-{os.urandom(4).hex()}{update_file.suffix}"
                    update_file.rename(dest)
                    actions.append(f"Archived {update_file.name} → Done/")
                except OSError as exc:
                    logger.warning("Could not archive %s: %s", update_file.name, exc)

        return SkillOutput(
            success=True,
            result=f"Merged {len(summaries)} cloud update(s) into Dashboard.md",
            actions_taken=actions,
            metadata={"updates_merged": len(summaries)},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _extract_first_paragraph(content: str) -> str:
    in_frontmatter = False
    found_frontmatter_end = False
    buffer: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()

        # Skip YAML front-matter.
        if not found_frontmatter_end:
            if stripped == "---":
                in_frontmatter = not in_frontmatter
                if not in_frontmatter:
                    found_frontmatter_end = True
                continue
            if in_frontmatter:
                continue

        # Skip heading lines.
        if stripped.startswith("#"):
            if buffer:
                break
            continue

        if stripped:
            buffer.append(stripped)
        elif buffer:
            break  # end of first paragraph

    text = " ".join(buffer).strip()
    return (text[:120] + "…") if len(text) > 120 else text


def _append_or_replace_section(dashboard_path: Path, section_heading: str, new_block: str) -> None:
    """Replace existing *section_heading* block or append *new_block* to dashboard."""
    if not dashboard_path.exists():
        dashboard_path.write_text(new_block, encoding="utf-8")
        return

    content = dashboard_path.read_text(encoding="utf-8")

    # Find and replace the existing section if present.
    lines = content.splitlines(keepends=True)
    start_idx: int | None = None
    end_idx: int | None = None

    for i, line in enumerate(lines):
        if line.strip().startswith(section_heading):
            start_idx = i
        elif start_idx is not None and line.startswith("## ") and i > start_idx:
            end_idx = i
            break

    if start_idx is not None:
        end_idx = end_idx or len(lines)
        new_lines = lines[:start_idx] + [new_block] + lines[end_idx:]
        dashboard_path.write_text("".join(new_lines), encoding="utf-8")
    else:
        # Append at end.
        with dashboard_path.open("a", encoding="utf-8") as fh:
            fh.write(new_block)
