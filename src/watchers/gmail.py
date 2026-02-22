"""Gmail inbox watcher — Silver tier (T035).

Polls Gmail for **unread + important** emails matching configured filters.
Creates a markdown Task Item (``.md``) in the vault's ``Needs_Action/``
folder for each new message. Tracks processed message IDs in a JSON
state file so no email is processed twice.

Requires Silver tier dependencies::

    pip install -e ".[silver]"

And a Gmail OAuth2 token file::

    GMAIL_OAUTH_TOKEN_PATH=/path/to/token.json   # in .env

Run standalone::

    python -m src.watchers.gmail

DRY_RUN semantics (inherited from BaseWatcher):
    Events are detected and logged; ``create_action_file()`` is NOT
    called; no IDs are marked as processed.
"""
from __future__ import annotations

import base64
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


# ---------------------------------------------------------------------------
# GmailWatcher
# ---------------------------------------------------------------------------


class GmailWatcher(BaseWatcher):
    """Polls Gmail inbox for unread important emails.

    Constructor accepts a config dict matching the Watcher Configuration
    schema::

        watcher:
          name: "gmail-inbox"
          type: "gmail"
          enabled: true
          polling_interval_seconds: 60
          max_results: 50
          state_file: "Config/gmail_processed_ids.json"
          filters:
            keywords: ["invoice", "urgent"]
            senders: ["boss@example.com"]
            labels: ["STARRED"]
          credential_ref: GMAIL_OAUTH_TOKEN_PATH   # env var name only

    The ``state_file`` path is relative to the vault root (derived from
    ``inbox_path.parent`` when ``run()`` is called).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        watcher_cfg = config.get("watcher", config)

        # Credential reference — env var name, NEVER the raw token value.
        self._credential_ref: str = watcher_cfg.get(
            "credential_ref", "GMAIL_OAUTH_TOKEN_PATH"
        )

        # Filters applied server-side via Gmail search query.
        self._filters: dict[str, Any] = watcher_cfg.get("filters", {})
        self._max_results: int = int(watcher_cfg.get("max_results", 50))

        # State file for deduplication (relative to vault root).
        self._state_file_rel: str = watcher_cfg.get(
            "state_file", "Config/gmail_processed_ids.json"
        )
        self._state_file: Path | None = None
        self._processed_ids: set[str] = set()

        # Gmail API service — lazily initialized in _get_service().
        self._service: Any = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    def run(self, inbox_path: Path, *, dry_run: bool = False) -> None:
        """Override to initialise state file path before the poll loop."""
        vault_root = inbox_path.parent
        self._state_file = vault_root / self._state_file_rel
        self._processed_ids = self._load_processed_ids()
        self._logger.info(
            "GmailWatcher starting | state_file=%s | known_ids=%d | dry_run=%s",
            self._state_file,
            len(self._processed_ids),
            dry_run,
        )
        super().run(inbox_path, dry_run=dry_run)

    def health_check(self) -> bool:
        """Return True when enabled and the token file exists on disk."""
        if not self._enabled:
            return False
        token_path_str = os.getenv(self._credential_ref, "")
        if not token_path_str:
            return False
        return Path(token_path_str).exists()

    # ── abstract implementations ───────────────────────────────────────────

    def check_for_updates(self) -> list[dict[str, Any]]:
        """Poll Gmail for unread important emails matching filters.

        Returns a list of event dicts (one per new message).  Returns an
        empty list when credentials are unavailable or the API fails —
        the watcher loop will retry on the next interval.
        """
        try:
            service = self._get_service()
        except Exception as exc:
            self._logger.warning(
                "Gmail service unavailable — skipping poll: %s", exc
            )
            return []

        query = self._build_query()
        self._logger.debug("Gmail query: %s", query)

        try:
            result = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=self._max_results)
                .execute()
            )
        except Exception as exc:
            self._logger.error("Gmail API list() error: %s", exc)
            return []

        raw_messages = result.get("messages", [])
        if not raw_messages:
            self._logger.debug("Gmail: inbox empty for query")
            return []

        events: list[dict[str, Any]] = []
        new_count = 0
        for msg_ref in raw_messages:
            msg_id = msg_ref["id"]
            if msg_id in self._processed_ids:
                continue
            new_count += 1
            try:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )
                events.append(self._parse_message(msg))
            except Exception as exc:
                self._logger.error(
                    "Failed to fetch message %s: %s", msg_id, exc
                )

        self._logger.info(
            "Gmail: %d new message(s) out of %d total",
            len(events),
            len(raw_messages),
        )
        return events

    def create_action_file(
        self, event: dict[str, Any], inbox_path: Path
    ) -> Path:
        """Write a markdown Task Item for the email and track its ID.

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
        subject: str = event.get("subject", "no-subject")

        # Safe filename slug from subject.
        slug = re.sub(r"[^\w]+", "-", subject).strip("-").lower()[:48]
        filename = f"email-{msg_id[:8]}-{slug}.md"
        path = inbox_path / filename

        item_id: str = event.get("item_id", str(uuid.uuid4()))
        now = datetime.now(timezone.utc).isoformat()
        from_addr: str = event.get("from_addr", "unknown")
        date_str: str = event.get("date", "")
        body: str = event.get("body") or event.get("snippet", "")

        content = (
            "---\n"
            f"id: {item_id}\n"
            "type: email\n"
            "source: gmail\n"
            f"source_id: {msg_id}\n"
            "priority: medium\n"
            "status: needs_action\n"
            "requires_approval: false\n"
            "classification: local_only\n"
            f"created_at: {now}\n"
            f"updated_at: {now}\n"
            "tags: []\n"
            "---\n\n"
            f"# Email: {subject}\n\n"
            f"**From**: {from_addr}  \n"
            f"**Subject**: {subject}  \n"
            f"**Date**: {date_str}  \n"
            f"**Gmail ID**: `{msg_id}`  \n\n"
            "## Content\n\n"
            f"{body}\n\n"
            "## Next Steps\n\n"
            "- [ ] Review email content\n"
            "- [ ] Draft response (if required)\n"
            "- [ ] Execute or delegate\n"
        )

        path.write_text(content, encoding="utf-8")

        # Track this ID so it's never processed again.
        self._processed_ids.add(msg_id)
        self._save_processed_ids()

        self._logger.info(
            "Email item created: %s (from: %s)", path.name, from_addr
        )
        return path

    # ── private helpers ────────────────────────────────────────────────────

    def _build_query(self) -> str:
        """Build a Gmail search query string from the watcher filters."""
        parts: list[str] = ["is:unread", "is:important"]

        keywords: list[str] = self._filters.get("keywords", [])
        senders: list[str] = self._filters.get("senders", [])
        labels: list[str] = self._filters.get("labels", [])

        if keywords:
            parts.append("(" + " OR ".join(keywords) + ")")
        if senders:
            parts.append("from:(" + " OR ".join(senders) + ")")
        for label in labels:
            parts.append(f"label:{label}")

        return " ".join(parts)

    def _get_service(self) -> Any:
        """Lazily build and cache the Gmail API service.

        Raises
        ------
        ImportError
            If Silver tier dependencies are not installed.
        ValueError
            If the credential env var is not set.
        FileNotFoundError
            If the token file does not exist on disk.
        """
        if self._service is not None:
            return self._service

        try:
            from google.oauth2.credentials import Credentials  # type: ignore[import]
            from googleapiclient.discovery import build  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "Gmail watcher requires Silver tier dependencies: "
                "pip install -e '.[silver]'"
            ) from exc

        token_path_str = os.getenv(self._credential_ref, "")
        if not token_path_str:
            raise ValueError(
                f"Gmail credential not configured. "
                f"Set {self._credential_ref} to your token.json path in .env"
            )

        token_path = Path(token_path_str)
        if not token_path.exists():
            raise FileNotFoundError(
                f"Gmail token file not found: {token_path}. "
                "Run 'python -m src.scripts.gmail_auth' to generate credentials."
            )

        creds = Credentials.from_authorized_user_file(str(token_path))
        self._service = build("gmail", "v1", credentials=creds)
        self._logger.info("Gmail API service initialised")
        return self._service

    def _parse_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Convert a Gmail API message object into a watcher event dict."""
        msg_id: str = msg["id"]
        headers: dict[str, str] = {
            h["name"]: h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        return {
            "message_id": msg_id,
            "item_id": str(uuid.uuid4()),
            "source": f"gmail:{msg_id}",
            "from_addr": headers.get("From", "unknown"),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "body": self._extract_body(msg),
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_body(self, msg: dict[str, Any]) -> str:
        """Extract the plain-text body from a Gmail API message payload."""
        payload = msg.get("payload", {})
        # Simple (non-multipart) message.
        raw = payload.get("body", {}).get("data", "")
        if raw:
            return _decode_b64(raw)
        # Multipart — recurse through parts.
        return _find_text_plain(payload.get("parts", []))

    def _load_processed_ids(self) -> set[str]:
        """Load the set of already-processed message IDs from disk."""
        if self._state_file is None or not self._state_file.exists():
            return set()
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            ids: set[str] = set(data.get("processed_ids", []))
            self._logger.debug(
                "Loaded %d processed Gmail ID(s) from %s",
                len(ids),
                self._state_file,
            )
            return ids
        except (json.JSONDecodeError, OSError) as exc:
            self._logger.warning(
                "Could not load processed IDs from %s: %s — starting fresh",
                self._state_file,
                exc,
            )
            return set()

    def _save_processed_ids(self) -> None:
        """Persist the processed ID set to the state file."""
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
                "Failed to persist processed IDs to %s: %s",
                self._state_file,
                exc,
            )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _decode_b64(data: str) -> str:
    """Decode Gmail URL-safe base64-encoded body data."""
    # Gmail omits padding — restore it.
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _find_text_plain(parts: list[dict[str, Any]]) -> str:
    """Recursively search multipart payload parts for a text/plain body."""
    for part in parts:
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            raw = part.get("body", {}).get("data", "")
            if raw:
                return _decode_b64(raw)
        # Recurse into nested multipart sections.
        sub = part.get("parts", [])
        if sub:
            result = _find_text_plain(sub)
            if result:
                return result
    return ""


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def _load_config(vault_root: Path) -> dict[str, Any]:
    """Load Config/gmail_watcher.yaml or return built-in defaults."""
    config_path = vault_root / "Config" / "gmail_watcher.yaml"
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
            "name": "gmail-inbox",
            "type": "gmail",
            "enabled": True,
            "polling_interval_seconds": 60,
            "max_results": 50,
            "state_file": "Config/gmail_processed_ids.json",
            "filters": {"keywords": [], "senders": [], "labels": []},
            "credential_ref": "GMAIL_OAUTH_TOKEN_PATH",
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
    watcher = GmailWatcher(config)
    inbox_path = VAULT_ROOT / "Needs_Action"
    inbox_path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "GmailWatcher | vault=%s | dry_run=%s | interval=%ds",
        VAULT_ROOT,
        DRY_RUN,
        watcher.polling_interval,
    )
    watcher.run(inbox_path, dry_run=DRY_RUN)
