"""CEO Briefing Skill — generate weekly executive briefing (FR-G016/FR-G017).

Reads:
    - Business_Goals.md          — strategic context and current priorities
    - Accounting/*.md            — revenue, invoice, and payment summaries
    - Done/                      — tasks completed during the review period
    - Needs_Action/, In_Progress/, Pending_Approval/, Approved/
                                 — current pipeline (bottleneck detection)
    - Logs/YYYY-MM-DD.json       — approval ratios, errors, and Odoo/social events
    - Errors/                    — unresolved failures
    - Logs/RalphWiggum_Review*.json — self-improvement insights (if available)

Writes:
    - Reports/CEO_Briefing_YYYY-MM-DD.md

The briefing includes:
    1. Period Summary
    2. Tasks Completed
    3. Current Pipeline & Bottlenecks
    4. Errors & Failures
    5. Approval Summary
    6. Revenue & Financial Activity
    7. Social Media Activity
    8. Subscription Health
    9. Ralph Wiggum Insights
    10. Proactive Suggestions

All sections degrade gracefully: if a data source is unavailable, the
section shows a [DATA UNAVAILABLE] notice instead of raising an error
(FR-G017 requirement).

DRY_RUN=true: renders the full briefing but does NOT write to Reports/.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)

# ── Data containers ──────────────────────────────────────────────────────────

@dataclass
class _LogSummary:
    total_actions: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    dry_runs: int = 0
    approval_requests: int = 0
    approval_approved: int = 0
    approval_rejected: int = 0
    odoo_events: list[dict[str, Any]] = field(default_factory=list)
    social_events: list[dict[str, Any]] = field(default_factory=list)
    ralph_events: list[dict[str, Any]] = field(default_factory=list)
    actors: dict[str, int] = field(default_factory=dict)
    slowest_ms: int = 0

@dataclass
class _AccountingData:
    available: bool = False
    raw_sections: list[str] = field(default_factory=list)
    total_invoiced: float = 0.0
    total_paid: float = 0.0
    invoice_count: int = 0
    payment_count: int = 0
    overdue_count: int = 0
    currency: str = "USD"

@dataclass
class _SubscriptionData:
    available: bool = False
    total: int = 0
    overdue: int = 0
    at_risk_amount: float = 0.0
    anomalies: list[dict[str, Any]] = field(default_factory=list)


# ── Skill ────────────────────────────────────────────────────────────────────

class CeoBriefingSkill(BaseSkill):
    """Generate the weekly CEO Briefing from vault data and audit logs."""

    @property
    def name(self) -> str:
        return "generate_ceo_briefing"

    @property
    def version(self) -> str:
        return "1.0.0"

    def health_check(self) -> bool:
        return True

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        vault_root = skill_input.vault_root
        dry_run = skill_input.dry_run
        config = skill_input.config

        period_days: int = int(config.get("period_days", 7))
        currency: str = str(config.get("currency", "USD"))
        report_dir: Path = vault_root / config.get("report_dir", "Reports")

        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=period_days)
        date_str = now.strftime("%Y-%m-%d")

        logger.info(
            "generate_ceo_briefing: period=%d days (%s → %s) dry_run=%s",
            period_days,
            period_start.strftime("%Y-%m-%d"),
            date_str,
            dry_run,
        )

        # ── Collect all data sources ─────────────────────────────────

        business_goals = _load_business_goals(vault_root)
        done_tasks = _collect_folder_items(vault_root / "Done", period_start)
        pending_tasks = _collect_folder_items(vault_root / "Needs_Action")
        in_progress = _collect_folder_items(vault_root / "In_Progress")
        pending_approval = _collect_folder_items(vault_root / "Pending_Approval")
        errors = _collect_folder_items(vault_root / "Errors")
        log_summary = _read_log_summary(vault_root / "Logs", period_start, now)
        accounting = _read_accounting(vault_root / "Accounting", currency)
        subscriptions = _extract_subscription_data(log_summary)
        ralph_insights = _read_ralph_wiggum_insights(vault_root / "Logs", period_start)

        # ── Detect bottlenecks ────────────────────────────────────────

        bottlenecks = _detect_bottlenecks(
            pending_tasks, in_progress, pending_approval, errors, log_summary
        )

        # ── Generate proactive suggestions ───────────────────────────

        suggestions = _generate_suggestions(
            done_tasks=done_tasks,
            pending_approval=pending_approval,
            errors=errors,
            log_summary=log_summary,
            accounting=accounting,
            subscriptions=subscriptions,
            bottlenecks=bottlenecks,
            business_goals=business_goals,
        )

        # ── Render briefing ──────────────────────────────────────────

        briefing = _render_briefing(
            now=now,
            period_start=period_start,
            period_days=period_days,
            dry_run=dry_run,
            business_goals=business_goals,
            done_tasks=done_tasks,
            pending_tasks=pending_tasks,
            in_progress=in_progress,
            pending_approval=pending_approval,
            errors=errors,
            log_summary=log_summary,
            accounting=accounting,
            subscriptions=subscriptions,
            ralph_insights=ralph_insights,
            bottlenecks=bottlenecks,
            suggestions=suggestions,
        )

        # ── Write report ─────────────────────────────────────────────

        report_path = report_dir / f"CEO_Briefing_{date_str}.md"
        actions: list[str] = []

        if dry_run:
            logger.info("[DRY_RUN] CEO Briefing would be written to %s", report_path)
            actions.append(f"[DRY_RUN] would write {report_path.name}")
        else:
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path.write_text(briefing, encoding="utf-8")
            logger.info("CEO Briefing written to %s (%d chars)", report_path, len(briefing))
            actions.append(f"written Reports/{report_path.name}")

        return SkillOutput(
            success=True,
            result=(
                f"CEO Briefing {'previewed' if dry_run else 'generated'}: "
                f"{len(done_tasks)} done, {len(errors)} errors, "
                f"{len(suggestions)} suggestions"
            ),
            actions_taken=actions,
            metadata={
                "report_path": str(report_path),
                "period_days": period_days,
                "done_count": len(done_tasks),
                "error_count": len(errors),
                "suggestion_count": len(suggestions),
                "dry_run": dry_run,
            },
        )


# ── Data loaders ─────────────────────────────────────────────────────────────

def _load_business_goals(vault_root: Path) -> str:
    """Return the content of Business_Goals.md, or a notice if missing."""
    path = vault_root / "Business_Goals.md"
    if not path.exists():
        return "_Business_Goals.md not found. Create this file in the vault root to give the AI context about your strategic priorities._"
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.warning("Could not read Business_Goals.md: %s", exc)
        return f"[DATA UNAVAILABLE — could not read Business_Goals.md: {exc}]"


def _collect_folder_items(
    folder: Path, since: datetime | None = None
) -> list[dict[str, str]]:
    """Return metadata dicts for all markdown files in a vault folder.

    If *since* is provided, only files modified on or after that datetime
    are included (used to filter Done/ to the review period).
    """
    if not folder.exists():
        return []
    items: list[dict[str, str]] = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix != ".md" or f.name.startswith("."):
            continue
        if since is not None:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < since:
                continue
        # Extract a title from the filename and a quick frontmatter peek.
        title = _item_title(f)
        items.append({"name": f.name, "title": title, "path": str(f)})
    return items


def _item_title(path: Path) -> str:
    """Return a human title from the first heading or the filename stem."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:500]
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return path.stem.replace("-", " ").replace("_", " ")


def _read_log_summary(
    logs_dir: Path, period_start: datetime, now: datetime
) -> _LogSummary:
    """Scan all daily JSON logs in the period and return aggregate stats."""
    summary = _LogSummary()
    if not logs_dir.exists():
        return summary

    current = period_start.date()
    end = now.date()
    while current <= end:
        log_file = logs_dir / f"{current.isoformat()}.json"
        if log_file.exists():
            try:
                entries: list[dict[str, Any]] = json.loads(
                    log_file.read_text(encoding="utf-8")
                )
                for e in entries:
                    _parse_log_entry(e, summary)
            except Exception as exc:
                logger.warning("Could not parse log %s: %s", log_file.name, exc)
        current += timedelta(days=1)

    return summary


def _parse_log_entry(e: dict[str, Any], s: _LogSummary) -> None:
    outcome = e.get("outcome", "")
    actor = e.get("actor", "unknown")
    integration = e.get("integration", "")

    s.total_actions += 1
    s.actors[actor] = s.actors.get(actor, 0) + 1

    if outcome == "success":
        s.successes += 1
    elif outcome in ("failure", "error"):
        s.failures += 1
    elif outcome == "retry":
        s.retries += 1
    elif outcome == "dry_run":
        s.dry_runs += 1
    elif outcome == "approval_pending":
        s.approval_requests += 1

    # Approvals
    approval = e.get("approval", {})
    if isinstance(approval, dict):
        status = approval.get("status", "")
        if status == "approved":
            s.approval_approved += 1
        elif status == "rejected":
            s.approval_rejected += 1
        elif status == "pending":
            s.approval_requests += 1

    # Duration tracking
    dur = e.get("duration_ms", 0)
    if isinstance(dur, (int, float)) and dur > s.slowest_ms:
        s.slowest_ms = int(dur)

    # Integration-specific events
    operation = e.get("operation", "")
    if integration == "odoo" or "odoo" in actor.lower():
        s.odoo_events.append({
            "timestamp": e.get("timestamp", ""),
            "operation": operation,
            "outcome": outcome,
            "details": str(e.get("details", ""))[:120],
        })
    if any(p in (integration + actor).lower() for p in ["linkedin", "facebook", "instagram", "twitter", "social"]):
        s.social_events.append({
            "timestamp": e.get("timestamp", ""),
            "operation": operation,
            "outcome": outcome,
            "details": str(e.get("details", ""))[:120],
        })
    if e.get("ralph_wiggum_tag"):
        s.ralph_events.append(e)


def _read_accounting(accounting_dir: Path, currency: str) -> _AccountingData:
    """Parse all markdown files in the Accounting/ directory for financial data."""
    data = _AccountingData(currency=currency)
    if not accounting_dir.exists():
        return data

    data.available = True
    invoice_re = re.compile(r"invoice[^\d]*(\d[\d,\.]+)", re.IGNORECASE)
    payment_re = re.compile(r"payment[^\d]*(\d[\d,\.]+)", re.IGNORECASE)
    overdue_re = re.compile(r"overdue", re.IGNORECASE)

    for f in sorted(accounting_dir.iterdir()):
        if not f.is_file() or f.suffix != ".md":
            continue
        try:
            text = f.read_text(encoding="utf-8")
            data.raw_sections.append(f"### {f.stem}\n\n{text[:600].strip()}")
            for m in invoice_re.finditer(text):
                try:
                    data.total_invoiced += float(m.group(1).replace(",", ""))
                    data.invoice_count += 1
                except ValueError:
                    pass
            for m in payment_re.finditer(text):
                try:
                    data.total_paid += float(m.group(1).replace(",", ""))
                    data.payment_count += 1
                except ValueError:
                    pass
            if overdue_re.search(text):
                data.overdue_count += 1
        except Exception as exc:
            logger.warning("Could not read accounting file %s: %s", f.name, exc)

    return data


def _extract_subscription_data(log_summary: _LogSummary) -> _SubscriptionData:
    """Extract subscription anomaly data from Odoo log events."""
    sub = _SubscriptionData()
    for event in log_summary.odoo_events:
        if "subscription" in event.get("operation", "").lower():
            sub.available = True
            details = event.get("details", "")
            m_total = re.search(r"(\d+) subscriptions", details)
            m_anomalies = re.search(r"(\d+) anomal", details)
            if m_total:
                sub.total = max(sub.total, int(m_total.group(1)))
            if m_anomalies:
                sub.overdue = max(sub.overdue, int(m_anomalies.group(1)))
    return sub


def _read_ralph_wiggum_insights(logs_dir: Path, period_start: datetime) -> list[str]:
    """Return summary lines from RalphWiggum review files in the period."""
    insights: list[str] = []
    if not logs_dir.exists():
        return insights
    for f in sorted(logs_dir.glob("RalphWiggum_Review_*.json")):
        try:
            date_str = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
            if date_str:
                file_date = datetime.strptime(date_str.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if file_date < period_start:
                    continue
            entries: list[dict[str, Any]] = json.loads(f.read_text(encoding="utf-8"))
            for e in entries:
                details = str(e.get("details", "")).strip()
                if details and len(details) > 10:
                    insights.append(details[:200])
        except Exception as exc:
            logger.warning("Could not parse Ralph Wiggum file %s: %s", f.name, exc)
    return insights[:10]  # cap at 10 insights


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _detect_bottlenecks(
    pending_tasks: list[dict[str, str]],
    in_progress: list[dict[str, str]],
    pending_approval: list[dict[str, str]],
    errors: list[dict[str, str]],
    log_summary: _LogSummary,
) -> list[str]:
    """Return a list of plain-language bottleneck descriptions."""
    bottlenecks: list[str] = []

    if len(pending_tasks) > 10:
        bottlenecks.append(
            f"**Queue backlog**: {len(pending_tasks)} items in Needs_Action — "
            "processing may be falling behind."
        )
    if len(pending_approval) > 5:
        bottlenecks.append(
            f"**Approval backlog**: {len(pending_approval)} items awaiting human approval — "
            "review and clear to unblock the pipeline."
        )
    if len(errors) > 0:
        bottlenecks.append(
            f"**{len(errors)} item(s) in Errors** — require manual requeue or investigation."
        )
    if log_summary.retries > log_summary.successes * 0.25 and log_summary.retries > 3:
        bottlenecks.append(
            f"**High retry rate**: {log_summary.retries} retries vs "
            f"{log_summary.successes} successes — an external integration may be unstable."
        )
    if log_summary.slowest_ms > 30_000:
        bottlenecks.append(
            f"**Slow operations detected**: slowest action took "
            f"{log_summary.slowest_ms / 1000:.1f}s — check MCP server health."
        )
    if log_summary.approval_rejected > log_summary.approval_approved and log_summary.approval_rejected > 0:
        bottlenecks.append(
            f"**High rejection rate**: {log_summary.approval_rejected} rejections vs "
            f"{log_summary.approval_approved} approvals — AI drafts may need refinement."
        )

    return bottlenecks


def _generate_suggestions(
    done_tasks: list[dict[str, str]],
    pending_approval: list[dict[str, str]],
    errors: list[dict[str, str]],
    log_summary: _LogSummary,
    accounting: _AccountingData,
    subscriptions: _SubscriptionData,
    bottlenecks: list[str],
    business_goals: str,
) -> list[str]:
    """Generate proactive suggestions from collected data."""
    suggestions: list[str] = []

    if len(errors) > 0:
        suggestions.append(
            f"**Resolve {len(errors)} error(s)**: Items in /Errors are blocking the pipeline. "
            "Review each item and requeue or close."
        )
    if len(pending_approval) > 3:
        suggestions.append(
            f"**Clear approval backlog**: {len(pending_approval)} items waiting for your decision. "
            "Spending 5–10 minutes on approvals unblocks the entire pipeline."
        )
    if accounting.available and accounting.overdue_count > 0:
        suggestions.append(
            f"**Follow up on {accounting.overdue_count} overdue invoice(s)**: "
            "These represent revenue not yet collected."
        )
    if accounting.available and accounting.total_invoiced > 0 and accounting.total_paid < accounting.total_invoiced * 0.5:
        collection_rate = (accounting.total_paid / accounting.total_invoiced * 100) if accounting.total_invoiced > 0 else 0
        suggestions.append(
            f"**Low collection rate ({collection_rate:.0f}%)**: Only "
            f"{accounting.currency} {accounting.total_paid:,.2f} collected of "
            f"{accounting.currency} {accounting.total_invoiced:,.2f} invoiced. "
            "Consider sending payment reminders."
        )
    if subscriptions.available and subscriptions.overdue > 0:
        suggestions.append(
            f"**Subscription renewals needed**: {subscriptions.overdue} subscription(s) "
            "are overdue. Run the subscription audit skill for details."
        )
    if log_summary.retries > 5:
        suggestions.append(
            f"**Investigate retry patterns**: {log_summary.retries} retries logged this period. "
            "Check integration health and credential validity."
        )
    if log_summary.total_actions == 0:
        suggestions.append(
            "**System appears idle**: No logged actions this period. "
            "Verify the filesystem watcher and scheduler are running."
        )
    if not accounting.available:
        suggestions.append(
            "**Connect financial data**: Create an Accounting/ folder in the vault "
            "with invoice and payment summaries to enable revenue tracking."
        )
    if not subscriptions.available:
        suggestions.append(
            "**Enable subscription monitoring**: Run the Odoo MCP `analyze_subscriptions` "
            "tool to start tracking subscription health."
        )

    return suggestions


# ── Renderer ─────────────────────────────────────────────────────────────────

def _render_briefing(
    now: datetime,
    period_start: datetime,
    period_days: int,
    dry_run: bool,
    business_goals: str,
    done_tasks: list[dict[str, str]],
    pending_tasks: list[dict[str, str]],
    in_progress: list[dict[str, str]],
    pending_approval: list[dict[str, str]],
    errors: list[dict[str, str]],
    log_summary: _LogSummary,
    accounting: _AccountingData,
    subscriptions: _SubscriptionData,
    ralph_insights: list[str],
    bottlenecks: list[str],
    suggestions: list[str],
) -> str:
    date_str = now.strftime("%Y-%m-%d")
    period_label = f"{period_start.strftime('%Y-%m-%d')} → {date_str}"
    generated_ts = now.strftime("%Y-%m-%d %H:%M UTC")
    dry_banner = "\n> ⚠️ **[DRY_RUN MODE]** — This briefing was generated in dry-run mode. No files were moved or sent.\n" if dry_run else ""

    # Approval ratio
    total_decisions = log_summary.approval_approved + log_summary.approval_rejected
    if total_decisions > 0:
        approval_rate = f"{log_summary.approval_approved / total_decisions * 100:.0f}%"
    else:
        approval_rate = "N/A (no decisions recorded)"

    # Task completion rate
    total_processed = len(done_tasks) + len(errors)
    completion_rate = (
        f"{len(done_tasks) / total_processed * 100:.0f}%"
        if total_processed > 0 else "N/A"
    )

    lines: list[str] = [
        f"# CEO Briefing — {date_str}",
        "",
        f"**Generated**: {generated_ts}",
        f"**Period covered**: {period_label} ({period_days} days)",
        f"**Status**: {'[DRY_RUN]' if dry_run else 'LIVE'}",
        dry_banner,
        "---",
        "",
        "## 1. Strategic Context",
        "",
        business_goals,
        "",
        "---",
        "",
        "## 2. Period Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tasks completed | {len(done_tasks)} |",
        f"| Tasks in queue | {len(pending_tasks)} |",
        f"| In progress | {len(in_progress)} |",
        f"| Pending approval | {len(pending_approval)} |",
        f"| Errors (unresolved) | {len(errors)} |",
        f"| Total actions logged | {log_summary.total_actions} |",
        f"| Completion rate | {completion_rate} |",
        f"| Approval rate | {approval_rate} |",
        "",
        "---",
        "",
        "## 3. Tasks Completed",
        "",
    ]

    if done_tasks:
        lines.append(f"**{len(done_tasks)} task(s) completed this period.**")
        lines.append("")
        for task in done_tasks[:20]:  # cap at 20 for readability
            lines.append(f"- {task['title']}")
        if len(done_tasks) > 20:
            lines.append(f"- _...and {len(done_tasks) - 20} more_")
    else:
        lines.append("_No tasks completed during this period._")

    lines += [
        "",
        "---",
        "",
        "## 4. Current Pipeline & Bottlenecks",
        "",
        f"- **Needs Action**: {len(pending_tasks)} item(s)",
        f"- **In Progress**: {len(in_progress)} item(s)",
        f"- **Pending Approval**: {len(pending_approval)} item(s)",
        "",
    ]

    if bottlenecks:
        lines.append("### Bottlenecks Detected")
        lines.append("")
        for b in bottlenecks:
            lines.append(f"- {b}")
    else:
        lines.append("_No bottlenecks detected — pipeline is flowing normally._")

    if pending_approval:
        lines += ["", "### Items Awaiting Your Approval", ""]
        for item in pending_approval[:10]:
            lines.append(f"- `{item['name']}` — {item['title']}")
        if len(pending_approval) > 10:
            lines.append(f"- _...and {len(pending_approval) - 10} more_")

    lines += [
        "",
        "---",
        "",
        "## 5. Errors & Failures",
        "",
    ]

    if errors:
        lines.append(f"**{len(errors)} unresolved error(s) require attention.**")
        lines.append("")
        for err in errors[:10]:
            lines.append(f"- `{err['name']}` — {err['title']}")
        if len(errors) > 10:
            lines.append(f"- _...and {len(errors) - 10} more (see /Errors folder)_")
    else:
        lines.append("_No unresolved errors. All items processed successfully._")

    lines += [
        "",
        "---",
        "",
        "## 6. Approval Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total approval requests | {log_summary.approval_requests} |",
        f"| Approved | {log_summary.approval_approved} |",
        f"| Rejected | {log_summary.approval_rejected} |",
        f"| Approval rate | {approval_rate} |",
        "",
    ]

    if log_summary.approval_rejected > 0:
        lines.append(
            f"> ⚠️ {log_summary.approval_rejected} request(s) were rejected this period. "
            "Review /Rejected folder to understand why and improve AI drafts."
        )

    # Section 7 — Financial Activity
    lines += [
        "",
        "---",
        "",
        "## 7. Revenue & Financial Activity",
        "",
    ]

    if accounting.available:
        lines += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Invoices detected | {accounting.invoice_count} |",
            f"| Total invoiced | {accounting.currency} {accounting.total_invoiced:,.2f} |",
            f"| Payments recorded | {accounting.payment_count} |",
            f"| Total collected | {accounting.currency} {accounting.total_paid:,.2f} |",
            f"| Overdue entries | {accounting.overdue_count} |",
            "",
        ]
        if log_summary.odoo_events:
            lines.append(f"**{len(log_summary.odoo_events)} Odoo event(s) logged this period.**")
            lines.append("")
            for ev in log_summary.odoo_events[:5]:
                ts = ev.get("timestamp", "")[:16]
                op = ev.get("operation", "")
                lines.append(f"- `{ts}` — `{op}` ({ev.get('outcome', '')})")
            if len(log_summary.odoo_events) > 5:
                lines.append(f"- _...and {len(log_summary.odoo_events) - 5} more_")
    else:
        lines.append(
            "[DATA UNAVAILABLE — Create an `Accounting/` folder in the vault with invoice "
            "and payment markdown summaries, or connect the Odoo MCP server to enable "
            "automatic financial tracking.]"
        )

    # Section 8 — Social Media
    lines += [
        "",
        "---",
        "",
        "## 8. Social Media Activity",
        "",
    ]

    if log_summary.social_events:
        lines.append(f"**{len(log_summary.social_events)} social media event(s) logged this period.**")
        lines.append("")
        for ev in log_summary.social_events[:5]:
            ts = ev.get("timestamp", "")[:16]
            op = ev.get("operation", "")
            lines.append(f"- `{ts}` — `{op}` ({ev.get('outcome', '')})")
        if len(log_summary.social_events) > 5:
            lines.append(f"- _...and {len(log_summary.social_events) - 5} more_")
    else:
        lines.append(
            "[DATA UNAVAILABLE — No social media events logged this period. "
            "Connect LinkedIn, Facebook, Instagram, or Twitter integrations to track activity.]"
        )

    # Section 9 — Subscription Health
    lines += [
        "",
        "---",
        "",
        "## 9. Subscription Health",
        "",
    ]

    if subscriptions.available:
        lines += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total subscriptions analysed | {subscriptions.total} |",
            f"| Overdue / anomalous | {subscriptions.overdue} |",
        ]
        if subscriptions.overdue > 0:
            lines.append("")
            lines.append(
                f"> ⚠️ {subscriptions.overdue} subscription anomaly(ies) detected. "
                "Run `analyze_subscriptions` for full details."
            )
    else:
        lines.append(
            "[DATA UNAVAILABLE — Run the Odoo MCP `analyze_subscriptions` tool to populate "
            "this section. Results are extracted automatically from the audit logs.]"
        )

    # Section 10 — Ralph Wiggum
    lines += [
        "",
        "---",
        "",
        "## 10. Ralph Wiggum Self-Improvement Insights",
        "",
    ]

    if ralph_insights:
        lines.append(f"**{len(ralph_insights)} insight(s) from the self-review loop this period.**")
        lines.append("")
        for insight in ralph_insights:
            lines.append(f"- {insight}")
    else:
        lines.append(
            "_No Ralph Wiggum review ran during this period. "
            "The loop requires 7+ days of logs and runs on a weekly schedule._"
        )

    # Section 11 — Proactive Suggestions
    lines += [
        "",
        "---",
        "",
        "## 11. Proactive Suggestions",
        "",
    ]

    if suggestions:
        for i, suggestion in enumerate(suggestions, 1):
            lines.append(f"{i}. {suggestion}")
    else:
        lines.append("_No actionable suggestions — system is operating well._")

    lines += [
        "",
        "---",
        "",
        f"_Briefing generated by `generate_ceo_briefing` skill v1.0.0 | {generated_ts}_",
        "",
    ]

    return "\n".join(lines)
