"""LinkedIn post drafting skill — Silver tier.

Reads a social TaskItem from ``Needs_Action/``, drafts a LinkedIn post
from its content, and routes the draft to ``Pending_Approval/`` for
human review.

FR-017: ``post_to_linkedin`` ALWAYS requires approval — this skill NEVER
posts directly.  It creates an ``ApprovalRequest``-style markdown file
with:

- Platform (LinkedIn)
- Draft post body
- Original item context

The human then reviews the draft and either approves (triggers LinkedIn
``/v2/ugcPosts``) or rejects (discards the draft).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models.task_item import TaskItem
from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)


class LinkedInPosterSkill(BaseSkill):
    """Draft a LinkedIn post from a social TaskItem.

    The draft is written to ``Pending_Approval/`` as a markdown file
    containing the post text and original context.  The human reviews
    and approves or rejects before any outbound post is triggered.

    Inputs
    ------
    skill_input.item_path:
        Path to a social TaskItem in ``Needs_Action/``.
    skill_input.vault_root:
        Vault root directory — used to locate ``Pending_Approval/``.
    skill_input.dry_run:
        When True, draft is logged but NOT written to disk.
    """

    @property
    def name(self) -> str:
        return "linkedin_poster"

    @property
    def version(self) -> str:
        return "1.0.0"

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        """Draft a LinkedIn post and place it in ``Pending_Approval/``."""
        if skill_input.item_path is None:
            return SkillOutput(
                success=False,
                result="linkedin_poster requires an item_path.",
                error="No item_path provided.",
            )

        item_path = skill_input.item_path
        if not item_path.exists():
            return SkillOutput(
                success=False,
                result=f"Item not found: {item_path}",
                error=f"File does not exist: {item_path}",
            )

        try:
            item = TaskItem.from_file(item_path)
        except Exception as exc:
            return SkillOutput(
                success=False,
                result=f"Could not parse TaskItem from {item_path.name}",
                error=str(exc),
            )

        if item.type != "social":
            return SkillOutput(
                success=False,
                result=(
                    f"Item {item.id[:8]} is not a social post "
                    f"(type={item.type!r}). LinkedInPosterSkill expects type=social."
                ),
                error=f"Expected type=social, got {item.type!r}.",
            )

        # Extract raw content from the item body.
        full_text = item_path.read_text(encoding="utf-8")
        raw_content = _extract_section(full_text, "Content") or item.body.strip()
        title = _extract_title(full_text) or item_path.stem

        # Draft the post body (Gemini if available, else structured placeholder).
        post_body = _draft_post(
            title=title,
            raw_content=raw_content,
            config=skill_input.config,
        )

        draft_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        draft_filename = f"draft-li-post-{draft_id[:8]}.md"
        pending_dir = skill_input.vault_root / "Pending_Approval"

        draft_content = (
            "---\n"
            f"id: {draft_id}\n"
            "type: social\n"
            "source: linkedin_poster\n"
            "priority: medium\n"
            "status: pending_approval\n"
            "requires_approval: true\n"
            "classification: local_only\n"
            f"created_at: {now}\n"
            f"updated_at: {now}\n"
            "tags: [draft, linkedin-post]\n"
            "approval:\n"
            '  proposed_action: "Post to LinkedIn"\n'
            '  reasoning: "FR-017 — outbound social post requires human approval"\n'
            f"  original_item_id: {item.id}\n"
            f"  requested_at: {now}\n"
            "  decision: pending\n"
            "  decided_at: null\n"
            "  feedback: null\n"
            "---\n\n"
            "# LinkedIn Post Draft\n\n"
            "**Platform**: LinkedIn  \n"
            f"**Original Item**: {item_path.name}  \n\n"
            "## Post Content\n\n"
            f"{post_body}\n\n"
            "## Original Context\n\n"
            f"{raw_content or '_No content extracted._'}\n\n"
            "## Approval Instructions\n\n"
            "- [ ] Review draft post above\n"
            "- [ ] Edit if needed\n"
            "- [ ] Change `decision: pending` → `decision: approved` to post\n"
            "- [ ] Change `decision: pending` → `decision: rejected` to discard\n"
        )

        if skill_input.dry_run:
            logger.info(
                "[DRY_RUN] Would create LinkedIn post draft: %s → Pending_Approval/%s",
                item_path.name,
                draft_filename,
            )
            return SkillOutput(
                success=True,
                result="[DRY_RUN] Would draft LinkedIn post.",
                actions_taken=["[DRY_RUN] draft_created"],
                metadata={"draft_id": draft_id},
            )

        pending_dir.mkdir(parents=True, exist_ok=True)
        draft_path = pending_dir / draft_filename
        draft_path.write_text(draft_content, encoding="utf-8")

        logger.info("LinkedIn post draft created: %s", draft_filename)
        return SkillOutput(
            success=True,
            result="LinkedIn post draft created in Pending_Approval/.",
            actions_taken=[f"created: Pending_Approval/{draft_filename}"],
            metadata={
                "draft_id": draft_id,
                "draft_path": str(draft_path),
            },
        )

    def health_check(self) -> bool:
        return True


# ── module helpers ─────────────────────────────────────────────────────────────


def _extract_title(text: str) -> str:
    """Extract the first # heading from markdown text."""
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_section(text: str, section_name: str) -> str:
    """Extract text between ``## Section`` and the next ``##`` heading."""
    pattern = rf"## {re.escape(section_name)}\n\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _draft_post(title: str, raw_content: str, config: dict[str, Any]) -> str:
    """Generate a LinkedIn post draft using Gemini.

    Falls back to a structured placeholder when GEMINI_API_KEY is not
    set or the API call fails.
    """
    import os
    from pathlib import Path as _Path
    from dotenv import load_dotenv

    load_dotenv(_Path.cwd() / ".env", override=False)

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — using fallback post draft.")
    else:
        try:
            return _gemini_draft_post(
                api_key=api_key,
                title=title,
                raw_content=raw_content,
            )
        except Exception as exc:
            logger.error(
                "Gemini API post draft failed (%s: %s) — using fallback.",
                type(exc).__name__,
                exc,
                exc_info=True,
            )

    # Fallback: structured placeholder.
    return (
        f"{raw_content}\n\n"
        "[Draft generated by AI Employee — please review and "
        "customise before posting.]\n\n"
        "#LinkedIn"
    )


def _gemini_draft_post(api_key: str, title: str, raw_content: str) -> str:
    """Call Gemini to generate a polished LinkedIn post draft."""
    import requests as _requests  # type: ignore[import]

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    prompt = (
        "You are an expert LinkedIn content writer. "
        "Transform the raw content below into an engaging LinkedIn post.\n\n"
        f"Title: {title}\n\n"
        f"Raw content:\n{raw_content}\n\n"
        "Instructions:\n"
        "- Write ONLY the post body (no subject line, no metadata)\n"
        "- Keep it professional, concise, and engaging (150-300 words)\n"
        "- Use short paragraphs for readability\n"
        "- End with 2-3 relevant hashtags\n"
        "- Do NOT include preamble or explanation — output the post body only"
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = _requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
