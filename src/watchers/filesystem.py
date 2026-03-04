"""Filesystem watcher for the AI Employee System — Bronze tier (T020).

Monitors a configured ``drop_folder`` directory for new files using
``watchdog`` OS-level events.  When a stable new file is detected it:

1. Copies the original file into ``Needs_Action/``.
2. Creates a companion ``<stem>-metadata.md`` Task Item alongside.
3. Appends an entry to the daily JSON audit log
   (``Logs/YYYY-MM-DD.json``).
4. Skips all side-effects when ``DRY_RUN`` is active.

Usage (standalone)::

    python -m src.watchers.filesystem

Or via the BaseWatcher run loop::

    from src.watchers.filesystem import FilesystemWatcher
    watcher = FilesystemWatcher({"watcher": {"name": "drop-folder",
                                              "type": "filesystem"}})
    watcher.run(inbox_path=Path("Needs_Action"), dry_run=False)
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from src.watchers.base import BaseWatcher


logger = logging.getLogger(__name__)

# Seconds without modification before a file is considered stable.
_DEFAULT_STABILITY_SECONDS: float = 2.0

# Poll interval for the stability-check sub-loop (seconds).
_STABILITY_POLL_INTERVAL: float = 0.5


# ---------------------------------------------------------------------------
# Internal watchdog event handler
# ---------------------------------------------------------------------------


class _DropFolderHandler(FileSystemEventHandler):
    """Pushes newly-created file paths onto a shared Queue."""

    def __init__(self, queue: "Queue[str]") -> None:
        super().__init__()
        self._queue = queue

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._queue.put(event.src_path)
            logger.debug("Queued for stability check: %s", event.src_path)


# ---------------------------------------------------------------------------
# FilesystemWatcher
# ---------------------------------------------------------------------------


class FilesystemWatcher(BaseWatcher):
    """watchdog-powered watcher for the ``drop_folder`` directory.

    Config keys (all under the ``watcher`` key, or at the top level):

    ==================== ============== ==================================
    Key                  Default        Description
    ==================== ============== ==================================
    ``watch_path``       ``drop_folder`` Directory to monitor
    ``needs_action_path````Needs_Action`` Destination for copied files
    ``vault_root``       *cwd*          Vault root (paths are relative to)
    ``stability_seconds``2.0            Quiet period before processing
    ==================== ============== ==================================

    Example::

        config = {
            "watcher": {
                "name": "drop-folder",
                "type": "filesystem",
                "enabled": True,
                "watch_path": "drop_folder",
                "needs_action_path": "Needs_Action",
                "stability_seconds": 2.0,
            }
        }
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = config.get("watcher", config)

        vault_root = Path(cfg.get("vault_root", Path.cwd())).resolve()
        self._watch_path: Path = vault_root / cfg.get("watch_path", "drop_folder")
        self._needs_action_path: Path = vault_root / cfg.get(
            "needs_action_path", "Needs_Action"
        )
        self._stability_seconds: float = float(
            cfg.get("stability_seconds", _DEFAULT_STABILITY_SECONDS)
        )
        self._log_dir: Path = vault_root / "Logs"

        self._event_queue: "Queue[str]" = Queue()
        self._observer: Observer | None = None

        # {path_str: (first_queued_monotonic, last_seen_mtime)}
        self._pending: dict[str, tuple[float, float]] = {}

    # ── BaseWatcher abstract implementation ───────────────────────────────

    def check_for_updates(self) -> list[dict[str, Any]]:
        """Drain the event queue and return a list of stable-file events.

        A file is considered stable when it has not been modified for at
        least ``stability_seconds`` *and* it has been queued for at least
        that long.
        """
        # Pull all new paths from the watchdog queue.
        while True:
            try:
                raw = self._event_queue.get_nowait()
                path = Path(raw)
                if path.exists():
                    mtime = path.stat().st_mtime
                    self._pending.setdefault(raw, (time.monotonic(), mtime))
            except Empty:
                break

        now_mono = time.monotonic()
        now_wall = time.time()
        stable: list[dict[str, Any]] = []
        done_keys: list[str] = []

        for path_str, (queued_at, _first_mtime) in list(self._pending.items()):
            path = Path(path_str)

            if not path.exists():
                done_keys.append(path_str)
                continue

            try:
                stat = path.stat()
            except OSError:
                done_keys.append(path_str)
                continue

            queued_elapsed = now_mono - queued_at
            mtime_age = now_wall - stat.st_mtime

            if (
                queued_elapsed >= self._stability_seconds
                and mtime_age >= self._stability_seconds
            ):
                stable.append(
                    {
                        "source": path_str,
                        "content": path_str,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                        "file_path": path,
                        "file_name": path.name,
                        "file_size": stat.st_size,
                    }
                )
                done_keys.append(path_str)

        for key in done_keys:
            self._pending.pop(key, None)

        return stable

    def create_action_file(
        self, event: dict[str, Any], inbox_path: Path
    ) -> Path:
        """Copy dropped file to Needs_Action/ and write companion metadata .md.

        If the dropped file already contains valid TaskItem YAML front-matter
        (i.e. it has a recognised ``type`` field other than the generic
        ``file``), it is treated as a first-class vault item: the copy is
        returned directly without creating a separate metadata wrapper.

        Returns the path of the action file to process.
        """
        src_path = Path(event["source"])
        timestamp = datetime.now(timezone.utc)
        item_id = str(uuid.uuid4())

        # ── Copy original file ──────────────────────────────────────────
        dest_file = self._needs_action_path / src_path.name
        if dest_file.exists():
            dest_file = (
                self._needs_action_path / f"{item_id[:8]}-{src_path.name}"
            )

        shutil.copy2(src_path, dest_file)
        self._logger.info("Copied %s → %s", src_path.name, dest_file)

        # ── Check if this is already a TaskItem vault file ──────────────
        # A file is a first-class vault item when its YAML front-matter
        # contains a 'type' that the TaskItem model recognises as non-generic.
        if _is_vault_item(dest_file):
            _ensure_needs_action_status(dest_file)
            self._logger.info(
                "Vault item detected (%s) — skipping metadata wrapper",
                dest_file.name,
            )
            _append_audit_log(
                log_dir=self._log_dir,
                item_id=item_id,
                src_path=src_path,
                dest_file=dest_file,
                meta_path=dest_file,
                timestamp=timestamp,
                dry_run=False,
            )
            return dest_file

        # ── Create metadata .md (Task Item) ────────────────────────────
        meta_path = self._needs_action_path / f"{dest_file.stem}-metadata.md"
        _write_metadata(
            path=meta_path,
            item_id=item_id,
            src_path=src_path,
            dest_file=dest_file,
            file_size=event.get("file_size", 0),
            timestamp=timestamp,
        )
        self._logger.info("Metadata created: %s", meta_path.name)

        # ── Audit log entry ─────────────────────────────────────────────
        _append_audit_log(
            log_dir=self._log_dir,
            item_id=item_id,
            src_path=src_path,
            dest_file=dest_file,
            meta_path=meta_path,
            timestamp=timestamp,
            dry_run=False,
        )

        return meta_path

    # ── on_event hook ─────────────────────────────────────────────────────

    def on_event(self, event: dict[str, Any]) -> None:
        self._logger.info(
            "File detected: %s  (%.0f bytes, detected at %s)",
            event.get("file_name", event.get("source")),
            event.get("file_size", 0),
            event.get("detected_at", ""),
        )

    # ── Lifecycle overrides ───────────────────────────────────────────────

    def start(self) -> None:
        """Create watched directories and start the watchdog observer thread.

        Uses the native OS observer (inotify on Linux) when available.
        Falls back to ``PollingObserver`` on Windows filesystem mounts
        (e.g. ``/mnt/d/`` in WSL2) where inotify is not supported.
        """
        self._watch_path.mkdir(parents=True, exist_ok=True)
        self._needs_action_path.mkdir(parents=True, exist_ok=True)
        self._log_dir.mkdir(parents=True, exist_ok=True)

        handler = _DropFolderHandler(self._event_queue)
        self._observer = _make_observer(self._watch_path)
        self._observer.schedule(handler, str(self._watch_path), recursive=False)
        self._observer.start()

        # Queue any files already sitting in drop_folder at startup.
        for existing in self._watch_path.iterdir():
            if existing.is_file() and not existing.name.startswith("."):
                self._event_queue.put(str(existing))
                self._logger.info("Startup scan: queued pre-existing file %s", existing.name)

        super().start()
        observer_type = type(self._observer).__name__
        self._logger.info(
            "Watching '%s' → '%s'  [observer: %s]",
            self._watch_path,
            self._needs_action_path,
            observer_type,
        )

    def stop(self) -> None:
        """Stop the watchdog observer and clean up."""
        if self._observer is not None and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5)
        super().stop()

    def health_check(self) -> bool:
        """Return True when the watchdog observer thread is alive."""
        if self._observer is None:
            return False
        return self._observer.is_alive() and self._enabled

    def run(
        self,
        inbox_path: Path,
        *,
        dry_run: bool = False,
    ) -> None:
        """Event-driven main loop using watchdog + stability polling.

        Overrides the parent's polling loop with a tight sub-loop that
        checks for newly-stable files every ``_STABILITY_POLL_INTERVAL``
        seconds.  DRY_RUN mode is enforced by the parent
        ``_process_event`` method, which logs instead of writing files.

        Parameters
        ----------
        inbox_path:
            Passed through to ``_run_cycle`` / ``create_action_file``
            (for API compatibility — this watcher uses
            ``self._needs_action_path`` internally).
        dry_run:
            When ``True``, files are detected and logged but nothing is
            copied and no metadata or audit entries are written.
        """
        self.start()
        dry_run_flag = dry_run or _resolve_dry_run()
        if dry_run_flag:
            self._logger.info(
                "[DRY_RUN] Filesystem watcher running in dry-run mode — "
                "no files will be copied."
            )

        try:
            while self._running:
                self._run_cycle(inbox_path, dry_run=dry_run_flag)
                time.sleep(_STABILITY_POLL_INTERVAL)
        except KeyboardInterrupt:
            self._logger.info("Interrupted — shutting down filesystem watcher")
        finally:
            self.stop()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_dry_run() -> bool:
    """Read DRY_RUN from the environment.

    Tries ``src.config.DRY_RUN`` first (when config.py has been
    implemented); falls back to the ``DRY_RUN`` environment variable
    (default: ``true`` for safety).
    """
    try:
        from src.config import DRY_RUN  # type: ignore[import]

        return bool(DRY_RUN)
    except ImportError:
        return os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")


_VAULT_ITEM_TYPES = {"email", "message", "social", "social_post", "erp", "audit"}


def _is_vault_item(path: Path) -> bool:
    """Return True if *path* has YAML front-matter with a non-generic 'type'."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    try:
        end = text.index("---", 3)
        fm = text[3:end]
    except ValueError:
        return False
    for line in fm.splitlines():
        stripped = line.strip()
        if stripped.startswith("type:"):
            _, _, raw = stripped.partition(":")
            item_type = raw.strip().strip('"').strip("'")
            return item_type in _VAULT_ITEM_TYPES
    return False


def _ensure_needs_action_status(path: Path) -> None:
    """Overwrite the 'status:' line in YAML front-matter with 'needs_action'."""
    try:
        text = path.read_text(encoding="utf-8")
        updated = re.sub(
            r"^(status:\s*).*$", r"\1needs_action", text, count=1, flags=re.MULTILINE
        )
        if updated != text:
            path.write_text(updated, encoding="utf-8")
    except OSError:
        pass


def _write_metadata(
    *,
    path: Path,
    item_id: str,
    src_path: Path,
    dest_file: Path,
    file_size: int,
    timestamp: datetime,
) -> None:
    """Write a YAML-front-matter Task Item markdown file."""
    iso = timestamp.isoformat()
    human_ts = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

    content = (
        "---\n"
        f"id: {item_id}\n"
        "type: file\n"
        "source: filesystem\n"
        f"source_path: {src_path.resolve()}\n"
        f"destination: {dest_file.resolve()}\n"
        "priority: medium\n"
        "status: needs_action\n"
        "requires_approval: false\n"
        "classification: local_only\n"
        f"created_at: {iso}\n"
        f"updated_at: {iso}\n"
        "tags: []\n"
        "---\n\n"
        f"# Action Item: {src_path.name}\n\n"
        f"**Source**: `{src_path}`  \n"
        f"**Copied to**: `{dest_file}`  \n"
        f"**Detected**: {human_ts}  \n"
        f"**Size**: {file_size:,} bytes  \n\n"
        "## Next Steps\n\n"
        "- [ ] Review file content\n"
        "- [ ] Classify and prioritise\n"
        "- [ ] Execute or delegate\n"
    )
    path.write_text(content, encoding="utf-8")


def _append_audit_log(
    *,
    log_dir: Path,
    item_id: str,
    src_path: Path,
    dest_file: Path,
    meta_path: Path,
    timestamp: datetime,
    dry_run: bool,
) -> None:
    """Append one entry to the daily JSON audit log.

    The log file is ``Logs/YYYY-MM-DD.json`` and holds a JSON array.
    Each entry follows the FR-038 schema subset relevant to file detection.
    """
    log_file = log_dir / timestamp.strftime("%Y-%m-%d.json")
    prefix = "[DRY_RUN] " if dry_run else ""

    entry: dict[str, Any] = {
        "timestamp": timestamp.isoformat(),
        "actor": "filesystem-watcher",
        "action": f"{prefix}file_detected",
        "item_id": item_id,
        "from_state": "drop_folder",
        "to_state": "needs_action",
        "outcome": "dry_run" if dry_run else "success",
        "dry_run": dry_run,
        "details": {
            "source_file": str(src_path),
            "copied_to": str(dest_file) if not dry_run else None,
            "metadata_file": str(meta_path) if not dry_run else None,
        },
    }

    # Read existing entries (or start fresh).
    entries: list[dict[str, Any]] = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        except (json.JSONDecodeError, OSError):
            entries = []

    entries.append(entry)
    log_file.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.debug("Audit log updated: %s", log_file)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def _make_observer(watch_path: Path) -> Observer | PollingObserver:
    """Return the best available observer for *watch_path*.

    On Linux paths backed by Windows NTFS (WSL2 ``/mnt/`` mounts),
    ``inotify`` does not fire events.  We probe by briefly starting the
    native observer against the target directory and falling back to
    ``PollingObserver`` when the probe fails.
    """
    import threading

    probe_fired = threading.Event()

    class _Probe(FileSystemEventHandler):
        def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
            probe_fired.set()

    probe_file = watch_path / ".watcher_probe"
    probe_obs = Observer()
    probe_obs.schedule(_Probe(), str(watch_path), recursive=False)
    probe_obs.start()
    try:
        probe_file.write_text("probe", encoding="utf-8")
        probe_fired.wait(timeout=1.0)
    finally:
        try:
            probe_file.unlink(missing_ok=True)
        except OSError:
            pass
        probe_obs.stop()
        probe_obs.join(timeout=2)

    if probe_fired.is_set():
        logger.debug("inotify works on '%s' — using native Observer", watch_path)
        return Observer()

    logger.warning(
        "inotify not supported for '%s' (WSL2/NTFS?) — falling back to "
        "PollingObserver (poll_interval=1s)",
        watch_path,
    )
    return PollingObserver(timeout=1)


def _default_config() -> dict[str, Any]:
    """Build a default config from environment variables."""
    vault_root = os.getenv("VAULT_ROOT", str(Path.cwd()))
    return {
        "watcher": {
            "name": "drop-folder",
            "type": "filesystem",
            "enabled": True,
            "vault_root": vault_root,
            "watch_path": os.getenv("WATCH_PATH", "drop_folder"),
            "needs_action_path": os.getenv("NEEDS_ACTION_PATH", "Needs_Action"),
            "stability_seconds": float(os.getenv("STABILITY_SECONDS", "2.0")),
            "polling_interval_seconds": 1,
        }
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    cfg = _default_config()
    dry = _resolve_dry_run()

    watcher = FilesystemWatcher(cfg)
    vault = Path(cfg["watcher"]["vault_root"])
    inbox = vault / cfg["watcher"]["needs_action_path"]

    logger.info(
        "Starting FilesystemWatcher | watch=%s | dest=%s | dry_run=%s",
        cfg["watcher"]["watch_path"],
        cfg["watcher"]["needs_action_path"],
        dry,
    )

    watcher.run(inbox, dry_run=dry)
