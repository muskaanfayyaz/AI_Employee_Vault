"""Agent identity — reads AGENT_ID and AGENT_ENV from the environment.

Every agent process must have:

- ``AGENT_ID``  — unique name, e.g. ``"cloud-vm-001"`` or ``"local-dev"``
- ``AGENT_ENV`` — deployment tier: ``"cloud"`` or ``"local"``

These are set in the ``.env`` file *outside* the vault so they are never
committed to Git (Constitution II — Privacy First).

Usage::

    from src.agents.identity import AgentIdentity

    identity = AgentIdentity()
    print(identity.agent_id)   # "cloud-vm-001"
    print(identity.is_cloud)   # True
"""
from __future__ import annotations

import os
import socket


class AgentIdentity:
    """Resolves and exposes the current agent's identity.

    Resolution order for ``AGENT_ID``:
    1. ``AGENT_ID`` environment variable.
    2. Fallback: ``local-<hostname>``.

    Resolution order for ``AGENT_ENV``:
    1. ``AGENT_ENV`` environment variable (``"cloud"`` or ``"local"``).
    2. Fallback: ``"local"``.
    """

    def __init__(self) -> None:
        hostname = socket.gethostname()
        self._agent_id: str = os.getenv("AGENT_ID", f"local-{hostname}")
        raw_env = os.getenv("AGENT_ENV", "local").strip().lower()
        self._agent_env: str = raw_env if raw_env in ("cloud", "local") else "local"

    @property
    def agent_id(self) -> str:
        """Unique agent identifier string."""
        return self._agent_id

    @property
    def agent_env(self) -> str:
        """Deployment environment: ``'cloud'`` or ``'local'``."""
        return self._agent_env

    @property
    def is_cloud(self) -> bool:
        """``True`` when this agent is running in cloud mode."""
        return self._agent_env == "cloud"

    @property
    def is_local(self) -> bool:
        """``True`` when this agent is running in local mode."""
        return self._agent_env == "local"

    def __repr__(self) -> str:
        return f"AgentIdentity(id={self._agent_id!r}, env={self._agent_env!r})"
