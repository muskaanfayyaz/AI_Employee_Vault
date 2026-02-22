"""Vault folder state machine with atomic moves (T010).

Encodes the FR-006 legal transition table and performs atomic
``os.rename()`` moves between vault folders.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# FR-006 legal transitions: from_folder → {allowed to_folders}
VALID_TRANSITIONS: dict[str, set[str]] = {
    "Inbox":            {"Needs_Action", "Errors"},
    "Needs_Action":     {"Plans", "In_Progress", "Errors"},
    "Plans":            {"In_Progress", "Errors"},
    "In_Progress":      {"Pending_Approval", "Done", "Errors", "Needs_Action"},
    "Pending_Approval": {"Approved", "Rejected"},
    "Approved":         {"In_Progress"},
    "Rejected":         {"Needs_Action", "Done"},
    "Done":             set(),
    "Errors":           {"Needs_Action"},
    "drop_folder":      {"Needs_Action"},
}


class InvalidTransitionError(Exception):
    """Raised when an illegal vault state transition is attempted."""


def move(
    item_path: Path,
    from_folder: str,
    to_folder: str,
    *,
    dry_run: bool = False,
) -> Path:
    """Move *item_path* from *from_folder* to *to_folder*.

    Parameters
    ----------
    item_path:
        Absolute path of the file to move.
    from_folder:
        Name of the source vault folder (e.g. ``"Needs_Action"``).
    to_folder:
        Name of the destination vault folder (e.g. ``"Done"``).
    dry_run:
        When ``True``, logs the intended move but does not execute it.

    Returns
    -------
    Path
        Absolute path of the file at its new location (or its current
        location in dry-run mode).

    Raises
    ------
    InvalidTransitionError
        When the requested transition is not in the legal table.
    FileNotFoundError
        When *item_path* does not exist (and not dry-run).
    """
    allowed = VALID_TRANSITIONS.get(from_folder)
    if allowed is None:
        raise InvalidTransitionError(
            f"Unknown source folder: {from_folder!r}. "
            f"Valid folders: {list(VALID_TRANSITIONS)}"
        )
    if to_folder not in allowed:
        raise InvalidTransitionError(
            f"Illegal transition: {from_folder!r} → {to_folder!r}. "
            f"Allowed destinations: {sorted(allowed)}"
        )

    dest_dir = item_path.parent.parent / to_folder
    dest_path = dest_dir / item_path.name

    if dry_run:
        logger.info(
            "[DRY_RUN] Would move: %s → %s/%s",
            item_path.name, to_folder, item_path.name,
        )
        return dest_path

    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        base = item_path.stem
        suffix = item_path.suffix
        dest_path = dest_dir / f"{base}-{os.urandom(4).hex()}{suffix}"

    os.rename(str(item_path), str(dest_path))
    logger.info("Moved: %s → %s/%s", item_path.name, to_folder, dest_path.name)
    return dest_path
