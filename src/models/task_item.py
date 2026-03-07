"""Task Item entity with YAML front-matter parse/write (T007)."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_VALID_TYPES = {"file", "email", "message", "social", "social_post", "erp", "audit"}
_VALID_SOURCES = {"filesystem", "gmail", "whatsapp", "odoo", "ralph_wiggum", "linkedin", "manual", "drop_folder"}
_VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
_VALID_STATUSES = {
    "inbox", "needs_action", "planned", "in_progress",
    "pending_approval", "approved", "rejected", "done", "error",
}
_VALID_CLASSIFICATIONS = {"local_only", "syncable", "redacted_summary"}


@dataclass
class TaskItem:
    id: str
    type: str
    source: str
    priority: str
    status: str
    requires_approval: bool = False
    classification: str = "local_only"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    body: str = ""

    # ── validation ────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self.type not in _VALID_TYPES:
            raise ValueError(f"Invalid type: {self.type!r}. Must be one of {_VALID_TYPES}")
        if self.source not in _VALID_SOURCES:
            raise ValueError(f"Invalid source: {self.source!r}")
        if self.priority not in _VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {self.priority!r}")
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status: {self.status!r}")
        if self.classification not in _VALID_CLASSIFICATIONS:
            raise ValueError(f"Invalid classification: {self.classification!r}")

    # ── serialization ─────────────────────────────────────────────────

    def to_markdown(self) -> str:
        tags_str = "[" + ", ".join(self.tags) + "]"
        platforms_line = (
            f"platforms: [{', '.join(self.platforms)}]\n" if self.platforms else ""
        )
        fm = (
            "---\n"
            f"id: {self.id}\n"
            f"type: {self.type}\n"
            f"source: {self.source}\n"
            f"priority: {self.priority}\n"
            f"status: {self.status}\n"
            f"requires_approval: {str(self.requires_approval).lower()}\n"
            f"classification: {self.classification}\n"
            f"created_at: {self.created_at}\n"
            f"updated_at: {self.updated_at}\n"
            f"tags: {tags_str}\n"
            + platforms_line +
            "---\n"
        )
        return fm + ("\n" + self.body if self.body else "")

    def to_file(self, path: Path) -> None:
        path.write_text(self.to_markdown(), encoding="utf-8")

    def update_frontmatter(self, **fields: Any) -> None:
        """Update mutable front-matter fields (created_at is immutable)."""
        immutable = {"id", "created_at"}
        for key, val in fields.items():
            if key in immutable:
                raise ValueError(f"Field {key!r} is immutable")
            if hasattr(self, key):
                setattr(self, key, val)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self._validate()

    # ── parsing ───────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: Path) -> "TaskItem":
        text = path.read_text(encoding="utf-8")
        return cls.from_markdown(text)

    @classmethod
    def from_markdown(cls, text: str) -> "TaskItem":
        fm, body = _split_front_matter(text)
        raw = _parse_yaml_simple(fm)

        def _bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            return str(v).lower() in ("true", "1", "yes")

        def _list(v: Any) -> list[str]:
            if isinstance(v, list):
                return v
            s = str(v).strip("[]")
            return [x.strip() for x in s.split(",") if x.strip()] if s else []

        # Accept both `platform: linkedin` (singular) and `platforms: [linkedin]` (plural).
        platforms_raw = raw.get("platforms", [])
        if not platforms_raw and "platform" in raw:
            platforms_raw = [raw["platform"]]

        return cls(
            id=raw.get("id", str(uuid.uuid4())),
            type=raw.get("type", "file"),
            source=raw.get("source", "filesystem"),
            priority=raw.get("priority", "medium"),
            status=raw.get("status", "needs_action"),
            requires_approval=_bool(raw.get("requires_approval", False)),
            classification=raw.get("classification", "local_only"),
            created_at=raw.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=raw.get("updated_at", datetime.now(timezone.utc).isoformat()),
            tags=_list(raw.get("tags", [])),
            platforms=_list(platforms_raw),
            body=body,
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _split_front_matter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    try:
        end = text.index("---", 3)
        return text[3:end].strip(), text[end + 3:].strip()
    except ValueError:
        return "", text


def _parse_yaml_simple(block: str) -> dict[str, Any]:
    """Minimal key:value YAML parser (no multi-line, no anchors)."""
    result: dict[str, Any] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, raw_val = line.partition(":")
            val = raw_val.strip().strip('"').strip("'")
            result[key.strip()] = val
    return result
