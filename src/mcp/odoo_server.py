"""Odoo MCP server — Gold tier (FR-G009, FR-G010, FR-G011).

Implements draft-only Odoo write actions through the standard
``BaseMCPServer`` pattern.  All write actions create *draft* records
and require human approval before being posted/confirmed.

Tools
-----
create_draft_invoice    — create a draft customer invoice (account.move, state=draft)
get_invoice             — read a single invoice by Odoo ID (read-only)
list_invoices           — search/filter invoices (read-only)
create_draft_quote      — create a draft quotation (sale.order, state=draft)
get_sale_order          — read a single sale order by Odoo ID (read-only)
get_partner             — read a single partner/contact by Odoo ID (read-only)

Constitution rules enforced
----------------------------
- No auto-posting: all write methods produce ``state=draft`` records only.
- No credential storage: credentials read exclusively from env vars at call time.
- Human-in-the-loop: writes return the Odoo draft ID for review; the caller
  must surface this to the user and route approval through Pending_Approval/.
- Retry-safe: all operations are idempotent reads or draft creates (safe to retry).

Credential refs (env var names):
    ODOO_URL         — base URL, e.g. https://mycompany.odoo.com
    ODOO_DB          — database name
    ODOO_USERNAME    — login username / email
    ODOO_API_KEY     — API key (Odoo ≥ 14: Settings → Technical → API Keys)

Transport: in-process (called directly from skills/approval runner).

Requires Gold tier dependencies::

    pip install -e ".[gold]"
    # no extra packages needed — uses stdlib urllib only
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from src.engine.retry import with_retry
from src.mcp.base import BaseMCPServer

logger = logging.getLogger(__name__)

# Default credential env-var names.
_URL_ENV = "ODOO_URL"
_DB_ENV = "ODOO_DB"
_USER_ENV = "ODOO_USERNAME"
_KEY_ENV = "ODOO_API_KEY"


class OdooMCPServer(BaseMCPServer):
    """Draft-only Odoo MCP server (create/read invoices, quotes, partners).

    Parameters
    ----------
    credential_refs:
        Mapping of logical name → env var name.  Recognised keys:
        ``"url"``, ``"db"``, ``"username"``, ``"api_key"``.
        Defaults to the standard ``ODOO_*`` env var names.
    dry_run:
        When True, write methods log actions but do NOT call the Odoo API.
        Read operations still attempt the API.
    """

    def __init__(
        self,
        credential_refs: dict[str, str] | None = None,
        *,
        dry_run: bool = False,
    ) -> None:
        cred_refs = credential_refs or {}
        super().__init__(
            name="odoo-mcp",
            credential_refs={
                "url": cred_refs.get("url", _URL_ENV),
                "db": cred_refs.get("db", _DB_ENV),
                "username": cred_refs.get("username", _USER_ENV),
                "api_key": cred_refs.get("api_key", _KEY_ENV),
            },
            dry_run=dry_run,
        )
        self._request_id = 0

    # ── health ────────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """True when all 4 credential env vars are set and Odoo is reachable."""
        creds = self._resolve_creds()
        if not all(creds.values()):
            return False
        try:
            uid = self._authenticate(**creds)
            return isinstance(uid, int) and uid > 0
        except Exception:
            return False

    # ── public tools (reads) ──────────────────────────────────────────────────

    @with_retry(base_delay=2, max_retries=3)
    def get_invoice(self, odoo_id: int) -> dict[str, Any]:
        """Read a single invoice by Odoo ID.  Returns a field dict."""
        creds = self._resolve_creds()
        uid = self._authenticate(**creds)
        records = self._search_read(
            **creds, uid=uid,
            model="account.move",
            domain=[["id", "=", odoo_id]],
            fields=[
                "id", "name", "move_type", "state", "partner_id",
                "invoice_date", "invoice_date_due", "amount_total",
                "amount_residual", "currency_id", "ref", "narration",
            ],
        )
        if not records:
            raise ValueError(f"Invoice Odoo ID {odoo_id} not found")
        return records[0]

    @with_retry(base_delay=2, max_retries=3)
    def list_invoices(
        self,
        *,
        move_type: str = "out_invoice",
        state: str | None = None,
        partner_id: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search invoices with optional filters.  Returns list of field dicts.

        Parameters
        ----------
        move_type:
            ``"out_invoice"`` (customer invoice), ``"in_invoice"`` (vendor bill),
            ``"out_refund"``, ``"in_refund"``.  Default: ``"out_invoice"``.
        state:
            ``"draft"``, ``"posted"``, ``"cancel"``.  Omit to return all.
        partner_id:
            Filter by Odoo partner ID.
        limit:
            Maximum records to return (default 20, max 100).
        """
        creds = self._resolve_creds()
        uid = self._authenticate(**creds)
        domain: list = [["move_type", "=", move_type]]
        if state:
            domain.append(["state", "=", state])
        if partner_id:
            domain.append(["partner_id", "=", partner_id])
        return self._search_read(
            **creds, uid=uid,
            model="account.move",
            domain=domain,
            fields=["id", "name", "move_type", "state", "partner_id",
                    "invoice_date", "amount_total", "currency_id"],
            limit=min(int(limit), 100),
        )

    @with_retry(base_delay=2, max_retries=3)
    def get_sale_order(self, odoo_id: int) -> dict[str, Any]:
        """Read a single sale order by Odoo ID."""
        creds = self._resolve_creds()
        uid = self._authenticate(**creds)
        records = self._search_read(
            **creds, uid=uid,
            model="sale.order",
            domain=[["id", "=", odoo_id]],
            fields=[
                "id", "name", "state", "partner_id",
                "date_order", "validity_date", "amount_total",
                "currency_id", "note",
            ],
        )
        if not records:
            raise ValueError(f"Sale order Odoo ID {odoo_id} not found")
        return records[0]

    @with_retry(base_delay=2, max_retries=3)
    def get_partner(self, odoo_id: int) -> dict[str, Any]:
        """Read a single partner (customer/vendor) by Odoo ID."""
        creds = self._resolve_creds()
        uid = self._authenticate(**creds)
        records = self._search_read(
            **creds, uid=uid,
            model="res.partner",
            domain=[["id", "=", odoo_id]],
            fields=[
                "id", "name", "email", "phone", "mobile",
                "street", "city", "country_id", "company_name",
                "customer_rank", "supplier_rank",
            ],
        )
        if not records:
            raise ValueError(f"Partner Odoo ID {odoo_id} not found")
        return records[0]

    # ── public tools (draft writes — require approval) ────────────────────────

    @with_retry(base_delay=2, max_retries=3)
    def create_draft_invoice(
        self,
        *,
        partner_id: int,
        move_type: str = "out_invoice",
        invoice_date: str | None = None,
        invoice_date_due: str | None = None,
        ref: str | None = None,
        narration: str | None = None,
        lines: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a DRAFT customer invoice (or vendor bill) in Odoo.

        The record is created with ``state=draft`` and is NOT posted.
        Returns ``{"odoo_id": int, "name": str, "state": "draft"}`` so the
        caller can surface it for human review and approval.

        Parameters
        ----------
        partner_id:
            Odoo res.partner ID of the customer/vendor.
        move_type:
            ``"out_invoice"`` (customer invoice) or ``"in_invoice"`` (vendor bill).
        invoice_date:
            ISO date string ``"YYYY-MM-DD"``.  Odoo defaults to today if omitted.
        invoice_date_due:
            Payment due date ``"YYYY-MM-DD"``.
        ref:
            External reference / PO number.
        narration:
            Internal note / footer text.
        lines:
            List of line dicts.  Each line should contain:
            ``{"product_id": int, "quantity": float, "price_unit": float,
               "name": str}``.
            If omitted, the draft is created with no lines (lines can be added
            manually in Odoo before posting).
        """
        if dry_run := self._dry_run:
            logger.info(
                "DRY_RUN: would create draft %s for partner_id=%s", move_type, partner_id
            )
            return {"odoo_id": 0, "name": "DRY_RUN", "state": "draft", "dry_run": True}

        creds = self._resolve_creds()
        uid = self._authenticate(**creds)

        vals: dict[str, Any] = {
            "move_type": move_type,
            "partner_id": partner_id,
        }
        if invoice_date:
            vals["invoice_date"] = invoice_date
        if invoice_date_due:
            vals["invoice_date_due"] = invoice_date_due
        if ref:
            vals["ref"] = ref
        if narration:
            vals["narration"] = narration

        if lines:
            vals["invoice_line_ids"] = [
                (0, 0, {
                    "product_id": ln.get("product_id"),
                    "quantity": ln.get("quantity", 1),
                    "price_unit": ln.get("price_unit", 0),
                    "name": ln.get("name", ""),
                })
                for ln in lines
            ]

        new_id = self._execute_kw(
            **creds, uid=uid,
            model="account.move",
            method="create",
            args=[vals],
        )
        logger.info(
            "Odoo draft invoice created: id=%s move_type=%s partner_id=%s",
            new_id, move_type, partner_id,
        )

        # Read back the auto-generated name for the response.
        record = self._search_read(
            **creds, uid=uid,
            model="account.move",
            domain=[["id", "=", new_id]],
            fields=["id", "name", "state"],
        )
        name = record[0]["name"] if record else str(new_id)
        return {"odoo_id": new_id, "name": name, "state": "draft"}

    @with_retry(base_delay=2, max_retries=3)
    def create_draft_quote(
        self,
        *,
        partner_id: int,
        validity_date: str | None = None,
        note: str | None = None,
        lines: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a DRAFT sales quotation (sale.order, state=draft) in Odoo.

        Returns ``{"odoo_id": int, "name": str, "state": "draft"}`` so the
        caller can surface it for human review before confirmation.

        Parameters
        ----------
        partner_id:
            Odoo res.partner ID of the customer.
        validity_date:
            Quote expiry date ``"YYYY-MM-DD"``.
        note:
            Internal note for the quotation.
        lines:
            List of order line dicts.  Each line should contain:
            ``{"product_id": int, "product_uom_qty": float, "price_unit": float,
               "name": str}``.
        """
        if self._dry_run:
            logger.info(
                "DRY_RUN: would create draft quotation for partner_id=%s", partner_id
            )
            return {"odoo_id": 0, "name": "DRY_RUN", "state": "draft", "dry_run": True}

        creds = self._resolve_creds()
        uid = self._authenticate(**creds)

        vals: dict[str, Any] = {"partner_id": partner_id}
        if validity_date:
            vals["validity_date"] = validity_date
        if note:
            vals["note"] = note
        if lines:
            vals["order_line"] = [
                (0, 0, {
                    "product_id": ln.get("product_id"),
                    "product_uom_qty": ln.get("product_uom_qty", 1),
                    "price_unit": ln.get("price_unit", 0),
                    "name": ln.get("name", ""),
                })
                for ln in lines
            ]

        new_id = self._execute_kw(
            **creds, uid=uid,
            model="sale.order",
            method="create",
            args=[vals],
        )
        logger.info(
            "Odoo draft quotation created: id=%s partner_id=%s", new_id, partner_id
        )

        record = self._search_read(
            **creds, uid=uid,
            model="sale.order",
            domain=[["id", "=", new_id]],
            fields=["id", "name", "state"],
        )
        name = record[0]["name"] if record else str(new_id)
        return {"odoo_id": new_id, "name": name, "state": "draft"}

    # ── private: JSON-RPC helpers ─────────────────────────────────────────────

    def _resolve_creds(self) -> dict[str, str]:
        """Resolve all 4 credential env vars at call time."""
        refs = self.credential_refs
        return {
            "url": os.getenv(refs["url"], "").rstrip("/"),
            "db": os.getenv(refs["db"], ""),
            "username": os.getenv(refs["username"], ""),
            "api_key": os.getenv(refs["api_key"], ""),
        }

    def _authenticate(self, *, url: str, db: str, username: str, api_key: str) -> int:
        """Authenticate via common/authenticate, return uid (int)."""
        result = self._jsonrpc(url, "common", "authenticate", [db, username, api_key, {}])
        if not isinstance(result, int) or result == 0:
            raise RuntimeError(f"Odoo authentication failed (uid={result!r})")
        return result

    def _search_read(
        self,
        *,
        url: str,
        db: str,
        username: str,
        api_key: str,
        uid: int,
        model: str,
        domain: list,
        fields: list[str],
        limit: int = 80,
        offset: int = 0,
        order: str = "",
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"fields": fields, "limit": limit, "offset": offset}
        if order:
            kwargs["order"] = order
        result = self._jsonrpc(
            url, "object", "execute_kw",
            [db, uid, api_key, model, "search_read", [domain], kwargs],
        )
        return result if isinstance(result, list) else []

    def _execute_kw(
        self,
        *,
        url: str,
        db: str,
        username: str,
        api_key: str,
        uid: int,
        model: str,
        method: str,
        args: list,
        kwargs: dict | None = None,
    ) -> Any:
        """Execute object/execute_kw with method and args."""
        return self._jsonrpc(
            url, "object", "execute_kw",
            [db, uid, api_key, model, method, args, kwargs or {}],
        )

    def _jsonrpc(self, url: str, service: str, method: str, args: list) -> Any:
        """Make a single Odoo JSON-RPC POST call via stdlib urllib."""
        self._request_id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "call",
            "id": self._request_id,
            "params": {"service": service, "method": method, "args": args},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{url}/jsonrpc",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Odoo HTTP {exc.code}: {exc.reason}") from exc

        if "error" in data:
            msg = (
                data["error"].get("data", {}).get("message")
                or data["error"].get("message")
                or "Unknown Odoo error"
            )
            raise RuntimeError(f"Odoo JSON-RPC error: {msg}")
        return data.get("result")
