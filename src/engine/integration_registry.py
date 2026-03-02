"""Integration registry — tracks health and last-contact state (FR-G037).

Persists state to ``Config/integration_registry.json``.

Usage::

    from src.engine.integration_registry import IntegrationRegistry

    registry = IntegrationRegistry(vault_root)
    registry.mark_healthy("gmail")
    registry.mark_degraded("odoo", "Connection timeout after 10s")
    registry.mark_down("linkedin", "HTTP 401: token expired")

    degraded = registry.get_degraded()  # ["odoo", "linkedin"]
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_REGISTRY_FILE = Path("Config") / "integration_registry.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntegrationRegistry:
    """Tracks health and last-contact state for named integrations.

    All state is persisted atomically to
    ``<vault_root>/Config/integration_registry.json``.

    Parameters
    ----------
    vault_root:
        Absolute path to the AI Employee vault root directory.
    """

    def __init__(self, vault_root: Path) -> None:
        self._vault_root = vault_root
        self._registry_path = vault_root / _REGISTRY_FILE

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def update(
        self,
        name: str,
        status: Literal["healthy", "degraded", "down"],
        *,
        error: str | None = None,
    ) -> None:
        """Update the named integration entry and persist to disk.

        Parameters
        ----------
        name:
            Unique integration identifier (e.g. ``"gmail"``, ``"odoo"``).
        status:
            One of ``"healthy"``, ``"degraded"``, or ``"down"``.
        error:
            Optional human-readable error description.  Pass ``None``
            when *status* is ``"healthy"`` to clear any prior error.
        """
        data = self._load()
        existing = data.get(name, {})
        now = _now_iso()

        entry: dict = {
            "status": status,
            "last_success": existing.get("last_success"),
            "last_error": None,
            "last_error_at": existing.get("last_error_at"),
            "updated_at": now,
        }

        if status == "healthy":
            entry["last_success"] = now
            entry["last_error"] = None
        else:
            entry["last_error"] = error
            entry["last_error_at"] = now

        data[name] = entry
        self._save(data)
        logger.debug(
            "[IntegrationRegistry] %s → %s%s",
            name,
            status,
            f" ({error})" if error else "",
        )

    def mark_healthy(self, name: str) -> None:
        """Record that *name* is healthy; clears last_error, sets last_success."""
        self.update(name, "healthy")

    def mark_degraded(self, name: str, error: str) -> None:
        """Record that *name* is degraded with an error description."""
        self.update(name, "degraded", error=error)

    def mark_down(self, name: str, error: str) -> None:
        """Record that *name* is fully down with an error description."""
        self.update(name, "down", error=error)

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def get(self, name: str) -> dict | None:
        """Return the registry entry for *name*, or ``None`` if not found."""
        return self._load().get(name)

    def get_all(self) -> dict[str, dict]:
        """Return a copy of the full registry."""
        return dict(self._load())

    def get_degraded(self) -> list[str]:
        """Return names of integrations with status ``degraded`` or ``down``."""
        data = self._load()
        return [
            name
            for name, entry in data.items()
            if entry.get("status") in ("degraded", "down")
        ]

    # ------------------------------------------------------------------
    # Private persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        """Read the registry JSON.  Returns ``{}`` on missing or corrupt file."""
        if not self._registry_path.exists():
            return {}
        try:
            raw = self._registry_path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[IntegrationRegistry] Failed to load %s: %s — starting fresh",
                self._registry_path,
                exc,
            )
            return {}

    def _save(self, data: dict) -> None:
        """Write the registry JSON atomically (write-then-rename)."""
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._registry_path.parent, suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp_path, str(self._registry_path))
        except OSError as exc:
            logger.error(
                "[IntegrationRegistry] Failed to save %s: %s",
                self._registry_path,
                exc,
            )
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
