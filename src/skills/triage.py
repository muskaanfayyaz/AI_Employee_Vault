"""Triage skill — classify and prioritise items from Needs_Action (T021)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.models.task_item import TaskItem
from src.engine import state_machine

logger = logging.getLogger(__name__)

_PRIORITY_KEYWORDS = {
    "urgent": ["urgent", "asap", "immediately", "critical", "emergency"],
    "high": ["important", "priority", "deadline", "overdue", "high priority"],
    "low": ["low priority", "when possible", "optional", "nice to have"],
}
_APPROVAL_KEYWORDS = [
    "send email", "payment", "publish", "delete", "remove", "contact",
    "invoice", "transfer", "purchase", "approve",
]
_TYPE_KEYWORDS = {
    "email": ["email", "reply", "inbox", "from:", "subject:"],
    "message": ["whatsapp", "message", "chat", "sms"],
    "erp": ["invoice", "sales order", "odoo", "erp", "record"],
    "social": ["linkedin", "twitter", "facebook", "instagram", "post"],
    "audit": ["audit", "review", "compliance", "ralph_wiggum"],
}


class TriageSkill(BaseSkill):
    """Classify item type, priority, and approval requirements."""

    @property
    def name(self) -> str:
        return "triage"

    @property
    def version(self) -> str:
        return "1.0.0"

    def health_check(self) -> bool:
        return True

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        item_path = skill_input.item_path
        dry_run = skill_input.dry_run
        vault_root = skill_input.vault_root

        if item_path is None:
            return SkillOutput(success=False, result="No item path provided", error="item_path required")

        try:
            item = TaskItem.from_file(item_path)
        except Exception as exc:
            return SkillOutput(success=False, result=f"Failed to parse {item_path.name}", error=str(exc))

        content = item.body.lower()

        # Determine type.
        item_type = item.type
        if item_type == "file":
            for t, keywords in _TYPE_KEYWORDS.items():
                if any(kw in content for kw in keywords):
                    item_type = t
                    break

        # Determine priority.
        priority = item.priority
        for p, keywords in _PRIORITY_KEYWORDS.items():
            if any(kw in content for kw in keywords):
                priority = p
                break

        # Approval flag.
        requires_approval = any(kw in content for kw in _APPROVAL_KEYWORDS)

        actions: list[str] = []
        if not dry_run:
            item.update_frontmatter(
                type=item_type,
                priority=priority,
                requires_approval=requires_approval,
                status="needs_action",
            )
            item.to_file(item_path)
            actions.append(f"updated front-matter: type={item_type}, priority={priority}")
        else:
            actions.append(f"[DRY_RUN] would set type={item_type}, priority={priority}")

        return SkillOutput(
            success=True,
            result=f"Triaged {item_path.name}: type={item_type}, priority={priority}",
            actions_taken=actions,
            metadata={"type": item_type, "priority": priority, "requires_approval": requires_approval},
        )
