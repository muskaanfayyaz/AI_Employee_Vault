"""Email response drafting skill — Silver tier (T039).

Reads an email TaskItem from ``Needs_Action/``, drafts a contextual
reply, and routes the draft to ``Pending_Approval/`` for human review.

FR-017: ``send_email`` ALWAYS requires approval — this skill NEVER sends
directly.  It creates an ``ApprovalRequest``-style markdown file with:

- Recipient (``To:``)
- Reply subject (``Re: <original subject>``)
- Draft body
- Original thread context

The human then reviews the draft and either approves (triggers MCP
``send_email``) or rejects (discards the draft).
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


class EmailDrafterSkill(BaseSkill):
    """Draft a reply to an email Task Item.

    The draft is written to ``Pending_Approval/`` as a markdown file
    containing full email metadata (recipient, subject, original body)
    and a draft reply body.  The human reviews and approves or rejects
    before any outbound send is triggered.

    Inputs
    ------
    skill_input.item_path:
        Path to an email TaskItem in ``Needs_Action/``.
    skill_input.vault_root:
        Vault root directory — used to locate ``Pending_Approval/``.
    skill_input.dry_run:
        When True, draft is logged but NOT written to disk.
    """

    @property
    def name(self) -> str:
        return "email_drafter"

    @property
    def version(self) -> str:
        return "1.0.0"

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        """Draft a reply and place it in ``Pending_Approval/``."""
        if skill_input.item_path is None:
            return SkillOutput(
                success=False,
                result="email_drafter requires an item_path.",
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

        if item.type != "email":
            return SkillOutput(
                success=False,
                result=(
                    f"Item {item.id[:8]} is not an email "
                    f"(type={item.type!r}). EmailDrafterSkill expects type=email."
                ),
                error=f"Expected type=email, got {item.type!r}.",
            )

        # Parse email metadata from the markdown body.
        full_text = item_path.read_text(encoding="utf-8")
        from_addr = _extract_header(full_text, "From") or "unknown@example.com"
        subject = _extract_header(full_text, "Subject") or "(no subject)"
        original_body = _extract_section(full_text, "Content")

        # Draft reply body (Claude stub per skill-interfaces.md contract).
        draft_body = _draft_reply(
            from_addr=from_addr,
            subject=subject,
            original_body=original_body,
            config=skill_input.config,
        )

        reply_subject = (
            f"Re: {subject}" if not subject.startswith("Re:") else subject
        )
        draft_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        draft_filename = f"draft-email-{draft_id[:8]}.md"
        pending_dir = skill_input.vault_root / "Pending_Approval"

        draft_content = (
            "---\n"
            f"id: {draft_id}\n"
            "type: email\n"
            "source: email_drafter\n"
            "priority: medium\n"
            "status: pending_approval\n"
            "requires_approval: true\n"
            "classification: local_only\n"
            f"created_at: {now}\n"
            f"updated_at: {now}\n"
            "tags: [draft, email-reply]\n"
            "approval:\n"
            f"  proposed_action: \"Send email reply to {from_addr}\"\n"
            "  reasoning: \"FR-017 — outbound email requires human approval\"\n"
            f"  original_item_id: {item.id}\n"
            f"  requested_at: {now}\n"
            "  decision: pending\n"
            "  decided_at: null\n"
            "  feedback: null\n"
            "---\n\n"
            "# Draft Email Reply\n\n"
            f"**To**: {from_addr}  \n"
            f"**Subject**: {reply_subject}  \n"
            f"**Original Item**: {item_path.name}  \n\n"
            "## Draft Body\n\n"
            f"{draft_body}\n\n"
            "## Original Context\n\n"
            f"{original_body or '_No content extracted._'}\n\n"
            "## Approval Instructions\n\n"
            "- [ ] Review draft reply above\n"
            "- [ ] Edit if needed\n"
            "- [ ] Change `decision: pending` → `decision: approved` to send\n"
            "- [ ] Change `decision: pending` → `decision: rejected` to discard\n"
        )

        if skill_input.dry_run:
            logger.info(
                "[DRY_RUN] Would create draft: %s → Pending_Approval/%s",
                item_path.name,
                draft_filename,
            )
            return SkillOutput(
                success=True,
                result=f"[DRY_RUN] Would draft reply to {from_addr}.",
                actions_taken=["[DRY_RUN] draft_created"],
                metadata={
                    "draft_id": draft_id,
                    "to": from_addr,
                    "subject": reply_subject,
                },
            )

        pending_dir.mkdir(parents=True, exist_ok=True)
        draft_path = pending_dir / draft_filename
        draft_path.write_text(draft_content, encoding="utf-8")

        logger.info(
            "Email draft created: %s (to: %s | subject: %s)",
            draft_filename,
            from_addr,
            reply_subject,
        )
        return SkillOutput(
            success=True,
            result=f"Draft reply to {from_addr} created in Pending_Approval/.",
            actions_taken=[f"created: Pending_Approval/{draft_filename}"],
            metadata={
                "draft_id": draft_id,
                "draft_path": str(draft_path),
                "to": from_addr,
                "subject": reply_subject,
            },
        )

    def health_check(self) -> bool:
        return True


# ── module helpers ────────────────────────────────────────────────────────────


def _extract_header(text: str, header_name: str) -> str:
    """Extract a markdown-bold header value like ``**From**: value``."""
    pattern = rf"\*\*{re.escape(header_name)}\*\*:\s*(.+)"
    match = re.search(pattern, text)
    return match.group(1).strip().rstrip("  ").strip() if match else ""


def _extract_section(text: str, section_name: str) -> str:
    """Extract text between ``## Section`` and the next ``##`` heading."""
    pattern = rf"## {re.escape(section_name)}\n\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _draft_reply(
    from_addr: str,
    subject: str,
    original_body: str,
    config: dict[str, Any],
) -> str:
    """Generate a contextual draft reply using Gemini.

    Falls back to a structured placeholder when GEMINI_API_KEY is
    not set or the API call fails, so the approval workflow remains
    testable without credentials.
    """
    import os
    from pathlib import Path as _Path
    from dotenv import load_dotenv

    # Safety net: load .env in case this skill runs before src.config is imported.
    load_dotenv(_Path.cwd() / ".env", override=False)

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — using fallback draft.")
    else:
        try:
            return _gemini_draft_reply(
                api_key=api_key,
                from_addr=from_addr,
                subject=subject,
                original_body=original_body,
            )
        except Exception as exc:
            logger.error(
                "Gemini API draft failed (%s: %s) — using fallback.",
                type(exc).__name__, exc,
                exc_info=True,
            )

    # Fallback: structured placeholder.
    name_part = from_addr.split("<")[0].strip().rstrip(",").strip()
    if "@" in name_part:
        name_part = name_part.split("@")[0].capitalize()
    greeting = f"Dear {name_part}," if name_part else "Dear sender,"
    return (
        f"{greeting}\n\n"
        "Thank you for your message. I have reviewed the content "
        "and will follow up accordingly.\n\n"
        "[Draft generated by AI Employee — please review and "
        "customise before sending.]\n\n"
        "Best regards,\n"
        "_[Your name]_"
    )


def _gemini_draft_reply(
    api_key: str,
    from_addr: str,
    subject: str,
    original_body: str,
) -> str:
    """Call Gemini to generate a contextual reply draft."""
    import os as _os
    from google import genai  # type: ignore[import]

    # Ensure our explicit key is used — suppress any GOOGLE_API_KEY env var
    # that the new SDK prefers over GEMINI_API_KEY when both are set.
    _os.environ.pop("GOOGLE_API_KEY", None)
    client = genai.Client(api_key=api_key)

    prompt = (
        f"You are an AI email assistant. Draft a professional, concise reply to the email below.\n\n"
        f"From: {from_addr}\n"
        f"Subject: {subject}\n\n"
        f"Original email:\n{original_body}\n\n"
        "Instructions:\n"
        "- Write ONLY the reply body (no subject line, no 'From:' headers)\n"
        "- Be professional and appropriately concise\n"
        "- Address the specific content and requests in the email\n"
        "- End with 'Best regards,' and a placeholder '_[Your name]_'\n"
        "- If the email requests an action (resignation, payment, etc.) respond thoughtfully — acknowledge receipt and state you will review/respond\n"
        "- Do NOT include any preamble or explanation — output the draft body only"
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text.strip()
