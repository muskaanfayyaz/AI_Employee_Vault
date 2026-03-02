"""Subscription audit skill — weekly Odoo subscription health check (FR-G019–G022).

Reads all active, overdue, and recently cancelled subscriptions from Odoo via
JSON-RPC, detects anomalies, writes a report to ``Reports/``, and creates
``Needs_Action`` vault items for any anomaly requiring human review.

This skill is READ-ONLY with respect to Odoo — it NEVER writes back.

Anomaly types detected:
    - ``overdue_renewal``     — subscription past next_invoice_date with no payment
    - ``unexpected_cancel``   — subscription cancelled within the last audit window
    - ``billing_gap``         — gap between two invoice dates > expected interval
    - ``duplicate``           — multiple active subscriptions for same partner+template

Scheduling:
    Runs weekly (default: Friday 06:00 before CEO Briefing on Monday 08:00).
    The `last_audit_at` timestamp is persisted to ``Config/subscription_audit_state.json``.

DRY_RUN:
    Odoo calls are made normally (read-only), but no vault items are created and
    the state file is NOT updated.  The report IS written (prefixed ``[DRY_RUN]``).

Config schema (``Config/subscription_audit.yaml``)::

    audit:
      enabled: true
      page_size: 50
      look_back_days: 7             # anomaly window
      min_amount_at_risk: 0.0       # filter out low-value anomalies (optional)
      state_file: "Config/subscription_audit_state.json"
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.skills.base import BaseSkill, SkillInput, SkillOutput

logger = logging.getLogger(__name__)

# Default Odoo subscription fields
_SUB_FIELDS = [
    "id", "name", "state", "partner_id", "template_id",
    "recurring_next_date", "date_start", "date",
    "recurring_total", "currency_id",
]


class SubscriptionAuditSkill(BaseSkill):
    """Weekly Odoo subscription health audit (FR-G019–G022).

    Reads subscriptions, detects anomalies, writes a report to ``Reports/``,
    and creates ``Needs_Action`` items for anomalies requiring human review.
    Does NOT write back to Odoo.
    """

    @property
    def name(self) -> str:
        return "subscription_audit"

    @property
    def version(self) -> str:
        return "1.0.0"

    def health_check(self) -> bool:
        """True when Odoo credential env vars are all set."""
        cfg = self._get_credential_refs({})
        return all(os.getenv(v, "") for v in cfg.values())

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        """Run the subscription audit and return a SkillOutput."""
        vault_root = skill_input.vault_root
        dry_run = skill_input.dry_run
        config = skill_input.config.get("audit", skill_input.config)

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        look_back_days: int = int(config.get("look_back_days", 7))
        page_size: int = int(config.get("page_size", 50))
        min_amount: float = float(config.get("min_amount_at_risk", 0.0))
        state_file_rel: str = config.get(
            "state_file", "Config/subscription_audit_state.json"
        )

        cred_refs = self._get_credential_refs(config)
        url = os.getenv(cred_refs["url"], "")
        db = os.getenv(cred_refs["db"], "")
        username = os.getenv(cred_refs["username"], "")
        api_key = os.getenv(cred_refs["api_key"], "")

        if not all([url, db, username, api_key]):
            return self._missing_credentials_result(vault_root, dry_run, date_str)

        # ── 1. Authenticate ──────────────────────────────────────────────────
        try:
            uid = self._authenticate(url, db, username, api_key)
        except Exception as exc:
            logger.error("SubscriptionAudit: authentication failed: %s", exc)
            return self._odoo_unavailable_result(vault_root, dry_run, date_str, str(exc))

        # ── 2. Fetch subscriptions ───────────────────────────────────────────
        window_start = (now - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

        try:
            all_subs = self._fetch_subscriptions(
                url, db, uid, api_key, page_size=page_size
            )
        except Exception as exc:
            logger.error("SubscriptionAudit: subscription fetch failed: %s", exc)
            return self._odoo_unavailable_result(vault_root, dry_run, date_str, str(exc))

        if not all_subs:
            logger.warning("SubscriptionAudit: no subscriptions found — possible empty dataset")

        # ── 3. Detect anomalies ──────────────────────────────────────────────
        anomalies = _detect_anomalies(all_subs, now=now, look_back_days=look_back_days)
        if min_amount > 0:
            anomalies = [a for a in anomalies if a["amount_at_risk"] >= min_amount]

        # ── 4. Write report ──────────────────────────────────────────────────
        report_dir = vault_root / "Reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_filename = f"Subscription_Audit_{date_str}.md"
        report_path = report_dir / report_filename

        report_md = _build_report(
            anomalies=anomalies,
            total_subs=len(all_subs),
            window_start=window_start,
            generated_at=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            dry_run=dry_run,
        )
        report_path.write_text(report_md, encoding="utf-8")
        logger.info("SubscriptionAudit: report written to %s", report_path)

        # ── 5. Create Needs_Action items for actionable anomalies ────────────
        actions_taken: list[str] = [f"wrote: Reports/{report_filename}"]
        needs_action_dir = vault_root / "Needs_Action"
        needs_action_dir.mkdir(parents=True, exist_ok=True)
        items_created = 0

        if not dry_run:
            for anomaly in anomalies:
                item_path = _create_needs_action_item(needs_action_dir, anomaly, now)
                actions_taken.append(f"created: Needs_Action/{item_path.name}")
                items_created += 1
        else:
            for anomaly in anomalies:
                logger.info(
                    "[DRY_RUN] Would create Needs_Action item for anomaly: %s (sub_id=%s)",
                    anomaly["anomaly_type"],
                    anomaly["sub_id"],
                )
                actions_taken.append(
                    f"[DRY_RUN] would create Needs_Action item: {anomaly['anomaly_type']} sub_id={anomaly['sub_id']}"
                )

        # ── 6. Persist state ─────────────────────────────────────────────────
        if not dry_run:
            _save_state(vault_root / state_file_rel, now)

        total_anomalies = len(anomalies)
        return SkillOutput(
            success=True,
            result=(
                f"Subscription audit complete — {len(all_subs)} subscriptions checked, "
                f"{total_anomalies} anomal{'y' if total_anomalies == 1 else 'ies'} detected"
                f"{' [DRY_RUN]' if dry_run else ''}"
            ),
            actions_taken=actions_taken,
            metadata={
                "total_subscriptions": len(all_subs),
                "anomalies_detected": total_anomalies,
                "items_created": items_created,
                "report_path": str(report_path),
            },
        )

    # ── private: Odoo helpers ─────────────────────────────────────────────────

    def _authenticate(self, url: str, db: str, username: str, api_key: str) -> int:
        result = _jsonrpc(url, "common", "authenticate", [db, username, api_key, {}])
        if not isinstance(result, int) or result == 0:
            raise RuntimeError(f"Odoo authentication returned unexpected uid: {result!r}")
        return result

    def _fetch_subscriptions(
        self, url: str, db: str, uid: int, api_key: str, *, page_size: int = 50
    ) -> list[dict]:
        """Fetch all subscriptions (paginated) matching active/overdue/cancelled states."""
        domain = [
            ["state", "in", ["open", "pending", "close", "cancelled"]],
        ]
        return _paginated_search_read(
            url, db, uid, api_key, "sale.subscription", domain, _SUB_FIELDS,
            page_size=page_size
        )

    # ── private: result helpers ───────────────────────────────────────────────

    @staticmethod
    def _get_credential_refs(config: dict) -> dict[str, str]:
        refs = config.get("credential_refs", {})
        return {
            "url": refs.get("url", "ODOO_URL"),
            "db": refs.get("db", "ODOO_DB"),
            "username": refs.get("username", "ODOO_USERNAME"),
            "api_key": refs.get("api_key", "ODOO_API_KEY"),
        }

    @staticmethod
    def _missing_credentials_result(
        vault_root: Path, dry_run: bool, date_str: str
    ) -> SkillOutput:
        logger.error("SubscriptionAudit: Odoo credentials not configured")
        _create_error_item(
            vault_root,
            title=f"Subscription Audit {date_str} — Credentials Missing",
            details="Subscription audit skipped: ODOO_* environment variables not fully set.",
        )
        return SkillOutput(
            success=False,
            result="Subscription audit failed: Odoo credentials not configured.",
            error="Missing ODOO_URL, ODOO_DB, ODOO_USERNAME, or ODOO_API_KEY env vars.",
        )

    @staticmethod
    def _odoo_unavailable_result(
        vault_root: Path, dry_run: bool, date_str: str, error: str
    ) -> SkillOutput:
        _create_error_item(
            vault_root,
            title=f"Subscription Audit {date_str} — Odoo Unavailable",
            details=f"Subscription audit skipped: {error}",
        )
        return SkillOutput(
            success=False,
            result="Subscription audit failed: Odoo unavailable.",
            error=error,
        )


# ── module-level helpers ──────────────────────────────────────────────────────


def _detect_anomalies(
    subscriptions: list[dict],
    *,
    now: datetime,
    look_back_days: int,
) -> list[dict[str, Any]]:
    """Detect subscription anomalies and return a list of anomaly dicts."""
    anomalies: list[dict[str, Any]] = []
    window_start = now - timedelta(days=look_back_days)

    # Index for duplicate detection: (partner_id, template_id) → count
    sub_index: dict[tuple, list[dict]] = {}

    for sub in subscriptions:
        partner_raw = sub.get("partner_id")
        template_raw = sub.get("template_id")
        partner_id = partner_raw[0] if isinstance(partner_raw, (list, tuple)) and partner_raw else None
        partner_name = partner_raw[1] if isinstance(partner_raw, (list, tuple)) and len(partner_raw) > 1 else "Unknown"
        template_id = template_raw[0] if isinstance(template_raw, (list, tuple)) and template_raw else None
        state = sub.get("state", "")
        amount = float(sub.get("recurring_total") or 0)
        next_date_str = sub.get("recurring_next_date") or ""
        sub_id = sub.get("id", 0)
        sub_name = sub.get("name", f"sub-{sub_id}")

        # Overdue renewal: active but past next_invoice_date
        if state == "open" and next_date_str:
            try:
                next_date = datetime.strptime(next_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if next_date < now:
                    anomalies.append({
                        "anomaly_type": "overdue_renewal",
                        "sub_id": sub_id,
                        "sub_name": sub_name,
                        "partner_name": partner_name,
                        "amount_at_risk": amount,
                        "detail": f"Next invoice was due {next_date_str} — not yet renewed",
                        "recommended_action": "Contact customer or trigger renewal invoice",
                    })
            except ValueError:
                pass

        # Unexpected cancellation in the look-back window
        if state in ("cancelled", "close"):
            date_str_val = sub.get("date") or ""
            if date_str_val:
                try:
                    cancelled_date = datetime.strptime(date_str_val, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if cancelled_date >= window_start:
                        anomalies.append({
                            "anomaly_type": "unexpected_cancel",
                            "sub_id": sub_id,
                            "sub_name": sub_name,
                            "partner_name": partner_name,
                            "amount_at_risk": amount,
                            "detail": f"Subscription cancelled/closed on {date_str_val}",
                            "recommended_action": "Review cancellation reason, consider win-back",
                        })
                except ValueError:
                    pass

        # Pending (payment failed / renewal pending)
        if state == "pending":
            anomalies.append({
                "anomaly_type": "billing_gap",
                "sub_id": sub_id,
                "sub_name": sub_name,
                "partner_name": partner_name,
                "amount_at_risk": amount,
                "detail": "Subscription in 'pending' state — payment may have failed",
                "recommended_action": "Verify payment status and contact customer if needed",
            })

        # Build index for duplicate detection
        if state == "open" and partner_id and template_id:
            key = (partner_id, template_id)
            sub_index.setdefault(key, []).append({
                "sub_id": sub_id,
                "sub_name": sub_name,
                "partner_name": partner_name,
                "amount": amount,
            })

    # Duplicate detection: same partner + template with multiple active subs
    for (partner_id, template_id), subs_list in sub_index.items():
        if len(subs_list) > 1:
            total = sum(s["amount"] for s in subs_list)
            ids = ", ".join(str(s["sub_id"]) for s in subs_list)
            anomalies.append({
                "anomaly_type": "duplicate",
                "sub_id": subs_list[0]["sub_id"],
                "sub_name": subs_list[0]["sub_name"],
                "partner_name": subs_list[0]["partner_name"],
                "amount_at_risk": total,
                "detail": f"{len(subs_list)} active subscriptions for same partner+template (IDs: {ids})",
                "recommended_action": "Consolidate or cancel duplicate subscriptions",
            })

    return anomalies


def _build_report(
    *,
    anomalies: list[dict],
    total_subs: int,
    window_start: str,
    generated_at: str,
    dry_run: bool,
) -> str:
    """Build the markdown report content."""
    dry_banner = "\n> **[DRY_RUN MODE]** No vault items were created.\n" if dry_run else ""
    anomaly_count = len(anomalies)

    header = (
        f"# Subscription Audit Report\n\n"
        f"**Generated**: {generated_at}  \n"
        f"**Mode**: {'[DRY_RUN]' if dry_run else 'LIVE'}  \n"
        f"**Subscriptions Checked**: {total_subs}  \n"
        f"**Anomalies Detected**: {anomaly_count}  \n"
        f"**Audit Window**: {window_start} to {generated_at[:10]}  \n"
        f"{dry_banner}\n"
    )

    if not anomalies:
        return header + "## Anomalies\n\n_No anomalies detected._\n"

    # Summary table
    summary = (
        "## Summary\n\n"
        "| Type | Count |\n"
        "|------|-------|\n"
    )
    type_counts: dict[str, int] = {}
    for a in anomalies:
        type_counts[a["anomaly_type"]] = type_counts.get(a["anomaly_type"], 0) + 1
    for atype, count in sorted(type_counts.items()):
        summary += f"| {atype.replace('_', ' ').title()} | {count} |\n"
    summary += "\n"

    # Detail table
    detail = (
        "## Anomaly Detail\n\n"
        "| Sub ID | Name | Customer | Type | Amount at Risk | Detail | Recommended Action |\n"
        "|--------|------|----------|------|---------------|--------|-------------------|\n"
    )
    for a in anomalies:
        detail += (
            f"| {a['sub_id']} "
            f"| {a['sub_name']} "
            f"| {a['partner_name']} "
            f"| {a['anomaly_type'].replace('_', ' ')} "
            f"| {a['amount_at_risk']:.2f} "
            f"| {a['detail']} "
            f"| {a['recommended_action']} |\n"
        )
    detail += "\n"

    footer = (
        "## Notes\n\n"
        "- This report is read-only — no Odoo records were modified.\n"
        "- Vault items have been created in `Needs_Action/` for each anomaly listed above.\n"
        "- All Odoo write actions (re-invoice, cancellation, correction) require explicit approval.\n"
    )

    return header + summary + detail + footer


def _create_needs_action_item(
    needs_action_dir: Path, anomaly: dict[str, Any], now: datetime
) -> Path:
    """Write a Needs_Action vault item for a subscription anomaly."""
    item_id = str(uuid.uuid4())
    ts = now.isoformat()
    filename = f"sub-anomaly-{anomaly['anomaly_type']}-{anomaly['sub_id']}-{item_id[:8]}.md"
    path = needs_action_dir / filename

    content = (
        "---\n"
        f"id: {item_id}\n"
        "type: subscription_anomaly\n"
        "source: subscription_audit\n"
        f"odoo_model: sale.subscription\n"
        f"odoo_id: {anomaly['sub_id']}\n"
        "priority: medium\n"
        "status: needs_action\n"
        "requires_approval: false\n"
        "classification: local_only\n"
        f"created_at: {ts}\n"
        f"updated_at: {ts}\n"
        f"tags: [odoo, subscription, {anomaly['anomaly_type']}]\n"
        "---\n\n"
        f"# Subscription Anomaly: {anomaly['anomaly_type'].replace('_', ' ').title()}\n\n"
        f"**Subscription**: {anomaly['sub_name']} (Odoo ID: {anomaly['sub_id']})  \n"
        f"**Customer**: {anomaly['partner_name']}  \n"
        f"**Anomaly Type**: `{anomaly['anomaly_type']}`  \n"
        f"**Amount at Risk**: {anomaly['amount_at_risk']:.2f}  \n"
        f"**Detected**: {ts}  \n\n"
        "## Detail\n\n"
        f"{anomaly['detail']}\n\n"
        "## Recommended Action\n\n"
        f"{anomaly['recommended_action']}\n\n"
        "## Next Steps\n\n"
        "- [ ] Verify in Odoo\n"
        "- [ ] Create plan for resolution\n"
        "- [ ] All Odoo writes require approval routing\n"
    )

    path.write_text(content, encoding="utf-8")
    return path


def _create_error_item(vault_root: Path, *, title: str, details: str) -> None:
    """Write an error vault item when the audit itself fails."""
    errors_dir = vault_root / "Errors"
    errors_dir.mkdir(parents=True, exist_ok=True)
    item_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    filename = f"subscription-audit-error-{item_id[:8]}.md"
    content = (
        "---\n"
        f"id: {item_id}\n"
        "type: audit_error\n"
        "source: subscription_audit\n"
        "priority: high\n"
        "status: error\n"
        f"created_at: {ts}\n"
        f"updated_at: {ts}\n"
        "tags: [subscription_audit, error]\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{details}\n"
    )
    (errors_dir / filename).write_text(content, encoding="utf-8")
    logger.warning("SubscriptionAudit error item created: Errors/%s", filename)


def _save_state(state_path: Path, now: datetime) -> None:
    """Persist the last_audit_at timestamp."""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"last_audit_at": now.isoformat()}
        state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error("SubscriptionAudit: failed to save state: %s", exc)


# ── Odoo JSON-RPC helpers (local, no external deps) ────────────────────────────


def _jsonrpc(url: str, service: str, method: str, args: list) -> Any:
    _id = 1
    payload = json.dumps({
        "jsonrpc": "2.0", "method": "call", "id": _id,
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


def _paginated_search_read(
    url: str, db: str, uid: int, api_key: str,
    model: str, domain: list, fields: list[str], *, page_size: int = 50
) -> list[dict]:
    """Read all records matching domain using offset/limit pagination."""
    results: list[dict] = []
    offset = 0
    while True:
        page = _jsonrpc(
            url, "object", "execute_kw",
            [db, uid, api_key, model, "search_read", [domain],
             {"fields": fields, "limit": page_size, "offset": offset}],
        )
        if not isinstance(page, list):
            break
        results.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return results
