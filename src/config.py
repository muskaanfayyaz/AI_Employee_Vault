"""Configuration loader for the AI Employee System (T005).

Loads ``.env`` via python-dotenv and exposes typed constants:

- ``DRY_RUN`` — safety flag (default True)
- ``VAULT_ROOT`` — absolute vault path
- ``LOG_RETENTION_DAYS`` — audit log retention

Also provides ``credential_leak_check(content)`` which scans any
string for values loaded from ``.env`` and raises ``ValueError`` if a
credential is about to be written to a vault file (FR-035).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# Load .env from vault root (or wherever the process is run from).
_DOTENV_PATH = Path.cwd() / ".env"
load_dotenv(_DOTENV_PATH, override=True)

# ── Core settings ────────────────────────────────────────────────────────────

DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")

VAULT_ROOT: Path = Path(
    os.getenv("VAULT_ROOT", str(Path.cwd()))
).resolve()

LOG_RETENTION_DAYS: int = int(os.getenv("LOG_RETENTION_DAYS", "90"))

# ── Derived paths ─────────────────────────────────────────────────────────────

INBOX_PATH: Path = VAULT_ROOT / "Inbox"
NEEDS_ACTION_PATH: Path = VAULT_ROOT / "Needs_Action"
PLANS_PATH: Path = VAULT_ROOT / "Plans"
IN_PROGRESS_PATH: Path = VAULT_ROOT / "In_Progress"
PENDING_APPROVAL_PATH: Path = VAULT_ROOT / "Pending_Approval"
APPROVED_PATH: Path = VAULT_ROOT / "Approved"
REJECTED_PATH: Path = VAULT_ROOT / "Rejected"
DONE_PATH: Path = VAULT_ROOT / "Done"
ERRORS_PATH: Path = VAULT_ROOT / "Errors"
REPORTS_PATH: Path = VAULT_ROOT / "Reports"
LOGS_PATH: Path = VAULT_ROOT / "Logs"
CONFIG_PATH: Path = VAULT_ROOT / "Config"
SKILLS_PATH: Path = VAULT_ROOT / "Skills"

# ── Credential leak detection ─────────────────────────────────────────────────

def _load_env_values() -> set[str]:
    """Return a set of non-trivial values currently in the .env file."""
    values: set[str] = set()
    if _DOTENV_PATH.exists():
        for val in dotenv_values(_DOTENV_PATH).values():
            if val and len(val) >= 8:  # skip short/empty values
                values.add(val)
    return values


_ENV_VALUES: set[str] = _load_env_values()


def credential_leak_check(content: str) -> bool:
    """Raise ValueError if *content* contains any .env credential value.

    Returns ``True`` when content is clean.

    This guards against accidentally writing a raw credential into a
    vault file (FR-035). Call this before any vault file write.

    Raises
    ------
    ValueError
        When a credential value from ``.env`` is found in *content*.
    """
    for secret in _ENV_VALUES:
        if secret in content:
            raise ValueError(
                f"Credential leak detected: a .env value was found in the "
                f"content about to be written. Aborting write to protect "
                f"secrets. (Leaked value starts with: {secret[:4]}...)"
            )
    return True
