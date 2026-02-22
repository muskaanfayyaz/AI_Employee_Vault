"""AI Employee System — entry point (T018, T025, T041).

Commands
--------
python -m src.main --init
    Create all 13 vault folders and empty Dashboard.md.

python -m src.main
    Start the Bronze processing loop:
    filesystem watcher → triage → plan → execute → dashboard.

python -m src.main --process
    Run one processing cycle over Needs_Action/ and exit.

python -m src.main --dry-run
    Force DRY_RUN mode regardless of .env setting.

python -m src.main --schedule
    Silver tier: start the scheduler alongside the filesystem watcher.
    Adds Gmail and WhatsApp watchers, runs approval checks each cycle,
    and wires the email drafter skill into the processing pipeline.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ai-employee")

# Vault folders to create on --init (FR-001).
_VAULT_FOLDERS = [
    "Inbox", "Needs_Action", "Plans", "In_Progress",
    "Pending_Approval", "Approved", "Rejected", "Done",
    "Errors", "Reports", "Logs", "Config", "Skills",
]


def _resolve_vault_root() -> Path:
    try:
        from src.config import VAULT_ROOT
        return VAULT_ROOT
    except ImportError:
        return Path(os.getenv("VAULT_ROOT", str(Path.cwd()))).resolve()


def _resolve_dry_run(force: bool = False) -> bool:
    if force:
        return True
    try:
        from src.config import DRY_RUN
        return DRY_RUN
    except ImportError:
        return os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")


def init_vault(vault_root: Path) -> None:
    """Create all vault folders and initialise Dashboard.md."""
    logger.info("Initialising vault at: %s", vault_root)
    for folder in _VAULT_FOLDERS:
        (vault_root / folder).mkdir(parents=True, exist_ok=True)
        logger.info("  ✓ %s/", folder)

    dashboard = vault_root / "Dashboard.md"
    if not dashboard.exists():
        dashboard.write_text(
            "# AI Employee Dashboard\n\n_Not yet generated. Run the system to populate._\n",
            encoding="utf-8",
        )
        logger.info("  ✓ Dashboard.md created")

    # Ensure drop_folder exists too.
    (vault_root / "drop_folder").mkdir(parents=True, exist_ok=True)
    logger.info("  ✓ drop_folder/")
    logger.info("Vault initialised — %d folders ready.", len(_VAULT_FOLDERS))


def run_approval_cycle(vault_root: Path, dry_run: bool) -> None:
    """Check for pending approvals and log stale ones.

    Called each scheduler tick when ``--schedule`` is active.
    Approved email drafts are sent via Gmail and moved to Done/.
    """
    from src.approval.manager import ApprovalManager
    from src.engine.logger import AuditLogger

    audit = AuditLogger(vault_root / "Logs")
    mgr = ApprovalManager(vault_root, audit_logger=audit, dry_run=dry_run)

    approved, rejected = mgr.check_approvals()
    stale = mgr.get_stale_approvals()

    # Silver tier: send approved email drafts via Gmail.
    if approved:
        _send_approved_email_drafts(vault_root, approved, dry_run)

    pending_dir = vault_root / "Pending_Approval"
    pending_count = len(list(pending_dir.glob("*.md"))) if pending_dir.exists() else 0

    if approved or rejected:
        logger.info(
            "Approval cycle: %d approved, %d rejected, %d stale, %d pending",
            len(approved), len(rejected), len(stale), pending_count,
        )
    elif pending_count:
        logger.info(
            "Approval cycle: %d item(s) awaiting your review in Pending_Approval/",
            pending_count,
        )
    if stale:
        logger.warning(
            "Approval cycle: %d stale approval(s) >24h — action required", len(stale)
        )


def _send_approved_email_drafts(vault_root: Path, approved: list, dry_run: bool) -> None:
    """Send approved email drafts via Gmail API and move them to Done/.

    Called from :func:`run_approval_cycle` whenever approved items contain
    email drafts (``source=email_drafter``).  Silently skips if Gmail
    credentials are unavailable or the draft body cannot be parsed.
    """
    import base64
    import os
    from email.mime.text import MIMEText

    email_drafts = [req for req in approved if req.source == "email_drafter"]
    if not email_drafts:
        return

    token_path_str = os.getenv("GMAIL_OAUTH_TOKEN_PATH", "")
    if not token_path_str or not Path(token_path_str).exists():
        logger.warning(
            "Approved email draft(s) found but GMAIL_OAUTH_TOKEN_PATH is not set or "
            "the token file does not exist — cannot send. Set the path in .env."
        )
        return

    try:
        from google.oauth2.credentials import Credentials  # type: ignore[import]
        from googleapiclient.discovery import build       # type: ignore[import]
    except ImportError:
        logger.warning("Silver deps not installed — cannot send approved emails.")
        return

    creds = Credentials.from_authorized_user_file(token_path_str)
    service = build("gmail", "v1", credentials=creds)

    approved_dir = vault_root / "Approved"
    done_dir = vault_root / "Done"

    for req in email_drafts:
        # Locate draft file: EmailDrafterSkill names it draft-email-<id[:8]>.md.
        draft_file = approved_dir / f"draft-email-{req.id[:8]}.md"
        if not draft_file.exists():
            # Fallback: scan for any file whose name contains the id prefix.
            draft_file = None
            for candidate in approved_dir.glob("draft-email-*.md"):
                if req.id[:8] in candidate.name:
                    draft_file = candidate
                    break
        if draft_file is None or not draft_file.exists():
            logger.warning(
                "Approved draft for id %s not found in Approved/ — skipping.", req.id[:8]
            )
            continue

        # Parse recipient, subject, and body from the draft file.
        # req.body may be empty if the file was moved after parsing; re-read if needed.
        body_text = req.body or draft_file.read_text(encoding="utf-8")
        to_addr = _parse_md_header(body_text, "To")
        subject = _parse_md_header(body_text, "Subject")
        draft_body = _parse_md_section(body_text, "Draft Body")

        if not to_addr or not draft_body:
            logger.warning(
                "Draft %s missing To or Draft Body content — cannot send.", draft_file.name
            )
            continue

        if dry_run:
            logger.info(
                "[DRY_RUN] Would send email → %s | subject: %s", to_addr, subject
            )
        else:
            try:
                msg = MIMEText(draft_body, "plain", "utf-8")
                msg["to"] = to_addr
                msg["subject"] = subject or "(no subject)"
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
                service.users().messages().send(
                    userId="me", body={"raw": raw}
                ).execute()
                logger.info("Email sent → %s | %s", to_addr, subject)
            except Exception as exc:
                logger.error("Failed to send email to %s: %s", to_addr, exc)
                continue  # don't move to Done/ if send failed

        # Move draft: Approved/ → Done/ (direct rename — Approved→Done is not in
        # the standard state machine, but Done is the correct terminal state here).
        done_dir.mkdir(parents=True, exist_ok=True)
        dest = done_dir / draft_file.name
        if not dry_run:
            if dest.exists():
                dest = done_dir / f"{draft_file.stem}-{os.urandom(4).hex()}{draft_file.suffix}"
            draft_file.rename(dest)
            logger.info("Draft archived to Done/: %s", dest.name)
        else:
            logger.info("[DRY_RUN] Would move %s → Done/", draft_file.name)


def _parse_md_header(text: str, header: str) -> str:
    """Extract ``**Header**: value`` from markdown text."""
    import re
    match = re.search(rf"\*\*{re.escape(header)}\*\*:\s*(.+)", text)
    return match.group(1).strip().rstrip("  ").strip() if match else ""


def _parse_md_section(text: str, section: str) -> str:
    """Extract text between ``## Section`` and the next ``##`` heading or EOF."""
    import re
    match = re.search(
        rf"## {re.escape(section)}\n\n(.*?)(?=\n## |\Z)", text, re.DOTALL
    )
    return match.group(1).strip() if match else ""


def run_processing_cycle(vault_root: Path, dry_run: bool) -> None:
    """One pass: triage → plan → execute → dashboard over Needs_Action."""
    from src.skills.base import SkillInput
    from src.skills.triage import TriageSkill
    from src.skills.planner import PlannerSkill
    from src.skills.executor import ExecutorSkill
    from src.skills.dashboard import DashboardSkill
    from src.engine.logger import AuditLogger
    from src.models.log_entry import LogEntry, ApprovalInfo

    audit = AuditLogger(vault_root / "Logs")
    skill_input_base = SkillInput(vault_root=vault_root, dry_run=dry_run)

    needs_action = vault_root / "Needs_Action"
    items = [
        f for f in needs_action.iterdir()
        if f.is_file() and f.suffix == ".md" and not f.name.endswith("-metadata.md")
    ] if needs_action.exists() else []

    if not items:
        logger.info("Needs_Action/ is empty — nothing to process.")
    else:
        logger.info("Processing %d item(s)...", len(items))

    for item_path in items:
        logger.info("--- Processing: %s ---", item_path.name)
        si = SkillInput(item_path=item_path, vault_root=vault_root, dry_run=dry_run)

        # Triage.
        out = TriageSkill().safe_execute(si)
        _log_skill(audit, "triage", out, item_path, dry_run)

        # Plan.
        out = PlannerSkill().safe_execute(si)
        _log_skill(audit, "planner", out, item_path, dry_run)

        # Execute.
        out = ExecutorSkill().safe_execute(si)
        _log_skill(audit, "executor", out, item_path, dry_run)

    # Dashboard.
    DashboardSkill().safe_execute(skill_input_base)
    logger.info("Cycle complete.")


def _log_skill(audit: "AuditLogger", skill_name: str, out: "SkillOutput",
               item_path: Path, dry_run: bool) -> None:
    from src.models.log_entry import LogEntry, ApprovalInfo
    try:
        entry = LogEntry(
            actor=skill_name,
            action=f"{'[DRY_RUN] ' if dry_run else ''}{skill_name}_executed",
            outcome="dry_run" if dry_run else ("success" if out.success else "failure"),
            details={"result": out.result, "item": item_path.name},
            dry_run=dry_run,
        )
        audit.log(entry)
    except Exception:
        pass


def run_watcher_loop(vault_root: Path, dry_run: bool) -> None:
    """Start filesystem watcher + periodic processing loop."""
    from src.watchers.filesystem import FilesystemWatcher
    import threading

    watcher_cfg = {
        "watcher": {
            "name": "drop-folder",
            "type": "filesystem",
            "enabled": True,
            "vault_root": str(vault_root),
            "watch_path": "drop_folder",
            "needs_action_path": "Needs_Action",
            "stability_seconds": float(os.getenv("STABILITY_SECONDS", "2.0")),
            "polling_interval_seconds": 1,
        }
    }

    watcher = FilesystemWatcher(watcher_cfg)
    inbox = vault_root / "Needs_Action"

    _running = True

    def _handle_signal(sig, frame):
        nonlocal _running
        logger.info("Shutdown signal received.")
        _running = False
        watcher.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    watcher_thread = threading.Thread(
        target=watcher.run, args=(inbox,), kwargs={"dry_run": dry_run}, daemon=True
    )
    watcher_thread.start()
    logger.info("Filesystem watcher started. Watching drop_folder/")
    logger.info("Press Ctrl+C to stop.")

    cycle_interval = 30  # seconds between processing cycles
    last_cycle = 0.0

    while _running:
        now = time.monotonic()
        if now - last_cycle >= cycle_interval:
            run_processing_cycle(vault_root, dry_run)
            last_cycle = now
        time.sleep(1)

    logger.info("AI Employee System stopped.")


def run_schedule_loop(vault_root: Path, dry_run: bool) -> None:
    """Silver tier: start scheduler + Gmail/WhatsApp watchers + approval loop.

    Starts:
    - Filesystem watcher (Bronze, drop_folder → Needs_Action/)
    - Gmail watcher (if Config/gmail_watcher.yaml exists and is enabled)
    - WhatsApp watcher (if Config/whatsapp_watcher.yaml exists and is enabled)
    - Scheduler: processing cycle every 30s, approval cycle every 15s
    """
    from src.watchers.filesystem import FilesystemWatcher
    from src.watchers.gmail import GmailWatcher
    from src.watchers.whatsapp import WhatsAppWatcher
    from src.engine.scheduler import Scheduler
    import threading
    import yaml  # type: ignore[import]

    _running = True
    _threads: list[threading.Thread] = []

    def _handle_signal(sig, frame):
        nonlocal _running
        logger.info("Shutdown signal received.")
        _running = False
        sched.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── filesystem watcher ────────────────────────────────────────────────────
    watcher_cfg = {
        "watcher": {
            "name": "drop-folder",
            "type": "filesystem",
            "enabled": True,
            "vault_root": str(vault_root),
            "watch_path": "drop_folder",
            "needs_action_path": "Needs_Action",
            "stability_seconds": float(os.getenv("STABILITY_SECONDS", "2.0")),
            "polling_interval_seconds": 1,
        }
    }
    fs_watcher = FilesystemWatcher(watcher_cfg)
    inbox = vault_root / "Needs_Action"
    _threads.append(threading.Thread(
        target=fs_watcher.run,
        args=(inbox,),
        kwargs={"dry_run": dry_run},
        daemon=True,
        name="fs-watcher",
    ))

    # ── Gmail watcher (optional) ──────────────────────────────────────────────
    gmail_config_path = vault_root / "Config" / "gmail_watcher.yaml"
    if gmail_config_path.exists():
        try:
            with gmail_config_path.open(encoding="utf-8") as fh:
                gmail_cfg = yaml.safe_load(fh)
            if gmail_cfg.get("watcher", {}).get("enabled", True):
                gmail_watcher = GmailWatcher(gmail_cfg)
                _threads.append(threading.Thread(
                    target=gmail_watcher.run,
                    args=(inbox,),
                    kwargs={"dry_run": dry_run},
                    daemon=True,
                    name="gmail-watcher",
                ))
                logger.info("Gmail watcher enabled.")
        except Exception as exc:
            logger.warning("Could not start Gmail watcher: %s", exc)

    # ── WhatsApp watcher (optional) ───────────────────────────────────────────
    wa_config_path = vault_root / "Config" / "whatsapp_watcher.yaml"
    if wa_config_path.exists():
        try:
            with wa_config_path.open(encoding="utf-8") as fh:
                wa_cfg = yaml.safe_load(fh)
            if wa_cfg.get("watcher", {}).get("enabled", True):
                wa_watcher = WhatsAppWatcher(wa_cfg)
                _threads.append(threading.Thread(
                    target=wa_watcher.run,
                    args=(inbox,),
                    kwargs={"dry_run": dry_run},
                    daemon=True,
                    name="whatsapp-watcher",
                ))
                logger.info("WhatsApp watcher enabled.")
        except Exception as exc:
            logger.warning("Could not start WhatsApp watcher: %s", exc)

    # ── start all watcher threads ─────────────────────────────────────────────
    for t in _threads:
        t.start()
        logger.info("Started thread: %s", t.name)

    # ── scheduler ─────────────────────────────────────────────────────────────
    sched = Scheduler(install_signal_handlers=False)  # signals handled above
    sched.add_job(
        lambda: run_processing_cycle(vault_root, dry_run),
        interval_seconds=30,
        tag="processing",
    )
    sched.add_job(
        lambda: run_approval_cycle(vault_root, dry_run),
        interval_seconds=15,
        tag="approvals",
    )
    logger.info(
        "Silver scheduler started | processing=30s | approvals=15s | dry_run=%s",
        dry_run,
    )

    sched_thread = sched.start_in_background()

    # ── main loop: wait for shutdown ──────────────────────────────────────────
    logger.info("AI Employee System running (Silver mode). Press Ctrl+C to stop.")
    while _running:
        time.sleep(1)

    logger.info("AI Employee System (Silver) stopped.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ai-employee",
        description="AI Employee System",
    )
    parser.add_argument("--init", action="store_true", help="Create vault folders and exit")
    parser.add_argument("--process", action="store_true", help="Run one processing cycle and exit")
    parser.add_argument("--schedule", action="store_true",
                        help="Silver tier: start scheduler with Gmail/WhatsApp watchers and approval loop")
    parser.add_argument("--dry-run", action="store_true", dest="force_dry_run",
                        help="Force DRY_RUN mode")
    args = parser.parse_args(argv)

    vault_root = _resolve_vault_root()
    dry_run = _resolve_dry_run(force=args.force_dry_run)

    logger.info("AI Employee System starting | vault=%s | dry_run=%s", vault_root, dry_run)

    if args.init:
        init_vault(vault_root)
        return 0

    if args.process:
        run_processing_cycle(vault_root, dry_run)
        return 0

    if args.schedule:
        run_schedule_loop(vault_root, dry_run)
        return 0

    # Default: start Bronze watcher loop.
    run_watcher_loop(vault_root, dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
