"""Approval Request model — human-in-the-loop approval workflow (T030).

An ``ApprovalRequest`` is a Task Item that has been routed to
``/Pending_Approval``. It carries all standard Task Item front-matter
plus an ``approval:`` nested block describing the proposed action and
capturing the human's decision.

File format::

    ---
    id: "uuid-v4"
    type: email
    source: gmail
    priority: medium
    status: pending_approval
    requires_approval: true
    classification: local_only
    created_at: "2026-02-19T10:00:00+00:00"
    updated_at: "2026-02-19T10:00:00+00:00"
    tags: []
    approval:
      proposed_action: "Send reply to John about invoice"
      reasoning: "FR-017 — outbound email requires approval"
      original_context: "John asked for Q4 invoice status"
      requested_at: "2026-02-19T10:00:00+00:00"
      expires_at: "2026-02-20T10:00:00+00:00"
      decision: pending
      decided_at: null
      feedback: null
    ---

Principle IV (from constitution.md): Expired approvals MUST be flagged
but NEVER auto-approved.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

_VALID_DECISIONS = {"pending", "approved", "rejected"}


@dataclass
class ApprovalRequest:
    """A Task Item awaiting human approval.

    Construct directly or use :meth:`from_file` / :meth:`from_markdown`.
    The ``expires_at`` field is auto-set to ``requested_at + 24h`` when
    left empty.
    """

    # ── Task Item base fields ────────────────────────────────────────────────
    id: str
    type: str
    source: str
    priority: str
    status: str = "pending_approval"
    requires_approval: bool = True
    classification: str = "local_only"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)
    body: str = ""

    # ── Approval-specific fields ─────────────────────────────────────────────
    proposed_action: str = ""
    reasoning: str = ""
    original_context: str = ""
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""          # auto-set in __post_init__ if empty
    decision: str = "pending"
    decided_at: str | None = None
    feedback: str | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if self.decision not in _VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision: {self.decision!r}. "
                f"Must be one of {sorted(_VALID_DECISIONS)}"
            )
        if not self.expires_at:
            requested = datetime.fromisoformat(self.requested_at)
            if requested.tzinfo is None:
                requested = requested.replace(tzinfo=timezone.utc)
            self.expires_at = (requested + timedelta(hours=24)).isoformat()

    # ── Decision methods ─────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        """Return ``True`` when the 24-hour approval window has passed.

        Expired approvals MUST be flagged but NEVER auto-approved
        (Principle IV).
        """
        expires = datetime.fromisoformat(self.expires_at)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires

    def approve(self, feedback: str | None = None) -> None:
        """Record a human approval.

        Parameters
        ----------
        feedback:
            Optional human comment attached to the decision.

        Raises
        ------
        ValueError
            If a decision has already been recorded.
        """
        if self.decision != "pending":
            raise ValueError(
                f"Cannot approve: decision already set to {self.decision!r}"
            )
        self.decision = "approved"
        self.decided_at = datetime.now(timezone.utc).isoformat()
        self.feedback = feedback
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def reject(self, feedback: str | None = None) -> None:
        """Record a human rejection.

        Parameters
        ----------
        feedback:
            Optional human comment attached to the decision.

        Raises
        ------
        ValueError
            If a decision has already been recorded.
        """
        if self.decision != "pending":
            raise ValueError(
                f"Cannot reject: decision already set to {self.decision!r}"
            )
        self.decision = "rejected"
        self.decided_at = datetime.now(timezone.utc).isoformat()
        self.feedback = feedback
        self.updated_at = datetime.now(timezone.utc).isoformat()

    # ── Serialization ────────────────────────────────────────────────────────

    def to_markdown(self) -> str:
        """Render the approval request as YAML front-matter + markdown body."""
        approval_block: dict[str, Any] = {
            "proposed_action": self.proposed_action,
            "reasoning": self.reasoning,
            "original_context": self.original_context,
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "decision": self.decision,
            "decided_at": self.decided_at,
            "feedback": self.feedback,
        }

        tags_str = "[" + ", ".join(self.tags) + "]"
        approval_yaml = yaml.dump(
            approval_block, default_flow_style=False, allow_unicode=True
        ).rstrip()
        # Indent each line of the approval sub-block by 2 spaces.
        approval_indented = "\n".join(f"  {line}" for line in approval_yaml.splitlines())

        fm = (
            "---\n"
            f"id: {self.id}\n"
            f"type: {self.type}\n"
            f"source: {self.source}\n"
            f"priority: {self.priority}\n"
            f"status: {self.status}\n"
            f"requires_approval: {str(self.requires_approval).lower()}\n"
            f"classification: {self.classification}\n"
            f"created_at: {self.created_at}\n"
            f"updated_at: {self.updated_at}\n"
            f"tags: {tags_str}\n"
            f"approval:\n{approval_indented}\n"
            "---\n"
        )
        return fm + ("\n" + self.body if self.body else "")

    def to_file(self, path: Path) -> None:
        """Write to a ``.md`` file at *path*."""
        path.write_text(self.to_markdown(), encoding="utf-8")

    # ── Parsing ──────────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: Path) -> "ApprovalRequest":
        """Parse an ``ApprovalRequest`` from a ``.md`` file."""
        return cls.from_markdown(path.read_text(encoding="utf-8"))

    @classmethod
    def from_markdown(cls, text: str) -> "ApprovalRequest":
        """Parse an ``ApprovalRequest`` from raw markdown text.

        Uses PyYAML to correctly handle the nested ``approval:`` block.
        """
        fm_text, body = _split_front_matter(text)
        raw: dict[str, Any] = yaml.safe_load(fm_text) or {}
        approval: dict[str, Any] = raw.get("approval") or {}

        def _bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            return str(v).lower() in ("true", "1", "yes")

        def _list(v: Any) -> list[str]:
            if v is None:
                return []
            if isinstance(v, list):
                return [str(x) for x in v]
            return []

        def _str_or_none(v: Any) -> str | None:
            if v is None:
                return None
            s = str(v).strip()
            return s if s and s.lower() != "null" else None

        return cls(
            id=str(raw.get("id", uuid.uuid4())),
            type=str(raw.get("type", "file")),
            source=str(raw.get("source", "filesystem")),
            priority=str(raw.get("priority", "medium")),
            status=str(raw.get("status", "pending_approval")),
            requires_approval=_bool(raw.get("requires_approval", True)),
            classification=str(raw.get("classification", "local_only")),
            created_at=str(raw.get("created_at", datetime.now(timezone.utc).isoformat())),
            updated_at=str(raw.get("updated_at", datetime.now(timezone.utc).isoformat())),
            tags=_list(raw.get("tags")),
            body=body,
            proposed_action=str(approval.get("proposed_action", "")),
            reasoning=str(approval.get("reasoning", "")),
            original_context=str(approval.get("original_context", "")),
            requested_at=str(
                approval.get("requested_at", datetime.now(timezone.utc).isoformat())
            ),
            expires_at=str(approval.get("expires_at", "")),
            decision=str(approval.get("decision", "pending")),
            decided_at=_str_or_none(approval.get("decided_at")),
            feedback=_str_or_none(approval.get("feedback")),
        )


# ── Module helpers ────────────────────────────────────────────────────────────


def _split_front_matter(text: str) -> tuple[str, str]:
    """Split ``---\n...\n---\n`` front-matter from markdown body."""
    if not text.startswith("---"):
        return "", text
    try:
        end = text.index("---", 3)
        return text[3:end].strip(), text[end + 3:].strip()
    except ValueError:
        return "", text
