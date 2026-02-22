"""Abstract base class for all Python MCP servers (T033).

Every MCP server (email, Odoo, social) extends ``BaseMCPServer`` and
implements its tool methods.  The base class provides:

- ``ping()`` — standard health-check tool matching the mcp-interfaces.md
  contract: ``{"status": "ok", "server": "<name>", "version": "<semver>"}``
- Credential-ref validation — ensures constructor args are env var names
  (UPPER_SNAKE_CASE), NEVER raw credential values
- ``_resolve_credential()`` — resolves an env-var name to its runtime value
- ``health_check()`` — True when all credential env vars are set
"""
from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

# Valid env var names: UPPER_SNAKE_CASE starting with a letter.
_ENV_VAR_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _validate_credential_ref(ref: str, param_name: str) -> None:
    """Raise ValueError if *ref* looks like a raw secret instead of an env var name.

    Parameters
    ----------
    ref:
        The value to validate (should be an env var name like
        ``"GMAIL_OAUTH_TOKEN_PATH"``).
    param_name:
        Name of the constructor parameter (used in the error message).

    Raises
    ------
    ValueError
        When *ref* does not match UPPER_SNAKE_CASE — indicating a raw
        credential was passed instead of an env var name.
    """
    if not ref:
        return  # empty string — caller may handle missing ref
    if not _ENV_VAR_PATTERN.match(ref):
        raise ValueError(
            f"{param_name!r} must be an environment variable name "
            f"(UPPER_SNAKE_CASE, e.g. 'GMAIL_OAUTH_TOKEN_PATH'), "
            f"not a raw credential value. Got: {ref!r}"
        )


class BaseMCPServer(ABC):
    """Abstract base for all AI Employee Python MCP servers.

    Subclasses MUST implement:
    - ``name`` (property) — unique server slug (e.g. ``"email-mcp"``)
    - ``version`` (property) — semver string (e.g. ``"1.0.0"``)
    - One or more tool methods decorated with ``@with_retry``

    Constructor validates that all credential_refs values are env var
    names — never raw secrets.  Raw credential values (e.g. token
    strings, file paths, API keys) must be stored in ``.env`` and
    referenced by env var name only.

    Parameters
    ----------
    credential_refs:
        ``{logical_name: ENV_VAR_NAME}`` mapping.  Each value must be
        an UPPER_SNAKE_CASE environment variable name.  Raw secrets
        are rejected at construction time.

    Example
    -------
    >>> server = EmailMCPServer({"token_path": "GMAIL_OAUTH_TOKEN_PATH"})
    >>> server.ping()
    {'status': 'ok', 'server': 'email-mcp', 'version': '1.0.0'}
    """

    def __init__(
        self,
        credential_refs: dict[str, str] | None = None,
    ) -> None:
        for param_name, ref in (credential_refs or {}).items():
            _validate_credential_ref(ref, param_name)
        self._credential_refs: dict[str, str] = dict(credential_refs or {})
        self._logger = logging.getLogger(
            f"{__name__}.{type(self).__name__}"
        )

    # ── required properties ───────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique server name/slug (e.g. ``"email-mcp"``)."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Server version as semver string (e.g. ``"1.0.0"``)."""

    # ── transport (fixed for Python servers) ──────────────────────────────────

    @property
    def transport(self) -> str:
        """MCP transport.  Always ``"stdio"`` for Python MCP servers."""
        return "stdio"

    # ── standard tool: ping ───────────────────────────────────────────────────

    def ping(self) -> dict[str, Any]:
        """Standard health-check tool (mcp-interfaces.md contract).

        Returns
        -------
        dict
            ``{"status": "ok", "server": <name>, "version": <version>}``
        """
        return {
            "status": "ok",
            "server": self.name,
            "version": self.version,
        }

    # ── health check ─────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Return True when all registered credential env vars are set."""
        for env_var_name in self._credential_refs.values():
            if not os.getenv(env_var_name):
                self._logger.debug(
                    "health_check: env var %r is not set", env_var_name
                )
                return False
        return True

    # ── credential resolution ─────────────────────────────────────────────────

    def _resolve_credential(self, ref_key: str) -> str:
        """Resolve a credential reference to its env-var value at runtime.

        Parameters
        ----------
        ref_key:
            Logical key registered in ``credential_refs``
            (e.g. ``"token_path"``).

        Returns
        -------
        str
            The environment variable value (the actual secret / path).

        Raises
        ------
        ValueError
            If *ref_key* was not registered in ``credential_refs``.
        KeyError
            If the corresponding env var is not set in the environment.
        """
        env_var_name = self._credential_refs.get(ref_key)
        if env_var_name is None:
            raise ValueError(
                f"Credential ref {ref_key!r} is not registered. "
                f"Registered keys: {list(self._credential_refs)}"
            )
        value = os.getenv(env_var_name)
        if value is None:
            raise KeyError(
                f"Environment variable {env_var_name!r} is not set. "
                "Check your .env file or environment."
            )
        return value

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} "
            f"name={self.name!r} version={self.version!r}>"
        )
