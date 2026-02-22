"""Python Gmail MCP server — Silver tier (T034).

Implements the Email MCP tools from mcp-interfaces.md using the
Google Gmail API (``google-api-python-client``).

Tools
-----
send_email    — REQUIRES APPROVAL (FR-017)
search_emails — auto-approved (read-only)
get_email     — auto-approved (read-only)
mark_read     — auto-approved

All tools are wrapped in ``@with_retry(base_delay=2, max_retries=3)``.

Transport: stdio
Credential Ref: ``GMAIL_OAUTH_TOKEN_PATH`` (env var name)

Requires Silver tier dependencies::

    pip install -e ".[silver]"
"""
from __future__ import annotations

import base64
import logging
import os
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from src.engine.retry import with_retry
from src.mcp.base import BaseMCPServer

logger = logging.getLogger(__name__)


class EmailMCPServer(BaseMCPServer):
    """Python Gmail MCP server (send/search/read/mark_read).

    Parameters
    ----------
    credential_refs:
        Mapping of logical name → env var name.  Must include
        ``"token_path"`` → an UPPER_SNAKE_CASE env var that resolves
        to the OAuth2 token JSON file path at runtime.
        Defaults to ``{"token_path": "GMAIL_OAUTH_TOKEN_PATH"}``.
    dry_run:
        When True, ``send_email`` and ``mark_read`` log actions but do
        NOT call the Gmail API.  Read operations still attempt the API.
    """

    def __init__(
        self,
        credential_refs: dict[str, str] | None = None,
        *,
        dry_run: bool = False,
    ) -> None:
        refs = credential_refs or {"token_path": "GMAIL_OAUTH_TOKEN_PATH"}
        super().__init__(refs)
        self._dry_run = dry_run
        self._service: Any = None

    # ── identity ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "email-mcp"

    @property
    def version(self) -> str:
        return "1.0.0"

    # ── tools (mcp-interfaces.md contract) ────────────────────────────────────

    @with_retry(base_delay=2, max_retries=3)
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an email via Gmail API.

        FR-017: ``send_email`` REQUIRES human approval.  The caller
        (executor skill / ApprovalManager) must verify the approval has
        been granted before invoking this tool.

        Parameters
        ----------
        to:
            Recipient email address.
        subject:
            Email subject line.
        body:
            Plain-text or HTML message body.
        cc:
            Optional comma-separated CC addresses.
        bcc:
            Optional comma-separated BCC addresses.
        reply_to_message_id:
            Gmail message ID to thread this reply against.

        Returns
        -------
        dict
            ``{message_id, status, error}`` per mcp-interfaces.md.
        """
        if self._dry_run:
            logger.info(
                "[DRY_RUN] Would send email | to=%s | subject=%s", to, subject
            )
            return {
                "message_id": "dry-run-msg-id",
                "status": "sent",
                "error": None,
            }

        try:
            service = self._get_service()
            msg = MIMEText(body)
            msg["to"] = to
            msg["subject"] = subject
            if cc:
                msg["cc"] = cc
            if bcc:
                msg["bcc"] = bcc
            if reply_to_message_id:
                msg["In-Reply-To"] = reply_to_message_id
                msg["References"] = reply_to_message_id

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            result = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            message_id: str = result.get("id", "")
            logger.info("Email sent: %s → %s", message_id, to)
            return {"message_id": message_id, "status": "sent", "error": None}

        except Exception as exc:
            logger.error("send_email failed: %s", exc)
            return {"message_id": "", "status": "failed", "error": str(exc)}

    @with_retry(base_delay=2, max_retries=3)
    def search_emails(
        self,
        query: str,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Search Gmail using Gmail query syntax (read-only, auto-approved).

        Parameters
        ----------
        query:
            Gmail search string (e.g. ``"from:boss@example.com is:unread"``).
        max_results:
            Maximum number of results to return.

        Returns
        -------
        dict
            ``{emails: [{id, from, subject, date, snippet}]}``
        """
        try:
            service = self._get_service()
            result = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            messages = result.get("messages", [])
            emails: list[dict[str, Any]] = []
            for msg_ref in messages:
                try:
                    msg = (
                        service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=msg_ref["id"],
                            format="metadata",
                            metadataHeaders=["From", "Subject", "Date"],
                        )
                        .execute()
                    )
                    headers = {
                        h["name"]: h["value"]
                        for h in msg.get("payload", {}).get("headers", [])
                    }
                    emails.append(
                        {
                            "id": msg_ref["id"],
                            "from": headers.get("From", ""),
                            "subject": headers.get("Subject", ""),
                            "date": headers.get("Date", ""),
                            "snippet": msg.get("snippet", ""),
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        "Could not fetch message %s: %s", msg_ref["id"], exc
                    )
            return {"emails": emails}

        except Exception as exc:
            logger.error("search_emails failed: %s", exc)
            return {"emails": []}

    @with_retry(base_delay=2, max_retries=3)
    def get_email(self, message_id: str) -> dict[str, Any]:
        """Fetch full email content by Gmail message ID (read-only).

        Returns
        -------
        dict
            ``{from, to, subject, body, date, attachments}``
        """
        try:
            service = self._get_service()
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            return {
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "body": _extract_body(msg),
                "date": headers.get("Date", ""),
                "attachments": _extract_attachments(msg),
            }

        except Exception as exc:
            logger.error("get_email(%s) failed: %s", message_id, exc)
            return {
                "from": "",
                "to": "",
                "subject": "",
                "body": "",
                "date": "",
                "attachments": [],
            }

    @with_retry(base_delay=2, max_retries=3)
    def mark_read(self, message_id: str) -> dict[str, Any]:
        """Remove the UNREAD label from a Gmail message.

        Returns
        -------
        dict
            ``{status: "ok" | "failed"}``
        """
        if self._dry_run:
            logger.info("[DRY_RUN] Would mark as read: %s", message_id)
            return {"status": "ok"}

        try:
            service = self._get_service()
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            logger.info("Marked as read: %s", message_id)
            return {"status": "ok"}

        except Exception as exc:
            logger.error("mark_read(%s) failed: %s", message_id, exc)
            return {"status": "failed"}

    # ── private helpers ───────────────────────────────────────────────────────

    def _get_service(self) -> Any:
        """Lazily build and cache the Gmail API service.

        Raises
        ------
        ImportError
            If Silver tier dependencies are not installed.
        FileNotFoundError
            If the OAuth2 token file does not exist.
        """
        if self._service is not None:
            return self._service

        try:
            from google.oauth2.credentials import Credentials  # type: ignore[import]
            from googleapiclient.discovery import build  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "EmailMCPServer requires Silver tier dependencies: "
                "pip install -e '.[silver]'"
            ) from exc

        token_path_str = self._resolve_credential("token_path")
        token_path = Path(token_path_str)
        if not token_path.exists():
            raise FileNotFoundError(
                f"Gmail OAuth2 token not found: {token_path}. "
                "Run 'python -m src.scripts.gmail_auth' to generate credentials."
            )

        creds = Credentials.from_authorized_user_file(str(token_path))
        self._service = build("gmail", "v1", credentials=creds)
        logger.info("EmailMCPServer: Gmail API service initialised")
        return self._service


# ── module-level helpers ──────────────────────────────────────────────────────


def _extract_body(msg: dict[str, Any]) -> str:
    """Extract plain-text body from a Gmail API message."""
    payload = msg.get("payload", {})
    raw = payload.get("body", {}).get("data", "")
    if raw:
        return _decode_b64(raw)
    return _find_text_plain(payload.get("parts", []))


def _find_text_plain(parts: list[dict[str, Any]]) -> str:
    for part in parts:
        if part.get("mimeType") == "text/plain":
            raw = part.get("body", {}).get("data", "")
            if raw:
                return _decode_b64(raw)
        sub = part.get("parts", [])
        if sub:
            result = _find_text_plain(sub)
            if result:
                return result
    return ""


def _extract_attachments(msg: dict[str, Any]) -> list[dict[str, Any]]:
    """Return attachment metadata from a Gmail API message."""
    attachments: list[dict[str, Any]] = []
    for part in msg.get("payload", {}).get("parts", []):
        filename = part.get("filename", "")
        if filename:
            attachments.append(
                {
                    "name": filename,
                    "mime_type": part.get("mimeType", ""),
                    "size": part.get("body", {}).get("size", 0),
                }
            )
    return attachments


def _decode_b64(data: str) -> str:
    """Decode Gmail URL-safe base64-encoded body data."""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""
