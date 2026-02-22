"""Audit log entry dataclass matching FR-038 schema (T009)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


_VALID_OUTCOMES = {"success", "failure", "retry", "dry_run"}
_VALID_APPROVAL_STATUSES = {"auto", "pending", "approved", "rejected", "n/a"}


@dataclass
class ApprovalInfo:
    required: bool = False
    status: str = "n/a"
    approver: str | None = None

    def validate(self) -> bool:
        if self.status not in _VALID_APPROVAL_STATUSES:
            raise ValueError(f"Invalid approval status: {self.status!r}")
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"required": self.required, "status": self.status, "approver": self.approver}


@dataclass
class LogEntry:
    """Single FR-038-compliant audit log entry."""

    actor: str
    action: str
    outcome: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    item_id: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    approval: ApprovalInfo = field(default_factory=ApprovalInfo)
    dry_run: bool = False

    def validate(self) -> bool:
        if self.outcome not in _VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome: {self.outcome!r}")
        # Validate timestamp is ISO-8601 with timezone.
        try:
            dt = datetime.fromisoformat(self.timestamp)
            if dt.tzinfo is None:
                raise ValueError("timestamp must include timezone")
        except ValueError as e:
            raise ValueError(f"Invalid timestamp: {e}") from e
        self.approval.validate()
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "item_id": self.item_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "outcome": self.outcome,
            "duration_ms": self.duration_ms,
            "details": self.details,
            "approval": self.approval.to_dict(),
            "dry_run": self.dry_run,
        }
