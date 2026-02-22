"""Plan entity with step parsing and status tracking (T014)."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models.task_item import _split_front_matter, _parse_yaml_simple

_VALID_PLAN_STATUSES = {"pending", "in_progress", "done", "failed"}
_VALID_STEP_STATUSES = {"pending", "in_progress", "done", "failed"}


@dataclass
class Step:
    number: int
    description: str
    status: str = "pending"
    requires_approval: bool = False
    expected_outcome: str = ""

    def is_done(self) -> bool:
        return self.status == "done"

    def is_pending(self) -> bool:
        return self.status == "pending"


@dataclass
class Plan:
    id: str
    item_id: str
    created_at: str
    updated_at: str
    status: str
    steps: list[Step] = field(default_factory=list)
    context: str = ""
    priority: str = "medium"
    requires_approval: bool = False

    def next_pending_step(self) -> Step | None:
        return next((s for s in self.steps if s.is_pending()), None)

    def update_step(self, step_num: int, status: str) -> None:
        if status not in _VALID_STEP_STATUSES:
            raise ValueError(f"Invalid step status: {status!r}")
        for step in self.steps:
            if step.number == step_num:
                step.status = status
                self.updated_at = datetime.now(timezone.utc).isoformat()
                # Update plan status.
                all_done = all(s.is_done() for s in self.steps)
                any_failed = any(s.status == "failed" for s in self.steps)
                if all_done:
                    self.status = "done"
                elif any_failed:
                    self.status = "failed"
                elif any(s.status == "in_progress" for s in self.steps):
                    self.status = "in_progress"
                return
        raise ValueError(f"Step {step_num} not found")

    def to_markdown(self) -> str:
        steps_md = ""
        for i, step in enumerate(self.steps, 1):
            check = "[x]" if step.is_done() else "[ ]"
            steps_md += f"- {check} {step.description}\n"

        return (
            "---\n"
            f"id: {self.id}\n"
            f"item_id: {self.item_id}\n"
            f"created_at: {self.created_at}\n"
            f"updated_at: {self.updated_at}\n"
            f"status: {self.status}\n"
            f"priority: {self.priority}\n"
            f"requires_approval: {str(self.requires_approval).lower()}\n"
            "---\n\n"
            f"## Context\n\n{self.context}\n\n"
            f"## Steps\n\n{steps_md}"
        )

    def to_file(self, path: Path) -> None:
        path.write_text(self.to_markdown(), encoding="utf-8")

    @classmethod
    def from_file(cls, path: Path) -> "Plan":
        return cls.from_markdown(path.read_text(encoding="utf-8"))

    @classmethod
    def from_markdown(cls, text: str) -> "Plan":
        fm, body = _split_front_matter(text)
        raw = _parse_yaml_simple(fm)

        def _bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            return str(v).lower() in ("true", "1", "yes")

        # Parse steps from body checkboxes.
        steps: list[Step] = []
        for i, m in enumerate(re.finditer(r"- \[([ xX])\]\s+(.+)", body), 1):
            done = m.group(1).lower() == "x"
            steps.append(Step(
                number=i,
                description=m.group(2).strip(),
                status="done" if done else "pending",
            ))

        # Extract context section.
        ctx_match = re.search(r"##\s+Context\s*\n(.*?)(?=\n##|\Z)", body, re.DOTALL)
        context = ctx_match.group(1).strip() if ctx_match else ""

        return cls(
            id=raw.get("id", str(uuid.uuid4())),
            item_id=raw.get("item_id", ""),
            created_at=raw.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=raw.get("updated_at", datetime.now(timezone.utc).isoformat()),
            status=raw.get("status", "pending"),
            steps=steps,
            context=context,
            priority=raw.get("priority", "medium"),
            requires_approval=_bool(raw.get("requires_approval", False)),
        )
