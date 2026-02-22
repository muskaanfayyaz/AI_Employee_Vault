"""Abstract base watcher for the AI Employee System.

All watchers (filesystem, gmail, whatsapp, odoo, sync) extend
BaseWatcher and implement check_for_updates() and create_action_file().
The run() loop polls at a configurable interval with safe exception
handling so one bad cycle never crashes the watcher.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class BaseWatcher(ABC):
    """Abstract watcher that monitors a source for new events.

    Constructor takes a config dict matching the Watcher Configuration
    schema from data-model.md::

        watcher:
          name: "gmail-inbox"
          type: "filesystem | gmail | whatsapp | odoo"
          enabled: true
          polling_interval_seconds: 60
          ...

    Subclasses MUST implement:
        check_for_updates() -> list[dict]
        create_action_file(event, inbox_path) -> Path
    """

    def __init__(self, config: dict[str, Any]) -> None:
        watcher_cfg = config.get("watcher", config)
        self._name: str = watcher_cfg["name"]
        self._watcher_type: str = watcher_cfg["type"]
        self._enabled: bool = watcher_cfg.get("enabled", True)
        self._polling_interval: int = max(
            watcher_cfg.get("polling_interval_seconds", 60), 1
        )
        self._config: dict[str, Any] = watcher_cfg
        self._running: bool = False
        self._logger = logging.getLogger(
            f"{__name__}.{self._name}"
        )

    # ── read-only properties ──────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def watcher_type(self) -> str:
        return self._watcher_type

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def polling_interval(self) -> int:
        return self._polling_interval

    # ── abstract interface ────────────────────────────────────────

    @abstractmethod
    def check_for_updates(self) -> list[dict[str, Any]]:
        """Poll the source and return a list of new events.

        Each event is a dict with at least:
            - ``source``: origin identifier (e.g. filepath, message_id)
            - ``content``: raw content or reference
            - ``detected_at``: ISO-8601 timestamp

        Returns an empty list when there is nothing new.
        """

    @abstractmethod
    def create_action_file(
        self, event: dict[str, Any], inbox_path: Path
    ) -> Path:
        """Materialise an event as a markdown Task Item in *inbox_path*.

        Must write a ``.md`` file with YAML front-matter matching the
        Task Item schema (id, type, source, priority, status, etc.)
        and return the absolute path of the created file.
        """

    # ── optional overrides ────────────────────────────────────────

    def on_event(self, event: dict[str, Any]) -> None:
        """Hook called after each event is detected.

        Default implementation logs the event.  Subclasses may override
        for custom post-detection behaviour.
        """
        self._logger.info(
            "Event detected: source=%s",
            event.get("source", "unknown"),
        )

    def health_check(self) -> bool:
        """Return True if the watcher is operational.

        Default returns ``self._enabled and self._running``.
        Subclasses may add connectivity checks (API ping, etc.).
        """
        return self._enabled and self._running

    # ── lifecycle ─────────────────────────────────────────────────

    def start(self) -> None:
        """Mark the watcher as running and log startup."""
        self._running = True
        self._logger.info(
            "Watcher '%s' (%s) started — polling every %ds",
            self._name,
            self._watcher_type,
            self._polling_interval,
        )

    def stop(self) -> None:
        """Signal the run-loop to stop and log shutdown."""
        self._running = False
        self._logger.info("Watcher '%s' stopped", self._name)

    def run(self, inbox_path: Path, *, dry_run: bool = False) -> None:
        """Main polling loop — runs until stop() is called.

        1. Calls ``check_for_updates()`` each cycle.
        2. For every event, calls ``create_action_file()`` (unless
           *dry_run* is True) then ``on_event()``.
        3. Sleeps for ``polling_interval`` seconds between cycles.
        4. Any exception inside a cycle is logged and swallowed so
           the loop keeps running.

        Parameters
        ----------
        inbox_path:
            Vault ``Inbox/`` directory where action files are created.
        dry_run:
            When True, events are detected and logged but no files
            are written.
        """
        self.start()
        try:
            while self._running:
                self._run_cycle(inbox_path, dry_run=dry_run)
                time.sleep(self._polling_interval)
        except KeyboardInterrupt:
            self._logger.info("Interrupted — shutting down")
        finally:
            self.stop()

    # ── internals ─────────────────────────────────────────────────

    def _run_cycle(
        self, inbox_path: Path, *, dry_run: bool = False
    ) -> None:
        """Execute one poll-and-process cycle with safe exception handling."""
        try:
            events = self.check_for_updates()
            for event in events:
                self._process_event(event, inbox_path, dry_run=dry_run)
        except Exception:
            self._logger.exception(
                "Error in watcher '%s' cycle — will retry next interval",
                self._name,
            )

    def _process_event(
        self,
        event: dict[str, Any],
        inbox_path: Path,
        *,
        dry_run: bool = False,
    ) -> None:
        """Handle a single event: create file (or log in dry-run), notify."""
        try:
            if dry_run:
                self._logger.info(
                    "[DRY_RUN] Would create action file for: %s",
                    event.get("source", "unknown"),
                )
            else:
                path = self.create_action_file(event, inbox_path)
                self._logger.info("Action file created: %s", path)

            self.on_event(event)
        except Exception:
            self._logger.exception(
                "Error processing event from '%s'",
                event.get("source", "unknown"),
            )
