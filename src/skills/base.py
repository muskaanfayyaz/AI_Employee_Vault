"""Abstract base class for all AI Employee Agent Skills (T016).

Every concrete skill extends ``BaseSkill`` and implements:

- ``name`` — unique slug (e.g. ``"process_needs_action"``)
- ``version`` — semver string (e.g. ``"1.0.0"``)
- ``execute(input: SkillInput) -> SkillOutput``
- ``health_check() -> bool``

Usage::

    class MySkill(BaseSkill):
        @property
        def name(self) -> str:
            return "my_skill"

        @property
        def version(self) -> str:
            return "1.0.0"

        def execute(self, input: SkillInput) -> SkillOutput:
            ...

        def health_check(self) -> bool:
            return True
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class SkillInput:
    """Input contract for every skill invocation.

    Attributes
    ----------
    item_path:
        Path to the primary item being processed (a markdown file in
        the vault). May be ``None`` for skills that scan a directory
        rather than process a single item (e.g. dashboard regeneration).
    config:
        Arbitrary skill-specific configuration dict (loaded from
        ``Config/<skill_name>.yaml`` if present).
    dry_run:
        When ``True`` the skill MUST NOT write files, move items, or
        call external services. It should log what it *would* do.
    vault_root:
        Absolute path to the vault root directory. Defaults to cwd.
    """

    item_path: Path | None = None
    config: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = True
    vault_root: Path = field(default_factory=Path.cwd)


@dataclass
class SkillOutput:
    """Output contract returned by every skill invocation.

    Attributes
    ----------
    success:
        ``True`` if the skill completed without error.
    result:
        Human-readable summary of what was accomplished (one sentence).
    actions_taken:
        Ordered list of atomic actions performed (file moves, writes,
        API calls). Each entry is a short string.
    error:
        Error message if ``success`` is ``False``, else ``None``.
    metadata:
        Optional dict of structured result data (e.g. plan path,
        item_id) for callers that need programmatic access.
    """

    success: bool
    result: str
    actions_taken: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """Abstract agent skill that the AI Employee System can invoke.

    Subclasses MUST implement:
    - ``name`` (property) — unique skill slug
    - ``version`` (property) — semver string
    - ``execute(input)`` — core skill logic
    - ``health_check()`` — return ``True`` if skill is operational

    The base class provides a ``safe_execute()`` wrapper that catches
    unexpected exceptions and returns a failed ``SkillOutput`` rather
    than letting the error propagate to the processing loop.
    """

    # ── required properties ──────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique snake_case identifier for this skill."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string (e.g. ``"1.0.0"``)."""

    # ── required methods ─────────────────────────────────────────────

    @abstractmethod
    def execute(self, skill_input: SkillInput) -> SkillOutput:
        """Run the skill and return a structured result.

        This method is the sole entry point for skill execution.
        Implementations MUST:

        - Respect ``skill_input.dry_run`` — no side-effects when True.
        - Log each action at INFO level before performing it.
        - Return a ``SkillOutput`` with ``success=False`` on expected
          failures (bad input, file not found) rather than raising.
        - NOT swallow unexpected exceptions — let them propagate to
          ``safe_execute()`` for centralised handling.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Return ``True`` if this skill is ready to accept work.

        Called by the health monitor (Platinum tier) and the main loop.
        Should be fast (< 100ms) and non-destructive.
        """

    # ── provided helpers ─────────────────────────────────────────────

    def safe_execute(self, skill_input: SkillInput) -> SkillOutput:
        """Execute with top-level exception handling.

        Wraps ``execute()`` so that any unhandled exception results in a
        failed ``SkillOutput`` rather than crashing the calling loop.
        """
        _log = logging.getLogger(f"skill.{self.name}")
        try:
            _log.info(
                "Skill '%s' v%s starting | dry_run=%s | item=%s",
                self.name,
                self.version,
                skill_input.dry_run,
                skill_input.item_path,
            )
            output = self.execute(skill_input)
            if output.success:
                _log.info(
                    "Skill '%s' completed: %s (%d actions)",
                    self.name,
                    output.result,
                    len(output.actions_taken),
                )
            else:
                _log.warning(
                    "Skill '%s' reported failure: %s",
                    self.name,
                    output.error,
                )
            return output
        except Exception as exc:  # noqa: BLE001
            _log.exception("Skill '%s' raised an unexpected error", self.name)
            return SkillOutput(
                success=False,
                result=f"Skill '{self.name}' failed with an unexpected error.",
                error=str(exc),
            )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} version={self.version!r}>"
