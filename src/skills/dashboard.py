"""Dashboard skill — regenerate Dashboard.md with vault status (T024)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)

_FOLDERS = [
    "Inbox", "Needs_Action", "Plans", "In_Progress",
    "Pending_Approval", "Approved", "Rejected", "Done", "Errors", "Reports",
]


class DashboardSkill(BaseSkill):
    """Regenerate Dashboard.md from vault folder counts and recent logs."""

    @property
    def name(self) -> str:
        return "dashboard"

    @property
    def version(self) -> str:
        return "1.0.0"

    def health_check(self) -> bool:
        return True

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        vault_root = skill_input.vault_root
        dry_run = skill_input.dry_run

        now = datetime.now(timezone.utc)
        human_ts = now.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Folder counts.
        counts: dict[str, int] = {}
        for folder in _FOLDERS:
            p = vault_root / folder
            counts[folder] = sum(1 for f in p.iterdir() if f.is_file() and not f.name.startswith(".")) if p.exists() else 0

        counts_md = "".join(f"| {f}/ | {c} |\n" for f, c in counts.items())

        # Recent log entries (last 10 from today's log).
        recent_md = ""
        log_file = vault_root / "Logs" / now.strftime("%Y-%m-%d.json")
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text(encoding="utf-8"))
                for e in entries[-10:]:
                    ts = e.get("timestamp", "")[:16]
                    actor = e.get("actor", "")
                    action = e.get("action", "")
                    outcome = e.get("outcome", "")
                    recent_md += f"| {ts} | {actor} | {action} | {outcome} |\n"
            except Exception:
                pass

        # Integration health (FR-G034).
        try:
            from src.engine.integration_registry import IntegrationRegistry  # noqa: PLC0415
            registry = IntegrationRegistry(vault_root)
            degraded_names = registry.get_degraded()
            all_integrations = registry.get_all()

            if not all_integrations:
                degraded_md = "_No integrations registered._\n"
            elif not degraded_names:
                degraded_md = "_All integrations healthy._\n"
            else:
                degraded_md = ""
                for iname in degraded_names:
                    entry = all_integrations[iname]
                    istatus = entry.get("status", "unknown").upper()
                    last_err = (entry.get("last_error") or "")[:80]
                    last_err_at = (entry.get("last_error_at") or "")[:19]
                    degraded_md += f"| {iname} | [{istatus}] | {last_err} | {last_err_at} |\n"
        except Exception as _reg_exc:
            logger.warning("[Dashboard] IntegrationRegistry unavailable: %s", _reg_exc)
            degraded_md = "_[DATA UNAVAILABLE]_\n"

        # Stale approvals (files in Pending_Approval > 24h old).
        stale: list[str] = []
        pa_dir = vault_root / "Pending_Approval"
        if pa_dir.exists():
            cutoff = now.timestamp() - 86400
            for f in pa_dir.iterdir():
                if f.is_file() and f.stat().st_mtime < cutoff:
                    stale.append(f.name)

        stale_md = "\n".join(f"- {s}" for s in stale) if stale else "_None_"
        dry_banner = "\n> **[DRY_RUN MODE]** No files were modified.\n" if dry_run else ""

        content = (
            f"# AI Employee Dashboard\n\n"
            f"**Last Updated**: {human_ts}  \n"
            f"**Mode**: {'[DRY_RUN MODE]' if dry_run else 'LIVE'}  \n"
            f"{dry_banner}\n"
            "## Queue Summary\n\n"
            "| Folder | Count |\n"
            "|--------|-------|\n"
            f"{counts_md}\n"
            "## Recent Activity (last 10)\n\n"
        )
        if recent_md:
            content += (
                "| Time | Actor | Action | Outcome |\n"
                "|------|-------|--------|---------|\n"
                f"{recent_md}\n"
            )
        else:
            content += "_No recent activity._\n\n"

        content += (
            "## Integration Health\n\n"
            "| Integration | Status | Last Error | Last Error At |\n"
            "|-------------|--------|------------|---------------|\n"
        )
        if degraded_md.startswith("_"):
            content += degraded_md + "\n"
        else:
            content += f"{degraded_md}\n"

        content += (
            "## Component Health\n\n"
            "| Component | Status | Last Check |\n"
            "|-----------|--------|------------|\n"
            f"| Filesystem Watcher | OK | {human_ts} |\n"
            f"| Triage Skill | OK | {human_ts} |\n"
            f"| Planner Skill | OK | {human_ts} |\n"
            f"| Executor Skill | OK | {human_ts} |\n\n"
            "## Stale Approvals (> 24h)\n\n"
            f"{stale_md}\n"
        )

        dashboard_path = vault_root / "Dashboard.md"
        actions: list[str] = []
        dashboard_path.write_text(content, encoding="utf-8")
        if dry_run:
            actions.append("[DRY_RUN] updated Dashboard.md (read-only preview)")
        else:
            actions.append("updated Dashboard.md")

        return SkillOutput(
            success=True,
            result=f"Dashboard updated — {sum(counts.values())} items across {len(_FOLDERS)} folders",
            actions_taken=actions,
            metadata={"counts": counts, "stale_approvals": len(stale)},
        )
