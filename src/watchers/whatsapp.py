"""WhatsApp Business API message watcher — Silver tier (T037).

Polls the WhatsApp Business API for new messages from configured
contacts/groups. Creates a markdown Task Item in ``Needs_Action/``
for each new message.

Credentials
-----------
Set ``WHATSAPP_API_TOKEN`` in ``.env``.  The credential is referenced
by env var name — never stored raw in code.

Config schema (matching Watcher Configuration from data-model.md)::

    watcher:
      name: "whatsapp-inbox"
      type: "whatsapp"
      enabled: true
      polling_interval_seconds: 30
      state_file: "Config/whatsapp_processed_ids.json"
      api_url: "https://graph.facebook.com/v18.0"
      phone_number_id: "YOUR_PHONE_NUMBER_ID"
      filters:
        contacts: ["+1234567890"]
        groups: ["family-chat"]
      credential_ref: WHATSAPP_API_TOKEN

DRY_RUN semantics (inherited from BaseWatcher):
    Messages are detected and logged; ``create_action_file()`` is NOT
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


class WhatsAppWatcher(BaseWatcher):
    """Polls the WhatsApp Business API for new messages.

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
            "credential_ref", "WHATSAPP_API_TOKEN"
        )
        self._api_url: str = watcher_cfg.get(
            "api_url", "https://graph.facebook.com/v18.0"
        )
        self._phone_number_id: str = watcher_cfg.get("phone_number_id", "")
        self._filters: dict[str, Any] = watcher_cfg.get("filters", {})

        # State file for deduplication (relative to vault root).
        self._state_file_rel: str = watcher_cfg.get(
            "state_file", "Config/whatsapp_processed_ids.json"
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
            "WhatsAppWatcher starting | state_file=%s | known_ids=%d | dry_run=%s",
            self._state_file,
            len(self._processed_ids),
            dry_run,
        )
        super().run(inbox_path, dry_run=dry_run)

    def health_check(self) -> bool:
        """Return True when enabled and the API token env var is set."""
        if not self._enabled:
            return False
        return bool(os.getenv(self._credential_ref, ""))

    # ── abstract implementations ──────────────────────────────────────────────

    def check_for_updates(self) -> list[dict[str, Any]]:
        """Poll the WhatsApp Business API for new messages.

        Returns an empty list when credentials are unavailable or on
        API error — the watcher loop will retry on the next interval.
        """
        token = os.getenv(self._credential_ref, "")
        if not token:
            self._logger.warning(
                "WhatsApp API token not set (%s) — skipping poll",
                self._credential_ref,
            )
            return []

        try:
            return self._fetch_messages(token)
        except Exception as exc:
            self._logger.error("WhatsApp API poll failed: %s", exc)
            return []

    def create_action_file(
        self, event: dict[str, Any], inbox_path: Path
    ) -> Path:
        """Write a markdown Task Item for a WhatsApp message.

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
        msg_id: str = event["message_id"]
        from_contact: str = event.get("from_contact", "unknown")
        body: str = event.get("body", "")

        # Safe filename slug from the contact identifier.
        slug = re.sub(r"[^\w]+", "-", from_contact).strip("-").lower()[:32]
        filename = f"wa-{msg_id[:8]}-{slug}.md"
        path = inbox_path / filename

        item_id: str = event.get("item_id", str(uuid.uuid4()))
        now = datetime.now(timezone.utc).isoformat()

        content = (
            "---\n"
            f"id: {item_id}\n"
            "type: message\n"
            "source: whatsapp\n"
            f"source_id: {msg_id}\n"
            "priority: medium\n"
            "status: needs_action\n"
            "requires_approval: false\n"
            "classification: local_only\n"
            f"created_at: {now}\n"
            f"updated_at: {now}\n"
            "tags: []\n"
            "---\n\n"
            f"# WhatsApp Message from {from_contact}\n\n"
            f"**From**: {from_contact}  \n"
            f"**Message ID**: `{msg_id}`  \n"
            f"**Received**: {event.get('timestamp', now)}  \n\n"
            "## Content\n\n"
            f"{body}\n\n"
            "## Next Steps\n\n"
            "- [ ] Review message\n"
            "- [ ] Draft response (if required)\n"
            "- [ ] Execute or delegate\n"
        )

        path.write_text(content, encoding="utf-8")

        # Track this ID so it is never processed again.
        self._processed_ids.add(msg_id)
        self._save_processed_ids()

        self._logger.info(
            "WhatsApp item created: %s (from: %s)", path.name, from_contact
        )
        return path

    # ── private helpers ───────────────────────────────────────────────────────

    def _fetch_messages(self, token: str) -> list[dict[str, Any]]:
        """Call the WhatsApp Business API to fetch unread messages.

        Uses ``urllib.request`` (stdlib) to avoid additional dependencies.
        Returns an empty list when ``phone_number_id`` is not configured
        (expected in dev / test environments).
        """
        if not self._phone_number_id:
            self._logger.debug(
                "phone_number_id not configured — no messages to fetch (dev mode)"
            )
            return []

        import urllib.request

        url = f"{self._api_url}/{self._phone_number_id}/messages"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            self._logger.error("WhatsApp API HTTP request failed: %s", exc)
            return []

        raw_messages = data.get("messages", data.get("data", []))
        contacts: list[str] = self._filters.get("contacts", [])
        groups: list[str] = self._filters.get("groups", [])

        events: list[dict[str, Any]] = []
        for msg in raw_messages:
            msg_id: str = msg.get("id", "")
            if not msg_id or msg_id in self._processed_ids:
                continue

            from_contact: str = msg.get("from", msg.get("wa_id", "unknown"))

            # Apply contact / group filter when configured.
            if contacts and from_contact not in contacts:
                continue
            if groups:
                chat_id = msg.get("chat_id", "")
                if not any(g in chat_id for g in groups):
                    continue

            events.append(
                {
                    "message_id": msg_id,
                    "item_id": str(uuid.uuid4()),
                    "from_contact": from_contact,
                    "body": msg.get("text", {}).get(
                        "body", msg.get("body", "")
                    ),
                    "timestamp": msg.get("timestamp", ""),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        self._logger.info(
            "WhatsApp: %d new message(s) detected", len(events)
        )
        return events

    def _load_processed_ids(self) -> set[str]:
        """Load the set of already-processed message IDs from the state file."""
        if self._state_file is None or not self._state_file.exists():
            return set()
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            ids: set[str] = set(data.get("processed_ids", []))
            self._logger.debug(
                "Loaded %d processed WhatsApp ID(s) from %s",
                len(ids),
                self._state_file,
            )
            return ids
        except (json.JSONDecodeError, OSError) as exc:
            self._logger.warning(
                "Could not load WhatsApp processed IDs from %s: %s "
                "— starting fresh",
                self._state_file,
                exc,
            )
            return set()

    def _save_processed_ids(self) -> None:
        """Persist the processed message ID set to the state file."""
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
                "Failed to persist WhatsApp processed IDs to %s: %s",
                self._state_file,
                exc,
            )


# ── standalone entry point ────────────────────────────────────────────────────


def _load_config(vault_root: Path) -> dict[str, Any]:
    """Load Config/whatsapp_watcher.yaml or return built-in defaults."""
    config_path = vault_root / "Config" / "whatsapp_watcher.yaml"
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
            "name": "whatsapp-inbox",
            "type": "whatsapp",
            "enabled": True,
            "polling_interval_seconds": 30,
            "state_file": "Config/whatsapp_processed_ids.json",
            "api_url": "https://graph.facebook.com/v18.0",
            "phone_number_id": "",
            "filters": {"contacts": [], "groups": []},
            "credential_ref": "WHATSAPP_API_TOKEN",
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
    watcher = WhatsAppWatcher(config)
    inbox_path = VAULT_ROOT / "Needs_Action"
    inbox_path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "WhatsAppWatcher | vault=%s | dry_run=%s | interval=%ds",
        VAULT_ROOT,
        DRY_RUN,
        watcher.polling_interval,
    )
    watcher.run(inbox_path, dry_run=DRY_RUN)
