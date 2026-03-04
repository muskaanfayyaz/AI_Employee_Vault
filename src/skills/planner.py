"""Planner skill — create Plan.md from a Needs_Action item (T022)."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.models.task_item import TaskItem
from src.models.plan import Plan, Step
from src.engine import state_machine

logger = logging.getLogger(__name__)

_APPROVAL_KEYWORDS = [
    "send email", "payment", "publish", "delete", "remove", "contact",
    "invoice", "transfer", "purchase",
]


class PlannerSkill(BaseSkill):
    """Decompose a Needs_Action item into a structured Plan.md."""

    @property
    def name(self) -> str:
        return "planner"

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
            return SkillOutput(success=False, result="No item path", error="item_path required")

        try:
            item = TaskItem.from_file(item_path)
        except Exception as exc:
            return SkillOutput(success=False, result=f"Failed to parse {item_path.name}", error=str(exc))

        content = item.body
        lower = content.lower()

        # Title from first heading or filename.
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else item_path.stem

        # Build steps — try Gemini reasoning first, fall back to rules.
        steps = _ai_generate_steps(
            title=title,
            content=content,
            item_type=item.type,
            priority=item.priority,
        )
        requires_approval = any(kw in lower for kw in _APPROVAL_KEYWORDS)

        now = datetime.now(timezone.utc).isoformat()
        plan = Plan(
            id=str(uuid.uuid4()),
            item_id=item.id,
            created_at=now,
            updated_at=now,
            status="pending",
            steps=steps,
            context=f"Process '{title}' — {item.priority} priority.",
            priority=item.priority,
            requires_approval=requires_approval,
        )

        plans_dir = vault_root / "Plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plans_dir / f"PLAN_{item_path.stem}.md"

        actions: list[str] = []
        if not dry_run:
            plan.to_file(plan_path)
            actions.append(f"created Plans/{plan_path.name}")
            # Update item status to planned.
            try:
                item.update_frontmatter(status="planned")
                item.to_file(item_path)
                actions.append("updated item status → planned")
            except Exception:
                pass
        else:
            actions.append(f"[DRY_RUN] would create Plans/{plan_path.name}")

        return SkillOutput(
            success=True,
            result=f"Plan created for {item_path.stem} with {len(steps)} steps",
            actions_taken=actions,
            metadata={"plan_path": str(plan_path), "steps": len(steps)},
        )


def _ai_generate_steps(
    title: str, content: str, item_type: str, priority: str
) -> list[Step]:
    """Generate plan steps using Gemini reasoning.

    Falls back to rule-based ``_generate_steps`` when GEMINI_API_KEY is
    not set or the API call fails.
    """
    import os
    from pathlib import Path as _Path
    from dotenv import load_dotenv

    load_dotenv(_Path.cwd() / ".env", override=False)
    api_key = os.getenv("GEMINI_API_KEY", "")

    if api_key:
        try:
            return _gemini_plan_steps(api_key, title, content, item_type, priority)
        except Exception as exc:
            logger.warning(
                "Gemini planner failed (%s: %s) — using rule-based fallback.",
                type(exc).__name__, exc,
            )

    return _generate_steps(content.lower(), item_type, priority)


def _gemini_plan_steps(
    api_key: str, title: str, content: str, item_type: str, priority: str
) -> list[Step]:
    """Call Gemini to reason about the best action steps for this item."""
    import requests as _requests  # type: ignore[import]

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    prompt = (
        "You are an AI task planner. Given the item below, output a numbered "
        "list of 3-5 concrete action steps to resolve it.\n\n"
        f"Type: {item_type}\n"
        f"Priority: {priority}\n"
        f"Title: {title}\n\n"
        f"Content:\n{content[:1500]}\n\n"
        "Rules:\n"
        "- Output ONLY a numbered list, one step per line (e.g. '1. Do X')\n"
        "- Last step must always be: 'Mark item complete and archive'\n"
        "- Steps must be specific to this item's actual content\n"
        "- No preamble, no explanation — just the numbered list"
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = _requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    steps: list[Step] = []
    for line in text.splitlines():
        line = line.strip()
        match = re.match(r"^\d+[\.\)]\s+(.+)$", line)
        if match:
            steps.append(Step(number=len(steps) + 1, description=match.group(1).strip()))

    if not steps:
        raise ValueError("Gemini returned no parseable steps")

    logger.info("Gemini planner: %d steps generated for '%s'", len(steps), title)
    return steps


def _generate_steps(lower: str, item_type: str, priority: str) -> list[Step]:
    base: list[str] = []
    if item_type == "email":
        base = ["Review email content and sender", "Draft reply", "Route to Pending_Approval"]
    elif item_type == "message":
        base = ["Review message content", "Draft response", "Route to Pending_Approval"]
    elif item_type == "erp":
        base = ["Review ERP record details", "Validate data accuracy", "Take required action"]
    elif item_type in ("social", "social_post"):
        base = ["Review social content", "Draft post", "Route to Pending_Approval"]
    else:
        if any(kw in lower for kw in ["invoice", "payment", "amount"]):
            base = ["Review financial details", "Cross-reference records", "Flag discrepancies"]
        elif any(kw in lower for kw in ["research", "report", "analyse"]):
            base = ["Read material thoroughly", "Summarise key findings", "Draft recommendations"]
        else:
            base = ["Review item content", "Identify required actions", "Execute or delegate"]

    base.append("Mark item complete and archive")
    return [Step(number=i, description=d) for i, d in enumerate(base, 1)]
