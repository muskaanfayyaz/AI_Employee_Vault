"""process_needs_action skill — Bronze tier Agent Skill.

Processes every item sitting in ``Needs_Action/`` by:

1. Reading and analysing the item's markdown content.
2. Creating ``Plans/PLAN_<stem>.md`` with a structured action plan.
3. Moving the processed file(s) to ``Done/``.
4. Regenerating ``Dashboard.md`` with updated vault counts.
5. Appending a structured entry to the daily JSON audit log.

The skill is deliberately self-contained (no external APIs required)
so it can run as part of the Bronze-tier local loop without any cloud
or third-party service dependencies.

Usage (standalone)::

    python -m src.skills.process_needs_action

Or via the skill interface::

    from pathlib import Path
    from src.skills.process_needs_action import ProcessNeedsActionSkill
    from src.skills.base import SkillInput

    skill = ProcessNeedsActionSkill()
    output = skill.safe_execute(SkillInput(vault_root=Path("."), dry_run=False))
    print(output.result)
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.skills.base import BaseSkill, SkillInput, SkillOutput


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Vault folder names (relative to vault_root).
_FOLDER_NEEDS_ACTION = "Needs_Action"
_FOLDER_PLANS = "Plans"
_FOLDER_DONE = "Done"
_FOLDER_LOGS = "Logs"

# Vault folders used in the dashboard summary (in display order).
_DASHBOARD_FOLDERS = [
    "Inbox",
    "Needs_Action",
    "Plans",
    "In_Progress",
    "Pending_Approval",
    "Approved",
    "Rejected",
    "Done",
    "Errors",
    "Reports",
    "Logs",
]

# Simple keyword → priority mapping (highest match wins).
_PRIORITY_KEYWORDS: dict[str, list[str]] = {
    "urgent": ["urgent", "asap", "immediately", "critical", "emergency"],
    "high": ["high priority", "important", "priority", "deadline", "overdue"],
    "low": ["low priority", "when possible", "nice to have", "optional"],
}

# Actions that require human approval based on keywords.
_APPROVAL_KEYWORDS = [
    "approve", "payment", "send email", "publish", "delete", "remove",
    "contact", "invoice", "transfer", "purchase",
]


# ---------------------------------------------------------------------------
# Skill implementation
# ---------------------------------------------------------------------------


class ProcessNeedsActionSkill(BaseSkill):
    """Analyse and process all items in ``Needs_Action/``.

    For each markdown item found it:

    * Parses the YAML front-matter (if present) or treats the file as a
      plain content item.
    * Generates a structured ``Plans/PLAN_<stem>.md`` with contextual
      steps derived from the item content.
    * Moves item files to ``Done/`` (unless dry-run).
    * Regenerates ``Dashboard.md`` with current vault folder counts.
    * Appends an audit log entry to ``Logs/YYYY-MM-DD.json``.
    """

    @property
    def name(self) -> str:
        return "process_needs_action"

    @property
    def version(self) -> str:
        return "1.0.0"

    def health_check(self) -> bool:
        return True

    # ── main entry point ─────────────────────────────────────────────────

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        """Process all items in ``Needs_Action/``.

        Parameters
        ----------
        skill_input:
            ``vault_root`` — path to the vault root (required).
            ``dry_run``   — when ``True`` no files are written or moved.
            ``config``    — optional overrides (unused for now).
        """
        vault_root = skill_input.vault_root.resolve()
        dry_run = skill_input.dry_run

        needs_action_dir = vault_root / _FOLDER_NEEDS_ACTION
        plans_dir = vault_root / _FOLDER_PLANS
        done_dir = vault_root / _FOLDER_DONE
        logs_dir = vault_root / _FOLDER_LOGS

        # Ensure target directories exist.
        for d in (needs_action_dir, plans_dir, done_dir, logs_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Collect candidate items.
        items = _collect_items(needs_action_dir)
        if not items:
            return SkillOutput(
                success=True,
                result="No items found in Needs_Action — nothing to process.",
                actions_taken=["scanned Needs_Action/ (empty)"],
            )

        actions_taken: list[str] = []
        processed: list[dict[str, Any]] = []
        errors: list[str] = []

        for item in items:
            try:
                result = self._process_item(
                    item=item,
                    plans_dir=plans_dir,
                    done_dir=done_dir,
                    logs_dir=logs_dir,
                    dry_run=dry_run,
                )
                processed.append(result)
                actions_taken.extend(result["actions"])
            except Exception as exc:  # noqa: BLE001
                msg = f"Error processing {item['stem']}: {exc}"
                logger.exception(msg)
                errors.append(msg)

        # Regenerate dashboard.
        try:
            dashboard_actions = _regenerate_dashboard(
                vault_root=vault_root,
                processed=processed,
                dry_run=dry_run,
            )
            actions_taken.extend(dashboard_actions)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to regenerate Dashboard.md")
            errors.append(f"Dashboard regeneration failed: {exc}")

        n = len(processed)
        summary = (
            f"Processed {n} item(s) from Needs_Action: "
            + ", ".join(p["stem"] for p in processed)
        )
        if errors:
            summary += f". Errors: {'; '.join(errors)}"

        return SkillOutput(
            success=len(errors) == 0,
            result=summary,
            actions_taken=actions_taken,
            error="; ".join(errors) if errors else None,
            metadata={"processed": processed, "error_count": len(errors)},
        )

    # ── per-item processing ──────────────────────────────────────────────

    def _process_item(
        self,
        *,
        item: dict[str, Any],
        plans_dir: Path,
        done_dir: Path,
        logs_dir: Path,
        dry_run: bool,
    ) -> dict[str, Any]:
        """Full lifecycle for a single Needs_Action item.

        Returns a dict with keys: stem, plan_path, done_paths, actions.
        """
        stem = item["stem"]
        content = item["content"]
        metadata = item["metadata"]
        item_id = metadata.get("id") or str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)

        actions: list[str] = []

        # ── 1. Analyse content ────────────────────────────────────────
        analysis = _analyse_content(content, metadata)
        logger.info("Analysed '%s': priority=%s, steps=%d",
                    stem, analysis["priority"], len(analysis["steps"]))

        # ── 2. Create PLAN_<stem>.md ──────────────────────────────────
        plan_path = plans_dir / f"PLAN_{stem}.md"
        plan_id = str(uuid.uuid4())

        if dry_run:
            logger.info("[DRY_RUN] Would create: %s", plan_path)
            actions.append(f"[DRY_RUN] would create {plan_path.name}")
        else:
            _write_plan(
                path=plan_path,
                plan_id=plan_id,
                item_id=item_id,
                stem=stem,
                analysis=analysis,
                timestamp=timestamp,
            )
            logger.info("Plan created: %s", plan_path)
            actions.append(f"created Plans/{plan_path.name}")

        # ── 3. Move item files to Done/ ───────────────────────────────
        done_paths: list[Path] = []
        files_to_move = item["files"]

        for src in files_to_move:
            dest = done_dir / src.name
            # Avoid collisions.
            if dest.exists():
                dest = done_dir / f"{item_id[:8]}-{src.name}"

            if dry_run:
                logger.info("[DRY_RUN] Would move: %s → Done/", src.name)
                actions.append(f"[DRY_RUN] would move {src.name} → Done/")
            else:
                shutil.move(str(src), str(dest))
                done_paths.append(dest)
                logger.info("Moved: %s → %s", src.name, dest)
                actions.append(f"moved {src.name} → Done/")

        # ── 4. Log action ─────────────────────────────────────────────
        log_entry: dict[str, Any] = {
            "timestamp": timestamp.isoformat(),
            "actor": "process_needs_action",
            "action": "[DRY_RUN] processed_item" if dry_run else "processed_item",
            "item_id": item_id,
            "from_state": "needs_action",
            "to_state": "done",
            "outcome": "dry_run" if dry_run else "success",
            "dry_run": dry_run,
            "details": {
                "stem": stem,
                "priority": analysis["priority"],
                "requires_approval": analysis["requires_approval"],
                "plan_path": str(plan_path),
                "steps_generated": len(analysis["steps"]),
                "files_moved": [str(p) for p in done_paths],
            },
        }
        if not dry_run:
            _append_audit_log(logs_dir, log_entry, timestamp)
            actions.append(f"logged to Logs/{timestamp.strftime('%Y-%m-%d.json')}")
        else:
            logger.info("[DRY_RUN] Would append audit log entry")
            actions.append("[DRY_RUN] would log audit entry")

        return {
            "stem": stem,
            "item_id": item_id,
            "plan_path": str(plan_path),
            "done_paths": [str(p) for p in done_paths],
            "actions": actions,
            "priority": analysis["priority"],
            "steps": analysis["steps"],
        }


# ---------------------------------------------------------------------------
# Content analysis
# ---------------------------------------------------------------------------


def _analyse_content(
    content: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    """Derive an action plan from item content.

    Returns a dict with:
        - ``priority``: low | medium | high | urgent
        - ``requires_approval``: bool
        - ``summary``: one-sentence description
        - ``steps``: list of step strings
        - ``word_count``: int
    """
    lower = content.lower()
    word_count = len(content.split())

    # Priority from metadata or keyword scan.
    priority = metadata.get("priority", "medium")
    for prio, keywords in _PRIORITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            priority = prio
            break

    # Approval flag.
    requires_approval = metadata.get("requires_approval", False)
    if not requires_approval:
        requires_approval = any(kw in lower for kw in _APPROVAL_KEYWORDS)

    # Extract title from first heading or filename.
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled Item"

    # Extract existing checkboxes / tasks from content.
    existing_tasks = re.findall(r"- \[ \]\s+(.+)", content)

    # Build contextual plan steps.
    steps = _generate_steps(
        title=title,
        lower_content=lower,
        existing_tasks=existing_tasks,
        requires_approval=requires_approval,
        word_count=word_count,
        metadata=metadata,
    )

    summary = f"Process '{title}' — {priority} priority, {word_count} words"
    if requires_approval:
        summary += " (requires approval)"

    return {
        "title": title,
        "priority": priority,
        "requires_approval": requires_approval,
        "summary": summary,
        "steps": steps,
        "word_count": word_count,
    }


def _generate_steps(
    *,
    title: str,
    lower_content: str,
    existing_tasks: list[str],
    requires_approval: bool,
    word_count: int,
    metadata: dict[str, Any],
) -> list[str]:
    """Generate plan steps based on content type and keywords."""
    steps: list[str] = []

    # If the item already has explicit tasks, promote them.
    if existing_tasks:
        steps.extend(existing_tasks[:5])  # cap at 5 inherited tasks

    # Content-type specific steps.
    item_type = metadata.get("type", "file")

    if item_type == "email" or "email" in lower_content:
        steps += [
            "Review email context and sender history",
            "Draft a contextual reply",
            "Route draft to Pending_Approval for review",
        ]
    elif item_type == "message" or "whatsapp" in lower_content:
        steps += [
            "Review message content and sender",
            "Draft response",
            "Route to Pending_Approval",
        ]
    elif any(kw in lower_content for kw in ["invoice", "payment", "amount"]):
        steps += [
            "Review financial details for accuracy",
            "Cross-reference with records",
            "Flag any discrepancies",
            "Route for approval if action required",
        ]
    elif any(kw in lower_content for kw in ["research", "analyse", "analyze", "report"]):
        steps += [
            "Review research material and objectives",
            "Summarise key findings",
            "Identify actionable recommendations",
            "Draft summary report",
        ]
    else:
        # Generic file processing.
        steps += [
            "Review item content thoroughly",
            "Identify required actions and owners",
            "Execute actions or delegate appropriately",
        ]

    # Long documents get an extra review step.
    if word_count > 500:
        steps.insert(0, f"Read full document ({word_count} words) and extract key points")

    # Approval gate step if needed.
    if requires_approval:
        steps.append("Route to Pending_Approval before any external action")

    # Completion step always last.
    steps.append("Mark item as complete and move to Done")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique_steps: list[str] = []
    for s in steps:
        if s not in seen:
            seen.add(s)
            unique_steps.append(s)

    return unique_steps


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------


def _write_plan(
    *,
    path: Path,
    plan_id: str,
    item_id: str,
    stem: str,
    analysis: dict[str, Any],
    timestamp: datetime,
) -> None:
    """Write a PLAN_<stem>.md file with YAML front-matter and step list."""
    iso = timestamp.isoformat()
    human_ts = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    steps_md = "\n".join(f"- [ ] {s}" for s in analysis["steps"])
    approval_note = (
        "\n> **Approval Required**: One or more steps require human approval "
        "before execution.\n"
        if analysis["requires_approval"]
        else ""
    )

    content = (
        "---\n"
        f"id: {plan_id}\n"
        f"item_id: {item_id}\n"
        f"source_item: {stem}\n"
        f"created_at: {iso}\n"
        f"updated_at: {iso}\n"
        "status: pending\n"
        f"priority: {analysis['priority']}\n"
        f"requires_approval: {str(analysis['requires_approval']).lower()}\n"
        "---\n\n"
        f"# Plan: {analysis['title']}\n\n"
        f"**Created**: {human_ts}  \n"
        f"**Priority**: {analysis['priority']}  \n"
        f"**Item ID**: `{item_id}`  \n\n"
        f"{approval_note}"
        "## Context\n\n"
        f"{analysis['summary']}\n\n"
        "## Steps\n\n"
        f"{steps_md}\n\n"
        "## Expected Outcome\n\n"
        f"Item `{stem}` fully processed and archived in `Done/`.\n"
    )
    path.write_text(content, encoding="utf-8")


def _regenerate_dashboard(
    *,
    vault_root: Path,
    processed: list[dict[str, Any]],
    dry_run: bool,
) -> list[str]:
    """Write an updated Dashboard.md to vault_root.

    Returns a list of action strings.
    """
    timestamp = datetime.now(timezone.utc)
    human_ts = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    actions: list[str] = []

    # Count files per vault folder.
    counts: dict[str, int] = {}
    for folder in _DASHBOARD_FOLDERS:
        folder_path = vault_root / folder
        if folder_path.exists():
            counts[folder] = sum(
                1 for f in folder_path.iterdir()
                if f.is_file() and not f.name.startswith(".")
            )
        else:
            counts[folder] = 0

    # Recent processing summary rows.
    recent_rows = ""
    for p in processed[-10:]:  # last 10
        recent_rows += (
            f"| `{p['stem']}` | {p['priority']} | "
            f"{len(p['steps'])} steps | Done/ |\n"
        )

    dry_run_banner = (
        "\n> **[DRY_RUN MODE]** No files were actually moved or modified.\n"
        if dry_run
        else ""
    )

    counts_rows = ""
    for folder, count in counts.items():
        counts_rows += f"| {folder}/ | {count} |\n"

    content = (
        f"# AI Employee Dashboard\n\n"
        f"**Last Updated**: {human_ts}  \n"
        f"**Skill**: `process_needs_action` v1.0.0  \n"
        f"{dry_run_banner}\n"
        "## Vault Status\n\n"
        "| Folder | Files |\n"
        "|--------|-------|\n"
        f"{counts_rows}\n"
        "## Recent Processing\n\n"
    )

    if recent_rows:
        content += (
            "| Item | Priority | Plan | Destination |\n"
            "|------|----------|------|-------------|\n"
            f"{recent_rows}\n"
        )
    else:
        content += "_No items processed in this run._\n\n"

    content += (
        "## System Health\n\n"
        "| Component | Status |\n"
        "|-----------|--------|\n"
        "| Filesystem Watcher | ✅ operational |\n"
        "| process_needs_action Skill | ✅ operational |\n"
        f"| Last Run | {human_ts} |\n"
    )

    dashboard_path = vault_root / "Dashboard.md"

    if dry_run:
        logger.info("[DRY_RUN] Would write Dashboard.md")
        actions.append("[DRY_RUN] would update Dashboard.md")
    else:
        dashboard_path.write_text(content, encoding="utf-8")
        logger.info("Dashboard.md updated: %s", dashboard_path)
        actions.append("updated Dashboard.md")

    return actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_items(needs_action_dir: Path) -> list[dict[str, Any]]:
    """Scan Needs_Action/ and group files into logical items.

    A "logical item" groups:
    - A metadata file (``<stem>-metadata.md``) with its companion
      content file (``<stem>.md``) if both exist.
    - A standalone ``.md`` file that has no companion metadata.

    Metadata files are identified by the ``-metadata`` suffix.
    Both the content file and the metadata file are included in
    ``item["files"]`` so they are moved together.
    """
    if not needs_action_dir.exists():
        return []

    all_md = {
        f.stem: f
        for f in needs_action_dir.iterdir()
        if f.is_file() and f.suffix == ".md"
    }

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for stem, path in sorted(all_md.items()):
        if stem in seen:
            continue

        if stem.endswith("-metadata"):
            # This IS the metadata file; find companion content file.
            content_stem = stem[: -len("-metadata")]
            content_path = all_md.get(content_stem)

            # Parse metadata front-matter.
            metadata = _parse_front_matter(path)

            # Read content from companion file (or fall back to metadata body).
            if content_path:
                content = content_path.read_text(encoding="utf-8")
                files = [path, content_path]
                seen.add(content_stem)
            else:
                content = _extract_body(path)
                files = [path]
                # Also include any non-.md companion file (e.g. task1.txt).
                for sibling in needs_action_dir.iterdir():
                    if sibling.stem == content_stem and sibling.suffix != ".md" and sibling.is_file():
                        files.append(sibling)
                        break

            items.append(
                {
                    "stem": content_stem,  # always name after the item, not the metadata file
                    "metadata": metadata,
                    "content": content,
                    "files": files,
                }
            )
            seen.add(stem)

        else:
            # Standalone content file — check if a metadata companion exists.
            meta_stem = f"{stem}-metadata"
            if meta_stem in all_md:
                # Will be processed when we hit the metadata file.
                seen.add(stem)
                continue

            # True standalone — treat the file as both content and metadata.
            content = path.read_text(encoding="utf-8")
            metadata = _parse_front_matter(path)
            items.append(
                {
                    "stem": stem,
                    "metadata": metadata,
                    "content": content,
                    "files": [path],
                }
            )
            seen.add(stem)

    return items


def _parse_front_matter(path: Path) -> dict[str, Any]:
    """Extract YAML front-matter from a markdown file.

    Returns an empty dict if the file has no front-matter or parsing
    fails (no ``pyyaml`` dependency required — simple key:value parse).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    if not text.startswith("---"):
        return {}

    try:
        end = text.index("---", 3)
    except ValueError:
        return {}

    fm_block = text[3:end].strip()
    result: dict[str, Any] = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _extract_body(path: Path) -> str:
    """Return the markdown body (after front-matter) of a file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    if not text.startswith("---"):
        return text

    try:
        end = text.index("---", 3)
        return text[end + 3:].strip()
    except ValueError:
        return text


def _append_audit_log(
    logs_dir: Path,
    entry: dict[str, Any],
    timestamp: datetime,
) -> None:
    """Append *entry* to the daily JSON audit log array."""
    log_file = logs_dir / timestamp.strftime("%Y-%m-%d.json")
    entries: list[dict[str, Any]] = []

    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        except (json.JSONDecodeError, OSError):
            entries = []

    entries.append(entry)
    log_file.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.debug("Audit log updated: %s", log_file)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def _resolve_dry_run() -> bool:
    """Read DRY_RUN from config or environment (default: True for safety)."""
    try:
        from src.config import DRY_RUN  # type: ignore[import]
        return bool(DRY_RUN)
    except ImportError:
        return os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    vault_root = Path(os.getenv("VAULT_ROOT", str(Path.cwd()))).resolve()
    dry = _resolve_dry_run()

    logger.info(
        "process_needs_action | vault=%s | dry_run=%s",
        vault_root,
        dry,
    )

    skill = ProcessNeedsActionSkill()
    skill_input = SkillInput(vault_root=vault_root, dry_run=dry)
    output = skill.safe_execute(skill_input)

    print("\n" + "=" * 60)
    print(f"Result  : {'✅ SUCCESS' if output.success else '❌ FAILED'}")
    print(f"Summary : {output.result}")
    print(f"Actions ({len(output.actions_taken)}):")
    for a in output.actions_taken:
        print(f"  • {a}")
    if output.error:
        print(f"Error   : {output.error}")
    print("=" * 60)
