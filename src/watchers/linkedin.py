"""LinkedIn API watcher — Silver tier.

Polls the LinkedIn API for new connection requests (invitations) and
direct messages. Creates a markdown Task Item in ``Needs_Action/``
for each new event.

Credentials
-----------
Set ``LINKEDIN_ACCESS_TOKEN`` in ``.env``.  Obtain a token by running
``python -m src.scripts.linkedin_auth`` (requires a LinkedIn App with
OAuth 2.0 credentials at Config/linkedin_credentials.json).

Config schema (matching Watcher Configuration from data-model.md)::

    watcher:
      name: "linkedin-inbox"
      type: "linkedin"
      enabled: false
      polling_interval_seconds: 300
      state_file: "Config/linkedin_processed_ids.json"
      api_url: "https://api.linkedin.com/v2"
      watch_invitations: true
      watch_messages: false   # requires LinkedIn Partner / MDP access
      credential_ref: LINKEDIN_ACCESS_TOKEN

DRY_RUN semantics (inherited from BaseWatcher):
    Events are detected and logged; ``create_action_file()`` is NOT
    called; no IDs are marked as processed.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.watchers.base import BaseWatcher

logger = logging.getLogger(__name__)


class LinkedInWatcher(BaseWatcher):
    """Polls the LinkedIn API for new invitations and messages.

    Parameters
    ----------
    config:
        Config dict matching the Watcher Configuration schema
        (see module docstring).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        watcher_cfg = config.get("watcher", config)

        # Credential reference — env var name, NEVER the raw token value.
        self._credential_ref: str = watcher_cfg.get(
            "credential_ref", "LINKEDIN_ACCESS_TOKEN"
        )
        self._api_url: str = watcher_cfg.get(
            "api_url", "https://api.linkedin.com/v2"
        )
        self._watch_invitations: bool = watcher_cfg.get("watch_invitations", True)
        self._watch_messages: bool = watcher_cfg.get("watch_messages", False)

        # State file for deduplication (relative to vault root).
        self._state_file_rel: str = watcher_cfg.get(
            "state_file", "Config/linkedin_processed_ids.json"
        )
        self._state_file: Path | None = None
        self._processed_ids: set[str] = set()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def run(self, inbox_path: Path, *, dry_run: bool = False) -> None:
        """Override to initialise the state file path before the poll loop."""
        vault_root = inbox_path.parent
        self._state_file = vault_root / self._state_file_rel
        self._processed_ids = self._load_processed_ids()
        self._logger.info(
            "LinkedInWatcher starting | state_file=%s | known_ids=%d | dry_run=%s",
            self._state_file,
            len(self._processed_ids),
            dry_run,
        )
        super().run(inbox_path, dry_run=dry_run)

    def health_check(self) -> bool:
        """Return True when enabled and the access token env var is set."""
        if not self._enabled:
            return False
        return bool(os.getenv(self._credential_ref, ""))

    # ── abstract implementations ──────────────────────────────────────────────

    def check_for_updates(self) -> list[dict[str, Any]]:
        """Poll the LinkedIn API for new invitations and/or messages.

        Returns an empty list when credentials are unavailable or on
        API error — the watcher loop will retry on the next interval.
        """
        token = os.getenv(self._credential_ref, "")
        if not token:
            self._logger.warning(
                "LinkedIn access token not set (%s) — skipping poll",
                self._credential_ref,
            )
            return []

        events: list[dict[str, Any]] = []

        if self._watch_invitations:
            try:
                events.extend(self._fetch_invitations(token))
            except Exception as exc:
                self._logger.error("LinkedIn invitations poll failed: %s", exc)

        if self._watch_messages:
            try:
                events.extend(self._fetch_messages(token))
            except Exception as exc:
                self._logger.error("LinkedIn messages poll failed: %s", exc)

        return events

    def create_action_file(
        self, event: dict[str, Any], inbox_path: Path
    ) -> Path:
        """Write a markdown Task Item for a LinkedIn invitation or message.

        Parameters
        ----------
        event:
            Dict produced by :meth:`check_for_updates`.
        inbox_path:
            Destination folder (``Needs_Action/`` in the vault).

        Returns
        -------
        Path
            Absolute path of the created ``.md`` file.
        """
        event_id: str = event["event_id"]
        event_type: str = event.get("event_type", "message")
        from_name: str = event.get("from_name", "unknown")
        body: str = event.get("body", "")

        slug = re.sub(r"[^\w]+", "-", from_name).strip("-").lower()[:32]
        prefix = "li-inv" if event_type == "invitation" else "li-msg"
        filename = f"{prefix}-{event_id[:8]}-{slug}.md"
        path = inbox_path / filename

        item_id: str = event.get("item_id", str(uuid.uuid4()))
        now = datetime.now(timezone.utc).isoformat()

        if event_type == "invitation":
            heading = f"LinkedIn Connection Request from {from_name}"
            section_label = "Message"
            next_steps = (
                "- [ ] Review connection request\n"
                "- [ ] Accept or ignore on LinkedIn\n"
                "- [ ] Send a reply message if accepted\n"
            )
        else:
            heading = f"LinkedIn Message from {from_name}"
            section_label = "Content"
            next_steps = (
                "- [ ] Review message\n"
                "- [ ] Draft response (if required)\n"
                "- [ ] Execute or delegate\n"
            )

        content = (
            "---\n"
            f"id: {item_id}\n"
            "type: message\n"
            "source: linkedin\n"
            f"source_id: {event_id}\n"
            "priority: medium\n"
            "status: needs_action\n"
            "requires_approval: false\n"
            "classification: local_only\n"
            f"created_at: {now}\n"
            f"updated_at: {now}\n"
            f"tags: [linkedin, {event_type}]\n"
            "---\n\n"
            f"# {heading}\n\n"
            f"**From**: {from_name}  \n"
            f"**Type**: {event_type}  \n"
            f"**Event ID**: `{event_id}`  \n"
            f"**Received**: {event.get('timestamp', now)}  \n\n"
            f"## {section_label}\n\n"
            f"{body or '_No content._'}\n\n"
            "## Next Steps\n\n"
            f"{next_steps}"
        )

        path.write_text(content, encoding="utf-8")

        # Track this ID so it is never processed again.
        self._processed_ids.add(event_id)
        self._save_processed_ids()

        self._logger.info(
            "LinkedIn item created: %s (from: %s, type: %s)",
            path.name,
            from_name,
            event_type,
        )
        return path

    # ── private helpers ───────────────────────────────────────────────────────

    def _fetch_invitations(self, token: str) -> list[dict[str, Any]]:
        """Fetch pending connection requests from the LinkedIn Invitations API.

        Uses ``urllib.request`` (stdlib) to avoid additional dependencies.
        Returns an empty list on 401/403 (missing scope) and logs a
        warning so the operator knows what to fix.
        """
        import urllib.request
        import urllib.error

        url = (
            f"{self._api_url}/invitations"
            "?q=receivedInvitations&invitationType=CONNECTION&status=PENDING"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                self._logger.warning(
                    "LinkedIn Invitations API returned HTTP %d — "
                    "the Invitations API requires a LinkedIn product with "
                    "invitation access (not included in basic OpenID Connect). "
                    "Set watch_invitations: false in linkedin_watcher.yaml to suppress.",
                    exc.code,
                )
                return []
            raise

        elements = data.get("elements", [])
        events: list[dict[str, Any]] = []

        for inv in elements:
            inv_id = str(inv.get("entityUrn", inv.get("id", "")))
            if not inv_id or inv_id in self._processed_ids:
                continue

            from_name = _extract_invitation_name(inv)
            message = inv.get("message", "")

            events.append(
                {
                    "event_id": inv_id,
                    "item_id": str(uuid.uuid4()),
                    "event_type": "invitation",
                    "from_name": from_name,
                    "body": message,
                    "timestamp": str(inv.get("sentTime", "")),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        self._logger.info(
            "LinkedIn: %d new invitation(s) detected", len(events)
        )
        return events

    def _fetch_messages(self, token: str) -> list[dict[str, Any]]:
        """Fetch recent conversations from the LinkedIn Conversations API.

        This endpoint requires LinkedIn Partner / Marketing Developer
        Platform (MDP) access.  Most standard developer apps will
        receive a 403 — the method returns an empty list and logs a
        one-time warning to keep the poll loop clean.
        Set ``watch_messages: false`` in the config to suppress.
        """
        import urllib.request
        import urllib.error

        url = f"{self._api_url}/conversations?q=participant&count=20"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                self._logger.warning(
                    "LinkedIn Conversations API returned HTTP %d — "
                    "Partner / MDP access is required. "
                    "Set watch_messages: false in linkedin_watcher.yaml to suppress.",
                    exc.code,
                )
                return []
            raise

        elements = data.get("elements", [])
        events: list[dict[str, Any]] = []

        for conv in elements:
            conv_id = str(conv.get("entityUrn", conv.get("id", "")))
            if not conv_id or conv_id in self._processed_ids:
                continue

            from_name = _extract_conversation_name(conv)
            last_activity = conv.get("lastActivityAt", "")

            events.append(
                {
                    "event_id": conv_id,
                    "item_id": str(uuid.uuid4()),
                    "event_type": "message",
                    "from_name": from_name,
                    "body": "_LinkedIn message — open the LinkedIn app to read._",
                    "timestamp": str(last_activity),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        self._logger.info(
            "LinkedIn: %d new conversation(s) detected", len(events)
        )
        return events

    def _load_processed_ids(self) -> set[str]:
        """Load the set of already-processed event IDs from the state file."""
        if self._state_file is None or not self._state_file.exists():
            return set()
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            ids: set[str] = set(data.get("processed_ids", []))
            self._logger.debug(
                "Loaded %d processed LinkedIn ID(s) from %s",
                len(ids),
                self._state_file,
            )
            return ids
        except (json.JSONDecodeError, OSError) as exc:
            self._logger.warning(
                "Could not load LinkedIn processed IDs from %s: %s "
                "— starting fresh",
                self._state_file,
                exc,
            )
            return set()

    def _save_processed_ids(self) -> None:
        """Persist the processed event ID set to the state file."""
        if self._state_file is None:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "processed_ids": sorted(self._processed_ids),
                "count": len(self._processed_ids),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._state_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            self._logger.error(
                "Failed to persist LinkedIn processed IDs to %s: %s",
                self._state_file,
                exc,
            )


# ── module helpers ─────────────────────────────────────────────────────────────


def _extract_invitation_name(inv: dict[str, Any]) -> str:
    """Best-effort extraction of a sender display name from an invitation dict."""
    # v2 Invitations API may nest the name under fromMember or miniProfile.
    for key in ("fromMember", "genericInvitation", "inviter"):
        member = inv.get(key, {})
        if member:
            first = member.get("firstName", "")
            last = member.get("lastName", "")
            # localized values may be wrapped: {"localized": {"en_US": "John"}}
            if isinstance(first, dict):
                first = next(iter(first.get("localized", {}).values()), "")
            if isinstance(last, dict):
                last = next(iter(last.get("localized", {}).values()), "")
            name = f"{first} {last}".strip()
            if name:
                return name
    return "LinkedIn Member"


def _extract_conversation_name(conv: dict[str, Any]) -> str:
    """Best-effort extraction of the other participant's name from a conversation."""
    participants = conv.get("participants", [])
    for p in participants:
        # Voyager messaging schema nests miniProfile under a long key.
        for value in p.values() if isinstance(p, dict) else []:
            if isinstance(value, dict):
                mp = value.get("miniProfile", {})
                first = mp.get("firstName", "")
                last = mp.get("lastName", "")
                name = f"{first} {last}".strip()
                if name:
                    return name
    return "LinkedIn Member"


# ── standalone entry point ────────────────────────────────────────────────────


def _load_config(vault_root: Path) -> dict[str, Any]:
    """Load Config/linkedin_watcher.yaml or return built-in defaults."""
    config_path = vault_root / "Config" / "linkedin_watcher.yaml"
    if config_path.exists():
        try:
            import yaml  # type: ignore[import]

            with config_path.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh)
        except Exception as exc:
            logger.warning(
                "Could not load %s: %s — using defaults", config_path, exc
            )

    return {
        "watcher": {
            "name": "linkedin-inbox",
            "type": "linkedin",
            "enabled": False,
            "polling_interval_seconds": 300,
            "state_file": "Config/linkedin_processed_ids.json",
            "api_url": "https://api.linkedin.com/v2",
            "watch_invitations": True,
            "watch_messages": False,
            "credential_ref": "LINKEDIN_ACCESS_TOKEN",
        }
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        from src.config import DRY_RUN, VAULT_ROOT
    except ImportError:
        DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")
        VAULT_ROOT = Path(os.getenv("VAULT_ROOT", str(Path.cwd()))).resolve()

    config = _load_config(VAULT_ROOT)
    watcher = LinkedInWatcher(config)
    inbox_path = VAULT_ROOT / "Needs_Action"
    inbox_path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "LinkedInWatcher | vault=%s | dry_run=%s | interval=%ds",
        VAULT_ROOT,
        DRY_RUN,
        watcher.polling_interval,
    )
    watcher.run(inbox_path, dry_run=DRY_RUN)
