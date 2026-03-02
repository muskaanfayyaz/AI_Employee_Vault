"""Ralph Wiggum autonomous loop (FR-G023–FR-G028).

Drives multi-step tasks to completion by running the standard vault
processing pipeline (triage → plan → execute → dashboard) iteratively
until one of the following stop conditions is met:

1. **All items done** — every .md file in the active pipeline folders has
   moved to a terminal folder (Done, Rejected, or Errors) and
   ``loop.stop_when_done`` is ``true``.
2. **Iteration cap** — ``loop.max_iterations`` cycles have completed.

Self-review analysis (FR-G024–G028)
------------------------------------
After the processing loop completes, the loop optionally analyses the
vault audit logs from the past ``self_review.min_log_days`` days and
produces structured improvement proposals:

- Failure rate by integration  (FR-G024)
- Retry rate by operation type (FR-G024)
- Rejection rate for approvals (FR-G024)
- Slow operations              (FR-G024)

Each proposal is written to ``Needs_Action/`` (FR-G025/G026), and a
deduplication guard prevents re-creating proposals that are still
pending in ``Needs_Action/`` or ``Pending_Approval/`` (FR-G028).

When fewer than ``min_log_days`` days of audit logs are available, the
analysis is skipped and a ``[RALPH_WIGGUM][SKIPPED]`` entry is logged
(FR-G023).

Each iteration is logged with a structured JSON entry tagged
``[RALPH_WIGGUM]`` (FR-G027).  A daily review file is written to
``Logs/RalphWiggum_Review_YYYY-MM-DD.json`` on completion.

Concurrent-run protection
-------------------------
On startup the loop writes a lock file at
``Config/.ralph_wiggum.lock``.  If the lock already exists, the loop
logs ``[RALPH_WIGGUM][CONCURRENT_SKIP]`` and exits immediately without
running — preventing overlapping executions from a scheduling glitch.
The lock is always removed in the ``finally`` block.

Usage (programmatic)::

    from src.engine.ralph_wiggum_loop import RalphWiggumLoop

    loop = RalphWiggumLoop(vault_root=vault_root, dry_run=dry_run)
    result = loop.run(config)  # config = parsed ralph_wiggum.yaml dict

Usage (CLI)::

    python -m src.main --ralph
    python -m src.main --ralph --dry-run
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_TAG = "[RALPH_WIGGUM]"

# Default active-folder list (mirrors loop.active_folders in the YAML).
_DEFAULT_ACTIVE_FOLDERS = [
    "Needs_Action",
    "Plans",
    "In_Progress",
    "Pending_Approval",
    "Approved",
]


class RalphWiggumLoop:
    """Autonomous run-until-done processing loop.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root directory.
    dry_run:
        When ``True``, processing cycles run in dry-run mode: no vault
        files are moved and no writes are committed, but all logic and
        logging execute normally.
    """

    def __init__(self, vault_root: Path, dry_run: bool = False) -> None:
        self._vault_root = vault_root
        self._dry_run = dry_run

    # ── public API ────────────────────────────────────────────────────────────

    def run(self, config: dict | None = None) -> dict:
        """Execute the autonomous loop.

        Parameters
        ----------
        config:
            Parsed contents of ``Config/ralph_wiggum.yaml``.  Only the
            ``loop`` and ``logging`` sections are used here; the
            ``self_review`` section is reserved for future skill use.
            Defaults are applied for any missing keys.

        Returns
        -------
        dict
            Summary containing:

            - ``iterations`` — number of cycles completed.
            - ``stop_reason`` — one of ``"all_items_done"``,
              ``"max_iterations_reached"``, or ``"concurrent_skip"``.
            - ``items_remaining`` — active items still in the pipeline
              when the loop exited (0 means fully complete).
        """
        cfg = config or {}
        loop_cfg = cfg.get("loop", {})
        log_cfg = cfg.get("logging", {})

        max_iterations: int = int(loop_cfg.get("max_iterations", 10))
        stop_when_done: bool = bool(loop_cfg.get("stop_when_done", True))
        interval: float = float(loop_cfg.get("iteration_interval_seconds", 30))
        active_folders: list[str] = loop_cfg.get("active_folders", _DEFAULT_ACTIVE_FOLDERS)
        log_each: bool = bool(log_cfg.get("log_each_iteration", True))
        review_log_dir: str = log_cfg.get("review_log_dir", "Logs")
        review_log_prefix: str = log_cfg.get("review_log_prefix", "RalphWiggum_Review")

        logger.info(
            "%s Starting autonomous loop | max_iterations=%d | stop_when_done=%s"
            " | interval=%ss | dry_run=%s",
            _TAG, max_iterations, stop_when_done, interval, self._dry_run,
        )

        # ── Concurrent-run guard ──────────────────────────────────────────────
        lock_file = self._vault_root / "Config" / ".ralph_wiggum.lock"
        if lock_file.exists():
            logger.warning(
                "%s[CONCURRENT_SKIP] Lock file present — another run may be active: %s",
                _TAG, lock_file,
            )
            return {
                "iterations": 0,
                "stop_reason": "concurrent_skip",
                "items_remaining": -1,
            }

        if not self._dry_run:
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            lock_file.write_text(
                datetime.now(timezone.utc).isoformat(), encoding="utf-8"
            )

        iteration_log: list[dict] = []
        stop_reason = "max_iterations_reached"
        iteration = 0

        try:
            for iteration in range(1, max_iterations + 1):
                iter_start = datetime.now(timezone.utc)
                active_before = self._count_active_items(active_folders)

                logger.info(
                    "%s ── Iteration %d/%d | active_items=%d ──",
                    _TAG, iteration, max_iterations, active_before,
                )

                # ── Core processing cycle ─────────────────────────────────────
                # Import here to avoid a circular import at module load time.
                from src.main import run_processing_cycle  # noqa: PLC0415
                run_processing_cycle(self._vault_root, self._dry_run)

                iter_end = datetime.now(timezone.utc)
                active_after = self._count_active_items(active_folders)
                duration_ms = int((iter_end - iter_start).total_seconds() * 1000)
                moved = max(0, active_before - active_after)

                iter_entry: dict = {
                    "tag": _TAG,
                    "iteration": iteration,
                    "max_iterations": max_iterations,
                    "started_at": iter_start.isoformat(),
                    "ended_at": iter_end.isoformat(),
                    "duration_ms": duration_ms,
                    "active_items_before": active_before,
                    "active_items_after": active_after,
                    "items_moved_to_terminal": moved,
                    "dry_run": self._dry_run,
                }
                iteration_log.append(iter_entry)

                if log_each:
                    logger.info(
                        "%s Iteration %d/%d done | duration=%dms"
                        " | active_before=%d | active_after=%d | moved=%d",
                        _TAG, iteration, max_iterations,
                        duration_ms, active_before, active_after, moved,
                    )

                # ── Stop condition: all items reached terminal folders ─────────
                if stop_when_done and active_after == 0:
                    stop_reason = "all_items_done"
                    logger.info(
                        "%s All items in terminal folders — loop complete after %d"
                        " iteration(s).",
                        _TAG, iteration,
                    )
                    break

                # Wait before the next cycle (skip wait on the last iteration).
                if iteration < max_iterations:
                    logger.debug(
                        "%s Waiting %ss before iteration %d.",
                        _TAG, interval, iteration + 1,
                    )
                    time.sleep(interval)

        finally:
            # Always release the lock regardless of exit path.
            if not self._dry_run and lock_file.exists():
                try:
                    lock_file.unlink()
                except OSError:
                    pass

        # ── Write review log (FR-G027) ────────────────────────────────────────
        final_active = self._count_active_items(active_folders)
        review: dict = {
            "tag": _TAG,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stop_reason": stop_reason,
            "total_iterations": iteration,
            "max_iterations": max_iterations,
            "items_remaining": final_active,
            "dry_run": self._dry_run,
            "iterations": iteration_log,
        }
        self._write_review_log(review, review_log_dir, review_log_prefix)

        # ── Self-review log analysis (FR-G024–G028) ──────────────────────────
        self_review_cfg = cfg.get("self_review", {})
        proposals_created = 0
        if self_review_cfg.get("enabled", True):
            proposals_created = self._run_self_review(
                self_review_cfg, review, log_cfg
            )

        logger.info(
            "%s Loop finished | stop_reason=%s | total_iterations=%d | items_remaining=%d"
            " | proposals_created=%d",
            _TAG, stop_reason, iteration, final_active, proposals_created,
        )
        return {
            "iterations": iteration,
            "stop_reason": stop_reason,
            "items_remaining": final_active,
            "proposals_created": proposals_created,
        }

    # ── self-review ───────────────────────────────────────────────────────────

    def _run_self_review(
        self, self_review_cfg: dict, loop_review: dict, log_cfg: dict
    ) -> int:
        """Analyse audit logs and create improvement proposals (FR-G024–G028).

        Returns the number of NEW proposals created.
        """
        min_log_days: int = int(self_review_cfg.get("min_log_days", 7))
        failure_rate_threshold: float = float(
            self_review_cfg.get("failure_rate_threshold", 0.10)
        )
        retry_rate_threshold: float = float(
            self_review_cfg.get("retry_rate_threshold", 0.20)
        )
        rejection_rate_threshold: float = float(
            self_review_cfg.get("rejection_rate_threshold", 0.30)
        )
        slow_multiplier: float = float(
            self_review_cfg.get("slow_operation_multiplier", 3.0)
        )
        max_entries: int = int(self_review_cfg.get("max_log_entries", 10000))

        logs_dir = self._vault_root / "Logs"
        now = datetime.now(timezone.utc)

        # Load audit logs from the past min_log_days days.
        entries, days_found = _load_audit_logs(
            logs_dir, now, min_log_days, max_entries
        )

        if days_found < min_log_days:
            logger.info(
                "%s[SKIPPED] Insufficient log history: %d days found, %d required.",
                _TAG, days_found, min_log_days,
            )
            loop_review["self_review"] = {
                "skipped": True,
                "reason": f"Only {days_found} days of logs; {min_log_days} required",
            }
            return 0

        logger.info(
            "%s Self-review: analysing %d log entries over %d days",
            _TAG, len(entries), days_found,
        )

        # Analyse patterns (FR-G024).
        proposals = _analyse_patterns(
            entries=entries,
            failure_rate_threshold=failure_rate_threshold,
            retry_rate_threshold=retry_rate_threshold,
            rejection_rate_threshold=rejection_rate_threshold,
            slow_multiplier=slow_multiplier,
        )

        if not proposals:
            logger.info("%s Self-review: no actionable patterns detected.", _TAG)
            loop_review["self_review"] = {"proposals": 0, "patterns": []}
            return 0

        # Load existing pending proposal fingerprints for deduplication (FR-G028).
        existing_fingerprints = _collect_pending_fingerprints(self._vault_root)

        needs_action_dir = self._vault_root / "Needs_Action"
        needs_action_dir.mkdir(parents=True, exist_ok=True)
        created = 0

        for proposal in proposals:
            fingerprint = proposal["fingerprint"]
            if fingerprint in existing_fingerprints:
                logger.info(
                    "%s[DUPLICATE_SKIPPED] Proposal already pending: %s",
                    _TAG, fingerprint,
                )
                continue

            if not self._dry_run:
                item_path = _write_proposal_item(needs_action_dir, proposal, now)
                logger.info(
                    "%s Improvement proposal created: %s", _TAG, item_path.name
                )
            else:
                logger.info(
                    "[DRY_RUN] %s Would create improvement proposal: %s",
                    _TAG, fingerprint,
                )
            created += 1

        loop_review["self_review"] = {
            "proposals": created,
            "patterns": [p["fingerprint"] for p in proposals],
        }
        return created

    # ── helpers ───────────────────────────────────────────────────────────────

    def _count_active_items(self, active_folders: list[str]) -> int:
        """Count .md files in all active (non-terminal) pipeline folders.

        Excludes ``*-metadata.md`` sidecar files, which are not task items.
        """
        total = 0
        for folder in active_folders:
            folder_path = self._vault_root / folder
            if folder_path.exists():
                total += sum(
                    1
                    for f in folder_path.iterdir()
                    if f.is_file()
                    and f.suffix == ".md"
                    and not f.name.endswith("-metadata.md")
                )
        return total

    def _write_review_log(
        self, review: dict, log_dir: str, prefix: str
    ) -> None:
        """Append the review dict to the daily JSON log (FR-G027).

        If the file already exists for today, the new entry is appended
        to the JSON array rather than overwriting it.
        """
        log_folder = self._vault_root / log_dir
        log_folder.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = log_folder / f"{prefix}_{date_str}.json"

        try:
            if log_file.exists():
                existing = json.loads(log_file.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = [existing]
                existing.append(review)
                log_file.write_text(
                    json.dumps(existing, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            else:
                log_file.write_text(
                    json.dumps([review], indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            logger.info("%s Review log written: %s", _TAG, log_file)
        except Exception as exc:
            logger.warning("%s Could not write review log: %s", _TAG, exc)


# ── Module-level helpers ───────────────────────────────────────────────────────


def _load_audit_logs(
    logs_dir: Path, now: datetime, window_days: int, max_entries: int
) -> tuple[list[dict], int]:
    """Load JSON audit log entries from the past ``window_days`` days.

    Returns ``(entries, days_with_logs_found)``.  Caps at ``max_entries``
    to prevent AI context overflow (edge case from spec).
    """
    entries: list[dict] = []
    days_found = 0

    for offset in range(window_days):
        day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        log_file = logs_dir / f"{day}.json"
        if not log_file.exists():
            continue
        try:
            raw = json.loads(log_file.read_text(encoding="utf-8"))
            day_entries = raw if isinstance(raw, list) else [raw]
            entries.extend(day_entries)
            days_found += 1
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("%s Could not load log %s: %s", _TAG, log_file.name, exc)

    # Cap to avoid context overflow (spec edge case: >10,000 entries → summarise).
    if len(entries) > max_entries:
        logger.warning(
            "%s Log entry count %d exceeds max %d — truncating to most recent.",
            _TAG, len(entries), max_entries,
        )
        entries = entries[-max_entries:]

    return entries, days_found


def _analyse_patterns(
    *,
    entries: list[dict],
    failure_rate_threshold: float,
    retry_rate_threshold: float,
    rejection_rate_threshold: float,
    slow_multiplier: float,
) -> list[dict]:
    """Detect actionable patterns from audit log entries (FR-G024).

    Returns a list of proposal dicts, each containing:
    - ``fingerprint``       — stable key for deduplication
    - ``pattern``           — human-readable pattern description
    - ``evidence``          — list of log timestamp references
    - ``severity``          — low | medium | high
    - ``proposed_action``   — suggested correction
    """
    proposals: list[dict] = []

    # ── Counters ──────────────────────────────────────────────────────────────
    total = len(entries)
    if total == 0:
        return []

    failures_by_integration: dict[str, int] = defaultdict(int)
    totals_by_integration: dict[str, int] = defaultdict(int)
    retries_by_operation: dict[str, int] = defaultdict(int)
    totals_by_operation: dict[str, int] = defaultdict(int)
    approvals_total = 0
    approvals_rejected = 0
    durations_by_operation: dict[str, list[float]] = defaultdict(list)
    evidence_by_integration: dict[str, list[str]] = defaultdict(list)
    evidence_by_operation: dict[str, list[str]] = defaultdict(list)

    for entry in entries:
        integration = entry.get("integration", "unknown")
        operation = entry.get("operation", "unknown")
        outcome = entry.get("outcome", "")
        ts = entry.get("timestamp", "")[:19]
        retry_ctx = entry.get("retry_context") or {}
        duration_ms = entry.get("duration_ms")

        # Failure tracking
        totals_by_integration[integration] += 1
        if outcome in ("error", "failed", "failure"):
            failures_by_integration[integration] += 1
            if ts:
                evidence_by_integration[integration].append(ts)

        # Retry tracking
        totals_by_operation[operation] += 1
        if retry_ctx.get("attempt", 1) > 1:
            retries_by_operation[operation] += 1
            if ts:
                evidence_by_operation[operation].append(ts)

        # Rejection tracking
        if operation in ("approval_request", "approve") or entry.get("action") == "approval_requested":
            approvals_total += 1
            if outcome in ("rejected", "rejection"):
                approvals_rejected += 1

        # Duration tracking
        if duration_ms is not None and operation != "unknown":
            durations_by_operation[operation].append(float(duration_ms))

    # ── Pattern: high failure rate per integration ────────────────────────────
    for integration, fail_count in failures_by_integration.items():
        total_for_int = totals_by_integration[integration]
        if total_for_int < 3:
            continue
        rate = fail_count / total_for_int
        if rate >= failure_rate_threshold:
            severity = "high" if rate >= 0.5 else "medium"
            proposals.append({
                "fingerprint": f"high_failure_rate:{integration}",
                "pattern": (
                    f"Integration '{integration}' has a {rate:.0%} failure rate "
                    f"({fail_count}/{total_for_int} operations failed)"
                ),
                "evidence": evidence_by_integration[integration][-5:],
                "severity": severity,
                "proposed_action": (
                    f"Investigate '{integration}' connectivity: check credentials, "
                    f"API endpoint availability, and recent error messages. "
                    f"Consider increasing retry attempts or alerting threshold."
                ),
            })

    # ── Pattern: high retry rate per operation ────────────────────────────────
    for operation, retry_count in retries_by_operation.items():
        total_for_op = totals_by_operation[operation]
        if total_for_op < 3:
            continue
        rate = retry_count / total_for_op
        if rate >= retry_rate_threshold:
            severity = "medium" if rate < 0.5 else "high"
            proposals.append({
                "fingerprint": f"high_retry_rate:{operation}",
                "pattern": (
                    f"Operation '{operation}' retried on {rate:.0%} of calls "
                    f"({retry_count}/{total_for_op})"
                ),
                "evidence": evidence_by_operation[operation][-5:],
                "severity": severity,
                "proposed_action": (
                    f"Review '{operation}' operation: the high retry rate suggests "
                    f"transient failures. Consider adjusting base_delay or "
                    f"max_retries in Config/ralph_wiggum.yaml."
                ),
            })

    # ── Pattern: high approval rejection rate ────────────────────────────────
    if approvals_total >= 5:
        rejection_rate = approvals_rejected / approvals_total
        if rejection_rate >= rejection_rate_threshold:
            proposals.append({
                "fingerprint": "high_rejection_rate:approvals",
                "pattern": (
                    f"Approval rejection rate is {rejection_rate:.0%} "
                    f"({approvals_rejected}/{approvals_total} requests rejected)"
                ),
                "evidence": [],
                "severity": "medium",
                "proposed_action": (
                    "Review the quality of AI-generated plans and drafts. "
                    "High rejection rate may indicate: misaligned tone for social posts, "
                    "inaccurate financial summaries, or overly aggressive action proposals. "
                    "Consider refining the relevant skill prompts."
                ),
            })

    # ── Pattern: consistently slow operations ────────────────────────────────
    for operation, durations in durations_by_operation.items():
        if len(durations) < 5:
            continue
        avg_ms = sum(durations) / len(durations)
        if avg_ms > 5000 * slow_multiplier:  # Flag ops averaging > 15s (default)
            proposals.append({
                "fingerprint": f"slow_operation:{operation}",
                "pattern": (
                    f"Operation '{operation}' averages {avg_ms/1000:.1f}s "
                    f"({len(durations)} samples)"
                ),
                "evidence": [],
                "severity": "low",
                "proposed_action": (
                    f"Investigate why '{operation}' is slow. "
                    f"Consider adding pagination, caching, or reducing scope. "
                    f"Check external API response times."
                ),
            })

    return proposals


def _collect_pending_fingerprints(vault_root: Path) -> set[str]:
    """Scan Needs_Action/ and Pending_Approval/ for existing proposal fingerprints.

    Returns a set of fingerprint strings found in existing Ralph Wiggum proposal
    files (detected via the ``ralph_wiggum_fingerprint:`` front-matter field).
    This enables FR-G028 deduplication.
    """
    fingerprints: set[str] = set()
    for folder in ("Needs_Action", "Pending_Approval"):
        d = vault_root / folder
        if not d.exists():
            continue
        for f in d.iterdir():
            if not (f.is_file() and f.suffix == ".md"):
                continue
            try:
                text = f.read_text(encoding="utf-8")
                # Look for the YAML front-matter field.
                import re
                match = re.search(r"^ralph_wiggum_fingerprint:\s*(.+)$", text, re.MULTILINE)
                if match:
                    fingerprints.add(match.group(1).strip())
            except OSError:
                pass
    return fingerprints


def _write_proposal_item(
    needs_action_dir: Path, proposal: dict, now: datetime
) -> Path:
    """Write a Needs_Action vault item for an improvement proposal (FR-G025/G026)."""
    item_id = str(uuid.uuid4())
    ts = now.isoformat()
    safe_fp = proposal["fingerprint"].replace(":", "-").replace("/", "-")
    filename = f"ralph-proposal-{safe_fp[:40]}-{item_id[:8]}.md"
    path = needs_action_dir / filename

    evidence_md = "\n".join(f"- {e}" for e in proposal["evidence"]) or "_No timestamps available._"

    content = (
        "---\n"
        f"id: {item_id}\n"
        "type: improvement_proposal\n"
        "source: ralph_wiggum\n"
        "priority: medium\n"
        "status: needs_action\n"
        "requires_approval: true\n"
        "classification: local_only\n"
        f"created_at: {ts}\n"
        f"updated_at: {ts}\n"
        f"ralph_wiggum_fingerprint: {proposal['fingerprint']}\n"
        f"severity: {proposal['severity']}\n"
        "tags: [ralph_wiggum, improvement_proposal]\n"
        "---\n\n"
        f"# Improvement Proposal: {proposal['pattern'][:80]}\n\n"
        f"**Source**: Ralph Wiggum Self-Review  \n"
        f"**Severity**: `{proposal['severity']}`  \n"
        f"**Fingerprint**: `{proposal['fingerprint']}`  \n"
        f"**Detected**: {ts}  \n\n"
        f"{_TAG}\n\n"
        "## Pattern Detected\n\n"
        f"{proposal['pattern']}\n\n"
        "## Evidence (Log References)\n\n"
        f"{evidence_md}\n\n"
        "## Proposed Action\n\n"
        f"{proposal['proposed_action']}\n\n"
        "## Approval Required\n\n"
        "This proposal was auto-generated by Ralph Wiggum. "
        "No changes will be made without explicit human approval.\n\n"
        "- [ ] Review the pattern and evidence above\n"
        "- [ ] Approve the proposed action or provide alternative\n"
        "- [ ] The executor skill will implement approved changes\n"
    )

    path.write_text(content, encoding="utf-8")
    return path
