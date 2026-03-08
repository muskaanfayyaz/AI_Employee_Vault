"""Nightly vault backup — Platinum Tier (run by PM2 cron at 02:00 UTC).

Creates a timestamped ``tar.gz`` snapshot of the vault in
``BACKUP_LOCAL_PATH`` (default ``/backups/vault``), then optionally
syncs snapshots to a cloud storage remote via ``rclone``.

Retention: snapshots older than ``BACKUP_RETENTION_DAYS`` are deleted.

Usage (standalone / PM2 entry point)::

    python -m src.sync.backup
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_BACKUP_PATH = Path(os.getenv("BACKUP_LOCAL_PATH", "/backups/vault"))
_DEFAULT_RETENTION = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
_RCLONE_REMOTE = os.getenv("RCLONE_REMOTE", "").strip()

# Directories/patterns to exclude from the snapshot (relative to vault root).
_EXCLUDE_PATTERNS = [
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".Dashboard.lock",
    "*.tmp",
    ".env",
    ".env.*",
]


def create_snapshot(vault_root: Path, backup_dir: Path) -> Path | None:
    """Create a ``vault-YYYY-MM-DD.tar.gz`` snapshot in *backup_dir*.

    Returns the snapshot path on success, ``None`` on failure.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_name = f"vault-{ts}.tar.gz"
    snapshot_path = backup_dir / snapshot_name

    if snapshot_path.exists():
        logger.info("Snapshot already exists for today: %s — skipping", snapshot_name)
        return snapshot_path

    logger.info("Creating vault snapshot: %s", snapshot_path)

    try:
        with tarfile.open(snapshot_path, "w:gz") as tar:
            for item in vault_root.iterdir():
                if _is_excluded(item):
                    continue
                tar.add(item, arcname=item.name)
        logger.info("Snapshot created: %s (%.1f MB)", snapshot_name, snapshot_path.stat().st_size / 1e6)
        return snapshot_path
    except Exception as exc:
        logger.error("Snapshot creation failed: %s", exc)
        if snapshot_path.exists():
            snapshot_path.unlink(missing_ok=True)
        return None


def prune_old_snapshots(backup_dir: Path, retention_days: int) -> int:
    """Delete snapshots older than *retention_days*.  Returns count removed."""
    if not backup_dir.exists():
        return 0
    import time
    cutoff = time.time() - retention_days * 86400
    removed = 0
    for f in backup_dir.glob("vault-*.tar.gz"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            logger.info("Pruned old snapshot: %s", f.name)
            removed += 1
    return removed


def sync_to_remote(backup_dir: Path, remote: str) -> bool:
    """Sync *backup_dir* to *remote* via ``rclone``.  Returns ``True`` on success."""
    if not remote:
        return True  # nothing configured — treat as success
    try:
        result = subprocess.run(
            ["rclone", "sync", str(backup_dir), remote, "--progress"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            logger.info("rclone sync to %s succeeded", remote)
            return True
        logger.error("rclone sync failed: %s", result.stderr[:400])
        return False
    except FileNotFoundError:
        logger.warning("rclone not installed — skipping off-VM backup")
        return False
    except subprocess.TimeoutExpired:
        logger.error("rclone sync timed out after 5 minutes")
        return False


def _is_excluded(path: Path) -> bool:
    for pattern in _EXCLUDE_PATTERNS:
        if path.name == pattern or path.match(pattern):
            return True
    return False


def run_backup(
    vault_root: Path,
    backup_dir: Path = _DEFAULT_BACKUP_PATH,
    retention_days: int = _DEFAULT_RETENTION,
    rclone_remote: str = _RCLONE_REMOTE,
) -> bool:
    """Run the full backup cycle.  Returns ``True`` on overall success."""
    logger.info(
        "Backup started | vault=%s | dest=%s | retention=%dd | remote=%s",
        vault_root, backup_dir, retention_days, rclone_remote or "(none)",
    )

    snapshot = create_snapshot(vault_root, backup_dir)
    if snapshot is None:
        return False

    pruned = prune_old_snapshots(backup_dir, retention_days)
    if pruned:
        logger.info("Pruned %d old snapshot(s)", pruned)

    remote_ok = sync_to_remote(backup_dir, rclone_remote)
    logger.info("Backup complete | remote_sync=%s", "OK" if remote_ok else "SKIP/FAIL")
    return True


# ---------------------------------------------------------------------------
# Standalone entry point (PM2 backup process)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv  # type: ignore[import]

    _env_path = Path.home() / ".ai-employee.env"
    if not _env_path.exists():
        _env_path = Path.cwd() / ".env"
    load_dotenv(_env_path, override=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    _vault = Path(os.getenv("VAULT_ROOT", str(Path.cwd()))).resolve()
    _backup_enabled = os.getenv("BACKUP_ENABLED", "true").lower() in ("1", "true", "yes")

    if not _backup_enabled:
        logger.info("BACKUP_ENABLED=false — skipping.")
        sys.exit(0)

    ok = run_backup(_vault)
    sys.exit(0 if ok else 1)
