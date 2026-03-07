"""Multi-platform social media poster skill — Gold Tier (FR-G012–G015, FR-G044).

Drafts platform-appropriate posts for LinkedIn, Facebook, Instagram, and Twitter/X
from a vault item, then routes each draft to ``Pending_Approval/`` for human review.

This skill NEVER publishes directly.  Every draft must receive an explicit
``decision: approved`` before any outbound post is triggered (FR-G015).

Platform constraints (FR-G014):

    Platform   | Max chars | Hashtags | Notes
    -----------|-----------|----------|-------
    linkedin   | 3000      | 5        | Professional tone, 1-3 paras
    facebook   | 63206     | 5        | Conversational, may be longer
    instagram  | 2200      | 30       | Visual cues, emoji friendly
    twitter    | 280       | 3        | Concise, punchy

Credential leak detection (FR-G044):
    Before writing any draft, the skill scans the post content for common
    credential patterns (API keys, tokens, passwords, secrets).  If a match
    is found the draft is REJECTED and a ``Needs_Action`` flag is created.

Security (FR-G041):
    Credentials are referenced only by env var name in config — never stored
    in vault files or logs.

Config schema (per-platform, e.g. ``Config/facebook_watcher.yaml``)::

    social:
      platform: "facebook"           # linkedin | facebook | instagram | twitter
      enabled: false
      credential_refs:
        access_token: "FACEBOOK_ACCESS_TOKEN"
        page_id: "FACEBOOK_PAGE_ID"   # platform-specific
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


# ── Platform metadata ─────────────────────────────────────────────────────────

_PLATFORM_META: dict[str, dict[str, Any]] = {
    "linkedin": {
        "display": "LinkedIn",
        "max_chars": 3000,
        "max_hashtags": 5,
        "tone": "professional",
        "instructions": (
            "Keep it professional and insightful (150–300 words). "
            "Use short paragraphs. End with 2–3 relevant hashtags."
        ),
    },
    "facebook": {
        "display": "Facebook",
        "max_chars": 63206,
        "max_hashtags": 5,
        "tone": "conversational",
        "instructions": (
            "Write in a friendly, conversational tone (100–250 words). "
            "Encourage engagement. End with 1–2 hashtags."
        ),
    },
    "instagram": {
        "display": "Instagram",
        "max_chars": 2200,
        "max_hashtags": 30,
        "tone": "visual",
        "instructions": (
            "Write a caption for an image post (80–150 words). "
            "Use an engaging hook. Add 5–10 relevant hashtags at the end."
        ),
    },
    "twitter": {
        "display": "Twitter/X",
        "max_chars": 280,
        "max_hashtags": 3,
        "tone": "concise",
        "instructions": (
            "Write a concise, punchy tweet (max 260 characters to leave room for hashtags). "
            "End with 1–2 relevant hashtags."
        ),
    },
}

# Configured platforms (union of all available)
_ALL_PLATFORMS = tuple(_PLATFORM_META.keys())


# ── Credential-leak detection patterns (FR-G044) ──────────────────────────────

_CREDENTIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:api[_-]?key|apikey)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:secret|token|password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),                 # base64-ish tokens
    re.compile(r"sk-[A-Za-z0-9]{32,}"),                       # OpenAI-style keys
    re.compile(r"ya29\.[A-Za-z0-9_\-]+"),                     # Google OAuth tokens
    re.compile(r"ghp_[A-Za-z0-9]{36}"),                       # GitHub PATs
    re.compile(r"AAAA[A-Za-z0-9+/]{100,}"),                   # FB-style tokens
]


def _contains_credentials(text: str) -> str | None:
    """Return the first matched pattern description if credentials found, else None."""
    for pattern in _CREDENTIAL_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Pattern: {pattern.pattern[:60]} matched at pos {match.start()}"
    return None


# ── Skill ─────────────────────────────────────────────────────────────────────


class SocialPosterSkill(BaseSkill):
    """Draft social media posts for all configured platforms and route to approval.

    Processes a vault item tagged ``type: social`` and creates one approval
    draft per configured, enabled platform.

    Parameters
    ----------
    platforms:
        Optional explicit list of platform slugs to draft for.  Defaults to
        all platforms whose config shows ``enabled: true``.
    """

    def __init__(self, platforms: list[str] | None = None) -> None:
        self._explicit_platforms = platforms

    @property
    def name(self) -> str:
        return "social_poster"

    @property
    def version(self) -> str:
        return "1.0.0"

    def health_check(self) -> bool:
        return True

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        """Draft posts for all enabled platforms and route to Pending_Approval."""
        if skill_input.item_path is None:
            return SkillOutput(
                success=False,
                result="social_poster requires an item_path.",
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

        if item.type not in ("social", "social_post"):
            return SkillOutput(
                success=False,
                result=(
                    f"Item {item.id[:8]} is not a social post "
                    f"(type={item.type!r}). SocialPosterSkill expects type=social or social_post."
                ),
                error=f"Expected type=social or social_post, got {item.type!r}.",
            )

        full_text = item_path.read_text(encoding="utf-8")
        raw_content = _extract_section(full_text, "Content") or _extract_section(full_text, "Post") or item.body.strip()
        title = _extract_title(full_text) or item_path.stem
        source_image_url = _extract_section(full_text, "Image URL").strip()

        # Determine which platforms to draft for.
        # Priority: 1) explicit override  2) ## Platform section in item
        #           3) item.platforms field (from YAML frontmatter)  4) config/tags
        config = skill_input.config
        item_platform = _extract_section(full_text, "Platform").strip().lower()
        if item_platform and item_platform in _PLATFORM_META:
            platforms = [item_platform]
        elif item.platforms:
            platforms = [p for p in item.platforms if p in _PLATFORM_META]
        else:
            fm_platforms = _extract_frontmatter_platforms(full_text)
            platforms = fm_platforms if fm_platforms else self._resolve_platforms(config)

        # Fallback: read Config/<platform>_watcher.yaml from vault when no platforms
        # resolved from item content or in-memory config.
        if not platforms:
            import yaml as _yaml
            vault_root = skill_input.vault_root
            for _p in _ALL_PLATFORMS:
                _cfg_path = vault_root / "Config" / f"{_p}_watcher.yaml"
                if _cfg_path.exists():
                    try:
                        _data = _yaml.safe_load(_cfg_path.read_text(encoding="utf-8")) or {}
                        _social = _data.get("social", _data)
                        if _social.get("enabled", False):
                            platforms.append(_p)
                    except Exception:
                        pass

        if not platforms:
            return SkillOutput(
                success=False,
                result="No enabled social platforms configured.",
                error="Add a '## Platform' section (e.g. 'twitter') to the item, or enable a platform in Config/<platform>_watcher.yaml.",
            )

        pending_dir = skill_input.vault_root / "Pending_Approval"
        needs_action_dir = skill_input.vault_root / "Needs_Action"
        now = datetime.now(timezone.utc)
        actions_taken: list[str] = []
        drafts_created: list[str] = []
        credential_flags: list[str] = []

        for platform in platforms:
            meta = _PLATFORM_META.get(platform)
            if meta is None:
                logger.warning("social_poster: unknown platform %r — skipping", platform)
                continue

            # Draft the post body (Gemini or fallback).
            post_body = _draft_post(
                platform=platform,
                meta=meta,
                title=title,
                raw_content=raw_content,
                config=config,
            )

            # FR-G044: Credential leak detection.
            leak = _contains_credentials(post_body)
            if leak:
                logger.error(
                    "social_poster [FR-G044]: credential pattern detected in %s draft — REJECTING. %s",
                    platform, leak
                )
                credential_flags.append(platform)
                if not skill_input.dry_run:
                    _create_credential_flag_item(needs_action_dir, item, platform, leak, now)
                    actions_taken.append(
                        f"[CREDENTIAL_FLAG] Needs_Action item created for {platform} draft"
                    )
                continue

            # Enforce character limit.
            max_chars = meta["max_chars"]
            if len(post_body) > max_chars:
                post_body = post_body[:max_chars - 3] + "..."
                logger.warning(
                    "social_poster: %s post truncated to %d chars", platform, max_chars
                )

            draft_id = str(uuid.uuid4())
            ts = now.isoformat()
            draft_filename = f"draft-{platform}-post-{draft_id[:8]}.md"

            draft_content = _build_draft_content(
                platform=platform,
                meta=meta,
                draft_id=draft_id,
                ts=ts,
                item=item,
                item_path=item_path,
                post_body=post_body,
                raw_content=raw_content,
                image_url=source_image_url,
            )

            if skill_input.dry_run:
                logger.info(
                    "[DRY_RUN] Would create %s post draft: %s → Pending_Approval/%s",
                    meta["display"], item_path.name, draft_filename,
                )
                actions_taken.append(f"[DRY_RUN] would draft {platform}: {draft_filename}")
            else:
                pending_dir.mkdir(parents=True, exist_ok=True)
                (pending_dir / draft_filename).write_text(draft_content, encoding="utf-8")
                logger.info("%s post draft created: %s", meta["display"], draft_filename)
                actions_taken.append(f"created: Pending_Approval/{draft_filename}")
                drafts_created.append(f"{meta['display']}:{draft_filename}")

        if credential_flags:
            actions_taken.append(
                f"[CREDENTIAL_FLAG] Drafts rejected for platforms: {', '.join(credential_flags)}"
            )

        total_drafted = len(drafts_created) + (len(platforms) - len(drafts_created) - len(credential_flags))
        dry_suffix = " [DRY_RUN]" if skill_input.dry_run else ""
        return SkillOutput(
            success=True,
            result=(
                f"Social drafts created for {len(drafts_created)} platform(s)"
                f"{', credential flags: ' + str(len(credential_flags)) if credential_flags else ''}"
                f"{dry_suffix}"
            ),
            actions_taken=actions_taken,
            metadata={
                "platforms_attempted": platforms,
                "drafts_created": drafts_created,
                "credential_flags": credential_flags,
            },
        )

    # ── private helpers ───────────────────────────────────────────────────────

    def _resolve_platforms(self, config: dict[str, Any]) -> list[str]:
        """Return list of enabled platform slugs from config or explicit override."""
        if self._explicit_platforms is not None:
            return [p for p in self._explicit_platforms if p in _PLATFORM_META]

        # Config may contain a 'platforms' dict keyed by platform name.
        platforms_cfg: dict = config.get("platforms", {})
        enabled = []
        for platform in _ALL_PLATFORMS:
            pcfg = platforms_cfg.get(platform, {})
            if pcfg.get("enabled", False):
                enabled.append(platform)
        return enabled


# ── Module helpers ─────────────────────────────────────────────────────────────


def _extract_title(text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_section(text: str, section_name: str) -> str:
    pattern = rf"## {re.escape(section_name)}\n\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _build_draft_content(
    *,
    platform: str,
    meta: dict[str, Any],
    draft_id: str,
    ts: str,
    item: Any,
    item_path: Path,
    post_body: str,
    raw_content: str,
    image_url: str = "",
) -> str:
    """Build the markdown approval draft file content."""
    char_count = len(post_body)
    return (
        "---\n"
        f"id: {draft_id}\n"
        "type: social\n"
        f"source: social_poster_{platform}\n"
        "priority: medium\n"
        "status: pending_approval\n"
        "requires_approval: true\n"
        "classification: local_only\n"
        f"created_at: {ts}\n"
        f"updated_at: {ts}\n"
        f"tags: [draft, {platform}-post]\n"
        "approval:\n"
        f'  proposed_action: "Post to {meta["display"]}"\n'
        '  reasoning: "FR-G015 — outbound social post requires human approval"\n'
        f"  original_item_id: {item.id}\n"
        f"  requested_at: {ts}\n"
        "  decision: pending\n"
        "  decided_at: null\n"
        "  feedback: null\n"
        "---\n\n"
        f"# {meta['display']} Post Draft\n\n"
        f"**Platform**: {meta['display']}  \n"
        f"**Character Count**: {char_count} / {meta['max_chars']}  \n"
        f"**Original Item**: {item_path.name}  \n\n"
        "## Post Content\n\n"
        f"{post_body}\n\n"
        + (
            "## Image URL\n\n"
            + (f"{image_url}\n\n" if image_url else "_Paste a public image URL here (required for Instagram feed posts)._\n\n")
            if platform == "instagram" else
            "## Image URL\n\n"
            + (f"{image_url}\n\n" if image_url else "_Paste a public image URL here to attach an image to this LinkedIn post (optional)._\n\n")
            if platform == "linkedin" else ""
        )
        + "## Original Context\n\n"
        f"{raw_content or '_No content extracted._'}\n\n"
        "## Approval Instructions\n\n"
        "- [ ] Review draft post above\n"
        + (
            "- [ ] Add a public image URL in the Image URL section above (required)\n"
            if platform == "instagram" else
            "- [ ] Optionally add a public image URL in the Image URL section above\n"
            if platform == "linkedin" else ""
        )
        + "- [ ] Edit if needed (editing resets approval)\n"
        "- [ ] Change `decision: pending` → `decision: approved` to schedule publish\n"
        "- [ ] Change `decision: pending` → `decision: rejected` to discard\n"
        "- [ ] Note: any edit to Post Content requires a new approval cycle\n"
    )


def _create_credential_flag_item(
    needs_action_dir: Path,
    item: Any,
    platform: str,
    leak_detail: str,
    now: datetime,
) -> None:
    """Create a Needs_Action flag for a credential-leak rejection."""
    needs_action_dir.mkdir(parents=True, exist_ok=True)
    flag_id = str(uuid.uuid4())
    ts = now.isoformat()
    filename = f"credential-flag-{platform}-{flag_id[:8]}.md"
    content = (
        "---\n"
        f"id: {flag_id}\n"
        "type: security_flag\n"
        "source: social_poster\n"
        "priority: high\n"
        "status: needs_action\n"
        "requires_approval: false\n"
        f"created_at: {ts}\n"
        f"updated_at: {ts}\n"
        f"tags: [security, credential_leak, {platform}]\n"
        "---\n\n"
        f"# Credential Leak Detected in {platform.title()} Post Draft\n\n"
        f"**Platform**: {platform}  \n"
        f"**Original Item**: {item.id}  \n"
        f"**Detected At**: {ts}  \n"
        f"**Detection Detail**: {leak_detail}  \n\n"
        "## Action Required\n\n"
        "The drafted social post was **rejected** because it appears to contain "
        "credential-like patterns (API keys, tokens, passwords, or secrets).\n\n"
        "1. Review the original item content for any embedded credentials\n"
        "2. Remove credentials before re-drafting\n"
        "3. Rotate any credentials that may have been exposed\n"
        "4. Re-submit the content brief without sensitive data\n"
    )
    (needs_action_dir / filename).write_text(content, encoding="utf-8")
    logger.warning(
        "social_poster [FR-G044]: Credential flag created: Needs_Action/%s", filename
    )


def _extract_frontmatter_platforms(text: str) -> list[str]:
    """Extract platform(s) from YAML frontmatter.

    Handles both:
      platform: linkedin          (singular — single platform)
      platforms: [twitter, linkedin]  (plural — multiple platforms)
    """
    if not text.startswith("---"):
        return []
    try:
        end = text.index("---", 3)
        fm = text[3:end]
    except ValueError:
        return []
    for line in fm.splitlines():
        stripped = line.strip()
        # Singular: platform: linkedin
        if stripped.startswith("platform:") and not stripped.startswith("platforms:"):
            _, _, raw = stripped.partition(":")
            p = raw.strip().strip('"').strip("'").lower()
            return [p] if p in _PLATFORM_META else []
        # Plural: platforms: [twitter, linkedin]
        if stripped.startswith("platforms:"):
            _, _, raw = stripped.partition(":")
            raw = raw.strip().strip("[]")
            result = [p.strip().strip('"').strip("'").lower() for p in raw.split(",") if p.strip()]
            return [p for p in result if p in _PLATFORM_META]
    return []


def _draft_post(
    *,
    platform: str,
    meta: dict[str, Any],
    title: str,
    raw_content: str,
    config: dict[str, Any],
) -> str:
    """Generate a post draft using Gemini, falling back to a structured placeholder."""
    import os
    from pathlib import Path as _Path
    from dotenv import load_dotenv  # type: ignore[import]

    load_dotenv(_Path.cwd() / ".env", override=False)

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning(
            "GEMINI_API_KEY not set — using fallback draft for %s", platform
        )
    else:
        try:
            return _gemini_draft_post(
                api_key=api_key,
                platform=platform,
                meta=meta,
                title=title,
                raw_content=raw_content,
            )
        except Exception as exc:
            logger.error(
                "Gemini post draft failed for %s (%s: %s) — using fallback",
                platform, type(exc).__name__, exc,
            )

    # Fallback: platform-specific placeholder.
    base = raw_content or title
    if platform == "twitter":
        truncated = base[:220] if len(base) > 220 else base
        return f"{truncated}\n\n[Draft — review before posting] #{platform}"
    return (
        f"{base}\n\n"
        f"[{meta['display']} draft — please review and customise]\n\n"
        f"#{platform}"
    )


def _gemini_draft_post(
    *,
    api_key: str,
    platform: str,
    meta: dict[str, Any],
    title: str,
    raw_content: str,
) -> str:
    """Call Gemini Flash to generate a polished platform-specific post draft."""
    import requests as _requests  # type: ignore[import]

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    prompt = (
        f"You are an expert {meta['display']} content writer.\n"
        f"Transform the raw content below into an engaging {meta['display']} post.\n\n"
        f"Title: {title}\n\n"
        f"Raw content:\n{raw_content}\n\n"
        f"Instructions:\n"
        f"- {meta['instructions']}\n"
        f"- Character limit: {meta['max_chars']}\n"
        f"- Max hashtags: {meta['max_hashtags']}\n"
        f"- Write ONLY the post body (no subject line, no metadata)\n"
        f"- Do NOT include preamble or explanation — output only the post text\n"
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = _requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
