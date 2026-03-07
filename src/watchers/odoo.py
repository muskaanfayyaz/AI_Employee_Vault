"""Odoo watcher — polls Odoo JSON-RPC for new/changed records (FR-G007/FR-G008).

Monitors:
    - New/updated invoices   (account.move)
    - New sales orders       (sale.order)
    - New contacts           (res.partner, optional)

Persistence:
    Stores the last successful poll timestamp in
    ``Config/odoo_last_poll.json`` so polls resume correctly after restart
    (FR-G008).

Security:
    Credentials are read exclusively from environment variables
    (ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY) — never from vault
    files or logs (FR-G040).

DRY_RUN:
    Detected records are logged; no vault items are created and the state
    file is NOT updated.

Config schema (``Config/odoo_watcher.yaml``)::

    watcher:
      name: "odoo-poller"
      type: "odoo"
      enabled: false
      polling_interval_seconds: 60
      state_file: "Config/odoo_last_poll.json"
      page_size: 50
      watch_invoices: true
      watch_sales_orders: true
      watch_contacts: false
      credential_refs:
        url: "ODOO_URL"
        db: "ODOO_DB"
        username: "ODOO_USERNAME"
        api_key: "ODOO_API_KEY"
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.watchers.base import BaseWatcher

logger = logging.getLogger(__name__)

# Default fields per model for vault item summaries.
_INVOICE_FIELDS = [
    "id", "name", "move_type", "state", "partner_id",
    "invoice_date", "amount_total", "currency_id", "ref",
]
_ORDER_FIELDS = [
    "id", "name", "state", "partner_id",
    "date_order", "amount_total", "currency_id",
]
_CONTACT_FIELDS = [
    "id", "name", "email", "phone", "company_name", "create_date",
]
_TASK_FIELDS = [
    "id", "name", "project_id", "stage_id", "date_deadline", "write_date",
]


class OdooWatcher(BaseWatcher):
    """Polls Odoo JSON-RPC for new invoice, sales-order, and contact records.

    Parameters
    ----------
    config:
        Config dict matching the Watcher Configuration schema
        (see module docstring).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        watcher_cfg = config.get("watcher", config)

        cred_refs = watcher_cfg.get("credential_refs", {})
        self._url_ref: str = cred_refs.get("url", "ODOO_URL")
        self._db_ref: str = cred_refs.get("db", "ODOO_DB")
        self._username_ref: str = cred_refs.get("username", "ODOO_USERNAME")
        self._api_key_ref: str = cred_refs.get("api_key", "ODOO_API_KEY")

        self._watch_invoices: bool = watcher_cfg.get("watch_invoices", True)
        self._watch_orders: bool = watcher_cfg.get("watch_sales_orders", True)
        self._watch_contacts: bool = watcher_cfg.get("watch_contacts", False)
        self._watch_tasks: bool = watcher_cfg.get("watch_tasks", False)
        self._page_size: int = int(watcher_cfg.get("page_size", 50))
        self._state_file_rel: str = watcher_cfg.get(
            "state_file", "Config/odoo_last_poll.json"
        )

        # Runtime state.
        self._state_file: Path | None = None
        self._last_poll: str = "2000-01-01 00:00:00"  # safe sentinel
        self._uid: int | None = None
        self._request_id = 0

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def run(self, inbox_path: Path, *, dry_run: bool = False) -> None:
        """Initialise state file path before the poll loop."""
        vault_root = inbox_path.parent
        self._state_file = vault_root / self._state_file_rel
        self._last_poll = self._load_last_poll()
        self._logger.info(
            "OdooWatcher starting | state_file=%s | last_poll=%s | dry_run=%s",
            self._state_file,
            self._last_poll,
            dry_run,
        )
        super().run(inbox_path, dry_run=dry_run)

    def health_check(self) -> bool:
        """True when enabled and all 4 credential env vars are set."""
        if not self._enabled:
            return False
        return all(
            os.getenv(ref, "")
            for ref in (self._url_ref, self._db_ref, self._username_ref, self._api_key_ref)
        )

    # ── abstract implementations ──────────────────────────────────────────────

    def check_for_updates(self) -> list[dict[str, Any]]:
        """Poll Odoo for new records since last_poll.

        Returns a list of event dicts; empty list on error.
        """
        url = os.getenv(self._url_ref, "")
        db = os.getenv(self._db_ref, "")
        username = os.getenv(self._username_ref, "")
        api_key = os.getenv(self._api_key_ref, "")

        if not all([url, db, username, api_key]):
            self._logger.warning(
                "OdooWatcher: credentials not fully set — skipping poll"
            )
            return []

        try:
            uid = self._authenticate(url, db, username, api_key)
        except Exception as exc:
            self._logger.error("OdooWatcher: authentication failed: %s", exc)
            return []

        events: list[dict[str, Any]] = []

        if self._watch_invoices:
            try:
                events.extend(self._fetch_invoices(url, db, uid, api_key))
            except Exception as exc:
                self._logger.error("OdooWatcher: invoice poll failed: %s", exc)

        if self._watch_orders:
            try:
                events.extend(self._fetch_orders(url, db, uid, api_key))
            except Exception as exc:
                self._logger.error("OdooWatcher: sales order poll failed: %s", exc)

        if self._watch_contacts:
            try:
                events.extend(self._fetch_contacts(url, db, uid, api_key))
            except Exception as exc:
                self._logger.error("OdooWatcher: contacts poll failed: %s", exc)

        if self._watch_tasks:
            try:
                events.extend(self._fetch_tasks(url, db, uid, api_key))
            except Exception as exc:
                self._logger.error("OdooWatcher: tasks poll failed: %s", exc)

        # Update last_poll timestamp to now (only when not dry-run — caller handles).
        self._last_poll = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._logger.info("OdooWatcher: %d new event(s) detected", len(events))
        return events

    def create_action_file(
        self, event: dict[str, Any], inbox_path: Path
    ) -> Path:
        """Write a markdown vault item for an Odoo record event."""
        odoo_model: str = event.get("odoo_model", "odoo.record")
        odoo_id: int = event.get("odoo_id", 0)
        event_type: str = event.get("event_type", "new_record")
        summary_fields: dict = event.get("summary_fields", {})
        detected_at: str = event.get("detected_at", datetime.now(timezone.utc).isoformat())

        item_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        slug = odoo_model.replace(".", "-")
        filename = f"odoo-{slug}-{odoo_id}-{item_id[:8]}.md"
        path = inbox_path / filename

        # Build human-readable summary from summary_fields.
        summary_lines = ""
        for k, v in summary_fields.items():
            if v is not None and v is not False:
                summary_lines += f"- **{k}**: {v}\n"

        model_display = odoo_model.replace(".", " ").title()
        content = (
            "---\n"
            f"id: {item_id}\n"
            "type: erp\n"
            "source: odoo\n"
            f"odoo_model: {odoo_model}\n"
            f"odoo_id: {odoo_id}\n"
            "priority: medium\n"
            "status: needs_action\n"
            "requires_approval: false\n"
            "classification: local_only\n"
            f"created_at: {now}\n"
            f"updated_at: {now}\n"
            f"tags: [odoo, {slug}, {event_type}]\n"
            "---\n\n"
            f"# Odoo {model_display} Record #{odoo_id}\n\n"
            f"**Model**: `{odoo_model}`  \n"
            f"**Odoo ID**: {odoo_id}  \n"
            f"**Event Type**: {event_type}  \n"
            f"**Detected**: {detected_at}  \n\n"
            "## Summary\n\n"
            f"{summary_lines or '_No summary fields available._'}\n\n"
            "## Next Steps\n\n"
            "- [ ] Review record in Odoo\n"
            "- [ ] Determine required action\n"
            "- [ ] Execute or delegate (all Odoo writes require approval)\n"
        )

        path.write_text(content, encoding="utf-8")

        # Persist the updated last_poll timestamp.
        self._save_last_poll(self._last_poll)

        self._logger.info(
            "Odoo vault item created: %s (model=%s id=%d)",
            path.name,
            odoo_model,
            odoo_id,
        )
        return path

    # ── private: JSON-RPC helpers ─────────────────────────────────────────────

    def _authenticate(self, url: str, db: str, username: str, api_key: str) -> int:
        """Authenticate with Odoo common/authenticate, return uid."""
        result = self._jsonrpc(
            url, "common", "authenticate", [db, username, api_key, {}]
        )
        if not isinstance(result, int) or result == 0:
            raise RuntimeError(
                f"Odoo authentication returned unexpected uid: {result!r}"
            )
        return result

    def _search_read(
        self,
        url: str,
        db: str,
        uid: int,
        api_key: str,
        model: str,
        domain: list,
        fields: list[str],
        *,
        limit: int = 50,
        offset: int = 0,
        order: str = "",
    ) -> list[dict]:
        """Execute an object/execute_kw search_read, paginating as needed (FR-G007)."""
        kwargs: dict[str, Any] = {"fields": fields, "limit": limit, "offset": offset}
        if order:
            kwargs["order"] = order

        result = self._jsonrpc(
            url, "object", "execute_kw",
            [db, uid, api_key, model, "search_read", [domain], kwargs],
        )
        return result if isinstance(result, list) else []

    def _jsonrpc(
        self,
        url: str,
        service: str,
        method: str,
        args: list,
    ) -> Any:
        """Make a single Odoo JSON-RPC call via stdlib urllib."""
        self._request_id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "call",
            "id": self._request_id,
            "params": {"service": service, "method": method, "args": args},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{url.rstrip('/')}/jsonrpc",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if "error" in data:
            msg = (
                data["error"].get("data", {}).get("message")
                or data["error"].get("message")
                or "Unknown Odoo error"
            )
            raise RuntimeError(f"Odoo JSON-RPC error: {msg}")
        return data.get("result")

    # ── private: per-model poll helpers ──────────────────────────────────────

    def _fetch_invoices(
        self, url: str, db: str, uid: int, api_key: str
    ) -> list[dict[str, Any]]:
        """Fetch invoices/bills written since last_poll (paginated)."""
        domain = [
            ["move_type", "in", ["out_invoice", "in_invoice", "out_refund", "in_refund"]],
            ["write_date", ">=", self._last_poll],
        ]
        records = self._paginated_read(url, db, uid, api_key, "account.move", domain, _INVOICE_FIELDS)
        events = []
        for rec in records:
            events.append({
                "event_id": f"invoice-{rec['id']}",
                "odoo_model": "account.move",
                "odoo_id": rec["id"],
                "event_type": "invoice_detected",
                "summary_fields": {
                    "Name": rec.get("name"),
                    "Type": rec.get("move_type"),
                    "State": rec.get("state"),
                    "Partner": _extract_name(rec.get("partner_id")),
                    "Date": rec.get("invoice_date"),
                    "Total": rec.get("amount_total"),
                    "Currency": _extract_name(rec.get("currency_id")),
                    "Reference": rec.get("ref"),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
            })
        return events

    def _fetch_orders(
        self, url: str, db: str, uid: int, api_key: str
    ) -> list[dict[str, Any]]:
        """Fetch sales orders written since last_poll (paginated)."""
        domain = [["write_date", ">=", self._last_poll]]
        records = self._paginated_read(url, db, uid, api_key, "sale.order", domain, _ORDER_FIELDS)
        events = []
        for rec in records:
            events.append({
                "event_id": f"sale-order-{rec['id']}",
                "odoo_model": "sale.order",
                "odoo_id": rec["id"],
                "event_type": "sales_order_detected",
                "summary_fields": {
                    "Name": rec.get("name"),
                    "State": rec.get("state"),
                    "Customer": _extract_name(rec.get("partner_id")),
                    "Date": rec.get("date_order"),
                    "Total": rec.get("amount_total"),
                    "Currency": _extract_name(rec.get("currency_id")),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
            })
        return events

    def _fetch_contacts(
        self, url: str, db: str, uid: int, api_key: str
    ) -> list[dict[str, Any]]:
        """Fetch new contacts created since last_poll (paginated)."""
        domain = [["create_date", ">=", self._last_poll], ["customer_rank", ">", 0]]
        records = self._paginated_read(url, db, uid, api_key, "res.partner", domain, _CONTACT_FIELDS)
        events = []
        for rec in records:
            events.append({
                "event_id": f"contact-{rec['id']}",
                "odoo_model": "res.partner",
                "odoo_id": rec["id"],
                "event_type": "new_contact",
                "summary_fields": {
                    "Name": rec.get("name"),
                    "Email": rec.get("email"),
                    "Phone": rec.get("phone"),
                    "Company": rec.get("company_name"),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
            })
        return events

    def _fetch_tasks(
        self, url: str, db: str, uid: int, api_key: str
    ) -> list[dict[str, Any]]:
        """Fetch project tasks updated since last_poll (paginated)."""
        domain = [["write_date", ">=", self._last_poll]]
        records = self._paginated_read(url, db, uid, api_key, "project.task", domain, _TASK_FIELDS)
        events = []
        for rec in records:
            events.append({
                "event_id": f"task-{rec['id']}",
                "odoo_model": "project.task",
                "odoo_id": rec["id"],
                "event_type": "project_task",
                "summary_fields": {
                    "Task": rec.get("name"),
                    "Project": _extract_name(rec.get("project_id")),
                    "Stage": _extract_name(rec.get("stage_id")),
                    "Deadline": rec.get("date_deadline"),
                },
                "detected_at": datetime.now(timezone.utc).isoformat(),
            })
        return events

    def _paginated_read(
        self,
        url: str,
        db: str,
        uid: int,
        api_key: str,
        model: str,
        domain: list,
        fields: list[str],
    ) -> list[dict]:
        """Read all records matching *domain* using page_size pagination (FR-G007)."""
        results: list[dict] = []
        offset = 0
        while True:
            page = self._search_read(
                url, db, uid, api_key, model, domain, fields,
                limit=self._page_size, offset=offset, order="write_date asc",
            )
            results.extend(page)
            if len(page) < self._page_size:
                break
            offset += self._page_size
        return results

    # ── private: state file helpers ──────────────────────────────────────────

    def _load_last_poll(self) -> str:
        """Load last_poll from state file; return sentinel if missing."""
        if self._state_file is None or not self._state_file.exists():
            return "2000-01-01 00:00:00"
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            ts = data.get("last_poll", "2000-01-01 00:00:00")
            self._logger.debug("OdooWatcher: loaded last_poll=%s", ts)
            return ts
        except (json.JSONDecodeError, OSError) as exc:
            self._logger.warning(
                "OdooWatcher: could not load state file %s: %s — starting from beginning",
                self._state_file, exc,
            )
            return "2000-01-01 00:00:00"

    def _save_last_poll(self, timestamp: str) -> None:
        """Persist last_poll to state file (FR-G008)."""
        if self._state_file is None:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "last_poll": timestamp,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._state_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            self._logger.error(
                "OdooWatcher: failed to save state file %s: %s",
                self._state_file, exc,
            )


# ── module helpers ────────────────────────────────────────────────────────────


def _extract_name(field_value: Any) -> str | None:
    """Extract name from Odoo many2one field value (list or False)."""
    if isinstance(field_value, (list, tuple)) and len(field_value) >= 2:
        return str(field_value[1])
    if isinstance(field_value, str):
        return field_value
    return None
