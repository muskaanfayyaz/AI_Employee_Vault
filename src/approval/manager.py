"""Human-in-the-loop approval workflow manager (T031).

Implements the approval loop described in FR-017:

1. A skill calls :meth:`ApprovalManager.request_approval` — this writes
   an ``ApprovalRequest`` file to ``/Pending_Approval``.
2. A human reviews the file and signals their decision by either:
   a. Editing the ``decision:`` field to ``approved`` or ``rejected``, or
   b. Moving the file directly to ``/Approved`` or ``/Rejected``.
3. The orchestrator periodically calls :meth:`ApprovalManager.check_approvals`
   which detects the decision and routes the file via the state machine.
   The returned list of approved requests is passed to the MCP executor.
4. Stale approvals (>24h pending) are surfaced by
   :meth:`ApprovalManager.get_stale_approvals` so the Dashboard can flag
   them. They are NEVER auto-approved (Principle IV).

Logging:
    Every approval event (request, approve, reject, stale) is written
    to the audit log via :class:`~src.engine.logger.AuditLogger`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.engine.state_machine import move
from src.models.approval import ApprovalRequest
from src.models.log_entry import ApprovalInfo, LogEntry

if TYPE_CHECKING:
    from src.engine.logger import AuditLogger
    from src.models.task_item import TaskItem

logger = logging.getLogger(__name__)


class ApprovalManager:
    """Manages the human-in-the-loop approval lifecycle.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root (parent of ``Pending_Approval/``,
        ``Approved/``, ``Rejected/``, etc.).
    audit_logger:
        Optional :class:`~src.engine.logger.AuditLogger` for structured
        audit trail. When ``None`` approval events are only emitted as
        ``logging`` messages.
    dry_run:
        When ``True`` no files are written or moved; approval requests
        are logged with ``outcome=dry_run``.
    """

    def __init__(
        self,
        vault_root: Path,
        *,
        audit_logger: "AuditLogger | None" = None,
        dry_run: bool = False,
    ) -> None:
        self._vault_root = Path(vault_root)
        self._pending_dir = self._vault_root / "Pending_Approval"
        self._approved_dir = self._vault_root / "Approved"
        self._rejected_dir = self._vault_root / "Rejected"
        self._audit_logger = audit_logger
        self._dry_run = dry_run

    # ── Public API ────────────────────────────────────────────────────────────

    def request_approval(
        self,
        item: "TaskItem",
        proposed_action: str,
        reasoning: str,
        original_context: str = "",
    ) -> ApprovalRequest:
        """Create an approval request file in ``/Pending_Approval``.

        The file name is ``approval-<item_id[:8]>.md``.  In dry-run mode
        the file is not written but the request object is still returned.

        Parameters
        ----------
        item:
            The Task Item triggering the approval requirement.
        proposed_action:
            Human-readable description of what will happen if approved.
            E.g. ``"Send reply to John about Q4 invoice"``.
        reasoning:
            The AI's rationale for why this action requires approval.
        original_context:
            Brief summary of the event that triggered this request.

        Returns
        -------
        ApprovalRequest
            The created (and optionally persisted) request.
        """
        request = ApprovalRequest(
            id=item.id,
            type=item.type,
            source=item.source,
            priority=item.priority,
            status="pending_approval",
            requires_approval=True,
            classification=item.classification,
            created_at=item.created_at,
            tags=list(item.tags),
            body=item.body,
            proposed_action=proposed_action,
            reasoning=reasoning,
            original_context=original_context,
        )

        filename = f"approval-{request.id[:8]}.md"
        dest = self._pending_dir / filename

        if not self._dry_run:
            self._pending_dir.mkdir(parents=True, exist_ok=True)
            request.to_file(dest)
            logger.info("Approval requested: %s → %s", request.id, filename)
        else:
            logger.info("[DRY_RUN] Would create approval request: %s", filename)

        self._log(
            actor="approval_manager",
            action=f"approval requested: {proposed_action[:80]}",
            item_id=request.id,
            from_state="In_Progress",
            to_state="Pending_Approval",
            outcome="dry_run" if self._dry_run else "success",
            details={
                "proposed_action": proposed_action,
                "filename": filename,
                "reasoning": reasoning,
            },
            approval_required=True,
            approval_status="pending",
        )
        return request

    def check_approvals(
        self,
    ) -> tuple[list[ApprovalRequest], list[ApprovalRequest]]:
        """Scan for human decisions and route files to ``Approved/`` or ``Rejected/``.

        Detects two human-approval patterns:

        **Pattern A — in-place edit**: the human edits the ``decision:``
        field in the file while it remains in ``Pending_Approval/``.
        ``check_approvals`` moves it to the appropriate destination.

        **Pattern B — manual move**: the human drags the file directly
        to ``Approved/`` in their file manager or Obsidian vault.
        ``check_approvals`` detects it there and marks it approved.

        Returns
        -------
        tuple[list[ApprovalRequest], list[ApprovalRequest]]
            ``(approved, rejected)`` — the caller (orchestrator) should
            iterate over *approved* and execute the corresponding MCP
            calls, then move the items back to ``In_Progress``.
        """
        approved: list[ApprovalRequest] = []
        rejected: list[ApprovalRequest] = []
        # Track IDs processed in Pattern A so Pattern B doesn't double-count
        # files that were just moved to Approved/ in this same call.
        processed_ids: set[str] = set()

        # ── Pattern A: files in Pending_Approval/ with a non-pending decision ──
        for md_file in self._iter_markdown(self._pending_dir):
            try:
                req = ApprovalRequest.from_file(md_file)
            except Exception as exc:
                logger.warning("Cannot parse approval file %s: %s", md_file.name, exc)
                continue

            if req.decision == "approved":
                self._move_file(md_file, "Pending_Approval", "Approved")
                logger.info("Approved (edit): %s", md_file.name)
                self._log(
                    actor="approval_manager",
                    action="approval decision: approved",
                    item_id=req.id,
                    from_state="Pending_Approval",
                    to_state="Approved",
                    outcome="dry_run" if self._dry_run else "success",
                    details={"feedback": req.feedback, "filename": md_file.name},
                    approval_required=True,
                    approval_status="approved",
                )
                processed_ids.add(req.id)
                approved.append(req)

            elif req.decision == "rejected":
                self._move_file(md_file, "Pending_Approval", "Rejected")
                logger.info("Rejected (edit): %s", md_file.name)
                self._log(
                    actor="approval_manager",
                    action="approval decision: rejected",
                    item_id=req.id,
                    from_state="Pending_Approval",
                    to_state="Rejected",
                    outcome="dry_run" if self._dry_run else "success",
                    details={"feedback": req.feedback, "filename": md_file.name},
                    approval_required=True,
                    approval_status="rejected",
                )
                processed_ids.add(req.id)
                rejected.append(req)

        # ── Pattern B: files already in Approved/ (manually moved by human) ──
        for md_file in self._iter_markdown(self._approved_dir):
            try:
                req = ApprovalRequest.from_file(md_file)
            except Exception as exc:
                logger.warning("Cannot parse approved file %s: %s", md_file.name, exc)
                continue

            if req.id in processed_ids:
                # This file was just moved here by Pattern A — skip to avoid double-counting.
                continue

            if req.decision == "pending":
                # Human moved the file directly — treat as approved.
                req.approve(feedback="[manual move to Approved/]")
                logger.info("Approved (manual move): %s", md_file.name)
                self._log(
                    actor="approval_manager",
                    action="approval decision: manually approved",
                    item_id=req.id,
                    from_state="Approved",
                    to_state="Approved",
                    outcome="dry_run" if self._dry_run else "success",
                    details={"filename": md_file.name},
                    approval_required=True,
                    approval_status="approved",
                )

            approved.append(req)

        return approved, rejected

    def get_stale_approvals(self) -> list[ApprovalRequest]:
        """Return approval requests that have been pending for more than 24h.

        Expired approvals are flagged for the Dashboard but NEVER
        auto-approved (Principle IV).

        Returns
        -------
        list[ApprovalRequest]
            Items in ``Pending_Approval/`` where ``decision == "pending"``
            and ``expires_at`` is in the past.
        """
        stale: list[ApprovalRequest] = []
        for md_file in self._iter_markdown(self._pending_dir):
            try:
                req = ApprovalRequest.from_file(md_file)
            except Exception as exc:
                logger.warning("Cannot parse file %s: %s", md_file.name, exc)
                continue

            if req.decision == "pending" and req.is_expired():
                stale.append(req)
                logger.warning(
                    "Stale approval (%s): requested at %s, expired at %s",
                    md_file.name,
                    req.requested_at,
                    req.expires_at,
                )
        return stale

    # ── Private helpers ───────────────────────────────────────────────────────

    def _move_file(self, file_path: Path, from_folder: str, to_folder: str) -> Path:
        """Move *file_path* via the state machine (or log only in dry-run)."""
        return move(file_path, from_folder, to_folder, dry_run=self._dry_run)

    @staticmethod
    def _iter_markdown(directory: Path):
        """Yield ``*.md`` files in *directory*, skipping missing dirs."""
        if not directory.exists():
            return
        yield from sorted(directory.glob("*.md"))

    def _log(
        self,
        *,
        actor: str,
        action: str,
        item_id: str,
        from_state: str,
        to_state: str,
        outcome: str,
        details: dict,
        approval_required: bool,
        approval_status: str,
    ) -> None:
        """Append a structured audit log entry (no-op when logger is None)."""
        if self._audit_logger is None:
            return
        entry = LogEntry(
            actor=actor,
            action=action,
            item_id=item_id,
            from_state=from_state,
            to_state=to_state,
            outcome=outcome,
            details=details,
            approval=ApprovalInfo(
                required=approval_required,
                status=approval_status,
                approver="human",
            ),
            dry_run=self._dry_run,
        )
        try:
            self._audit_logger.log(entry)
        except Exception as exc:
            logger.error("Failed to write audit log entry: %s", exc)
