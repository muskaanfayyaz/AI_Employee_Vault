"""Audit logger: append-only JSON log writer with redaction (T012)."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from src.models.log_entry import LogEntry

_log = logging.getLogger(__name__)

# fcntl is Unix-only; Windows falls back to a no-op context manager.
try:
    import fcntl as _fcntl
    _HAVE_FCNTL = True
except ImportError:
    _HAVE_FCNTL = False


class AuditLogger:
    """Append-only audit log writer.

    Writes ``LogEntry`` objects to ``Logs/YYYY-MM-DD.json`` as a JSON
    array. Each call to ``log()`` appends one entry. Redaction is
    applied to ``details`` string values before writing.

    File writes are protected by an exclusive ``fcntl.flock`` lock so
    concurrent agents cannot corrupt the log (S-02 fix).
    """

    def __init__(self, logs_dir: Path) -> None:
        self._logs_dir = Path(logs_dir)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    def log(self, entry: LogEntry) -> Path:
        """Validate, redact, and append *entry* to the daily log file."""
        entry.validate()
        raw = entry.to_dict()
        raw["details"] = {
            k: redact(v) if isinstance(v, str) else v
            for k, v in (raw.get("details") or {}).items()
        }

        timestamp = datetime.fromisoformat(entry.timestamp)
        log_file = self._logs_dir / timestamp.strftime("%Y-%m-%d.json")
        lock_file = log_file.with_suffix(".json.lock")

        with open(lock_file, "w") as lf:
            if _HAVE_FCNTL:
                _fcntl.flock(lf, _fcntl.LOCK_EX)
            try:
                entries: list[dict] = []
                if log_file.exists():
                    try:
                        entries = json.loads(log_file.read_text(encoding="utf-8"))
                        if not isinstance(entries, list):
                            entries = []
                    except (json.JSONDecodeError, OSError):
                        entries = []

                entries.append(raw)
                log_file.write_text(
                    json.dumps(entries, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            finally:
                if _HAVE_FCNTL:
                    _fcntl.flock(lf, _fcntl.LOCK_UN)

        _log.debug("Logged: %s → %s", entry.action, log_file.name)
        return log_file


def redact(text: str) -> str:
    """Mask sensitive patterns in *text*.

    - Email addresses → ``j***@example.com``
    - Financial amounts → ``$***``
    - 16-digit card numbers → ``****``
    """
    # Email masking: keep first char + domain
    text = re.sub(
        r"\b([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b",
        r"\1***\2",
        text,
    )
    # Currency amounts
    text = re.sub(r"\$[\d,]+(?:\.\d{2})?", "$***", text)
    # 16-digit card numbers
    text = re.sub(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "****", text)
    return text
