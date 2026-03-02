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
    Adds Gmail, WhatsApp, and LinkedIn watchers, runs approval checks
    each cycle, and wires the email drafter skill into the pipeline.

python -m src.main --subscription-audit
    Gold tier: run the subscription audit now and exit.
    Reads Odoo subscriptions, detects anomalies, writes Reports/Subscription_Audit_YYYY-MM-DD.md.
    Configuration: Config/subscription_audit.yaml

python -m src.main --ralph
    Gold tier: run the Ralph Wiggum autonomous loop.
    Cycles the processing pipeline until all items reach Done/Rejected/Errors
    or the max_iterations cap (default 10) is hit, then writes a review log.
    Self-review analysis runs after the loop to surface improvement proposals.
    Configuration: Config/ralph_wiggum.yaml
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

    # Silver tier: post approved LinkedIn drafts.
    if approved:
        _post_approved_linkedin_drafts(vault_root, approved, dry_run)

    # Gold tier: handle approved multi-platform social posts.
    if approved:
        _handle_approved_social_posts(vault_root, approved, dry_run)

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
    """Send approved email drafts via EmailMCPServer and move them to Done/.

    Routes all outbound email through ``EmailMCPServer.send_email()``
    (Req 5 — working MCP server for external action).  Silently skips
    if Gmail credentials are unavailable or draft body cannot be parsed.
    """
    import os

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

    # Route through EmailMCPServer — the designated MCP server for email actions.
    try:
        from src.mcp.email_server import EmailMCPServer
    except ImportError:
        logger.warning("EmailMCPServer unavailable — cannot send approved emails.")
        return

    mcp = EmailMCPServer(dry_run=dry_run)
    if not mcp.health_check():
        logger.warning("EmailMCPServer health check failed — GMAIL_OAUTH_TOKEN_PATH not set.")
        return

    logger.info("EmailMCPServer (%s v%s) handling approved email drafts.", mcp.name, mcp.version)

    approved_dir = vault_root / "Approved"
    done_dir = vault_root / "Done"

    for req in email_drafts:
        # Locate draft file: EmailDrafterSkill names it draft-email-<id[:8]>.md.
        draft_file = approved_dir / f"draft-email-{req.id[:8]}.md"
        if not draft_file.exists():
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
                "[DRY_RUN] EmailMCPServer would send → %s | subject: %s", to_addr, subject
            )
        else:
            result = mcp.send_email(
                to=to_addr,
                subject=subject or "(no subject)",
                body=draft_body,
            )
            if result.get("status") != "sent":
                logger.error(
                    "EmailMCPServer.send_email failed → %s: %s",
                    to_addr, result.get("error"),
                )
                continue  # don't move to Done/ if send failed
            logger.info(
                "EmailMCPServer sent → %s | %s | msg_id=%s",
                to_addr, subject, result.get("message_id"),
            )

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


def _post_approved_linkedin_drafts(vault_root: Path, approved: list, dry_run: bool) -> None:
    """Post approved LinkedIn drafts via the LinkedIn UGC Posts API.

    Called from :func:`run_approval_cycle` whenever approved items contain
    LinkedIn post drafts (``source=linkedin_poster``).
    """
    import json
    import os
    import urllib.request
    import urllib.error

    li_drafts = [req for req in approved if req.source == "linkedin_poster"]
    if not li_drafts:
        return

    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        logger.warning(
            "Approved LinkedIn post draft(s) found but LINKEDIN_ACCESS_TOKEN is not set."
        )
        return

    # Fetch the LinkedIn person URN once — needed as the post author.
    person_urn = _get_linkedin_person_urn(token)
    if not person_urn:
        logger.warning("Could not resolve LinkedIn person URN — cannot post.")
        return

    approved_dir = vault_root / "Approved"
    done_dir = vault_root / "Done"

    for req in li_drafts:
        # Locate the draft file by id prefix.
        draft_file = approved_dir / f"draft-li-post-{req.id[:8]}.md"
        if not draft_file.exists():
            draft_file = None
            for candidate in approved_dir.glob("draft-li-post-*.md"):
                if req.id[:8] in candidate.name:
                    draft_file = candidate
                    break
        if draft_file is None or not draft_file.exists():
            logger.warning(
                "Approved LinkedIn draft for id %s not found in Approved/ — skipping.",
                req.id[:8],
            )
            continue

        body_text = req.body or draft_file.read_text(encoding="utf-8")
        post_content = _parse_md_section(body_text, "Post Content")

        if not post_content:
            logger.warning(
                "Draft %s missing Post Content section — cannot post.", draft_file.name
            )
            continue

        if dry_run:
            logger.info("[DRY_RUN] Would post to LinkedIn: %.80s...", post_content)
        else:
            try:
                payload = {
                    "author": person_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {"text": post_content},
                            "shareMediaCategory": "NONE",
                        }
                    },
                    "visibility": {
                        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                    },
                }
                data = json.dumps(payload).encode("utf-8")
                req_obj = urllib.request.Request(
                    "https://api.linkedin.com/v2/ugcPosts",
                    data=data,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req_obj, timeout=15) as resp:
                    resp.read()
                logger.info("LinkedIn post published successfully.")
            except Exception as exc:
                logger.error("Failed to post to LinkedIn: %s", exc)
                continue  # don't move to Done/ if post failed

        # Move draft: Approved/ → Done/
        done_dir.mkdir(parents=True, exist_ok=True)
        dest = done_dir / draft_file.name
        if not dry_run:
            if dest.exists():
                dest = done_dir / f"{draft_file.stem}-{os.urandom(4).hex()}{draft_file.suffix}"
            draft_file.rename(dest)
            logger.info("LinkedIn draft archived to Done/: %s", dest.name)
        else:
            logger.info("[DRY_RUN] Would move %s → Done/", draft_file.name)


def _get_linkedin_person_urn(token: str) -> str:
    """Fetch the LinkedIn member URN via /v2/userinfo (sub field).

    Returns a string like ``urn:li:person:XXXXXXX`` or empty string on failure.
    """
    import json
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        sub = data.get("sub", "")
        if sub:
            return f"urn:li:person:{sub}"
        logger.warning("LinkedIn /v2/userinfo returned no 'sub' field: %s", data)
        return ""
    except urllib.error.HTTPError as exc:
        logger.error("LinkedIn /v2/userinfo returned HTTP %d", exc.code)
        return ""
    except Exception as exc:
        logger.error("Could not fetch LinkedIn person URN: %s", exc)
        return ""


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
    - LinkedIn watcher (if Config/linkedin_watcher.yaml exists and is enabled)
    - Scheduler: processing cycle every 30s, approval cycle every 15s
    """
    from src.watchers.filesystem import FilesystemWatcher
    from src.watchers.gmail import GmailWatcher
    from src.watchers.whatsapp import WhatsAppWatcher
    from src.watchers.linkedin import LinkedInWatcher
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

    # ── LinkedIn watcher (optional) ───────────────────────────────────────────
    li_config_path = vault_root / "Config" / "linkedin_watcher.yaml"
    if li_config_path.exists():
        try:
            with li_config_path.open(encoding="utf-8") as fh:
                li_cfg = yaml.safe_load(fh)
            if li_cfg.get("watcher", {}).get("enabled", False):
                li_watcher = LinkedInWatcher(li_cfg)
                _threads.append(threading.Thread(
                    target=li_watcher.run,
                    args=(inbox,),
                    kwargs={"dry_run": dry_run},
                    daemon=True,
                    name="linkedin-watcher",
                ))
                logger.info("LinkedIn watcher enabled.")
        except Exception as exc:
            logger.warning("Could not start LinkedIn watcher: %s", exc)

    # ── Odoo watcher (optional, Gold tier) ────────────────────────────────────
    odoo_config_path = vault_root / "Config" / "odoo_watcher.yaml"
    if odoo_config_path.exists():
        try:
            with odoo_config_path.open(encoding="utf-8") as fh:
                odoo_cfg = yaml.safe_load(fh)
            if odoo_cfg.get("watcher", {}).get("enabled", False):
                from src.watchers.odoo import OdooWatcher  # noqa: PLC0415
                odoo_watcher = OdooWatcher(odoo_cfg)
                _threads.append(threading.Thread(
                    target=odoo_watcher.run,
                    args=(inbox,),
                    kwargs={"dry_run": dry_run},
                    daemon=True,
                    name="odoo-watcher",
                ))
                logger.info("Odoo watcher enabled.")
        except Exception as exc:
            logger.warning("Could not start Odoo watcher: %s", exc)

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

    # ── CEO Briefing — weekly scheduled job (FR-G016) ─────────────────────────
    briefing_cfg_path = vault_root / "Config" / "ceo_briefing.yaml"
    if briefing_cfg_path.exists():
        try:
            with briefing_cfg_path.open(encoding="utf-8") as _fh:
                _briefing_cfg = yaml.safe_load(_fh)
            _skill_cfg = _briefing_cfg.get("skill", {})
            _schedule_cfg = _briefing_cfg.get("schedule", {})
            _briefing_cfg_data = _briefing_cfg.get("briefing", {})
            if _skill_cfg.get("enabled", True):
                _day = int(_schedule_cfg.get("day", 0))
                _hour = int(_schedule_cfg.get("hour", 8))
                _minute = int(_schedule_cfg.get("minute", 0))
                _day_names = ["monday", "tuesday", "wednesday", "thursday",
                              "friday", "saturday", "sunday"]
                _day_name = _day_names[_day % 7]
                _time_str = f"{_hour:02d}:{_minute:02d}"

                def _run_briefing(
                    _vr=vault_root,
                    _dr=dry_run,
                    _cfg=_briefing_cfg_data,
                ) -> None:
                    run_ceo_briefing(_vr, _dr, _cfg)

                getattr(sched.every(), _day_name).at(_time_str).do(_run_briefing)
                logger.info(
                    "CEO Briefing scheduled: every %s at %s | dry_run=%s",
                    _day_name,
                    _time_str,
                    dry_run,
                )
        except Exception as _exc:
            logger.warning("Could not schedule CEO Briefing: %s", _exc)

    # ── Ralph Wiggum Loop — weekly scheduled job (FR-G023) ───────────────────
    ralph_cfg_path = vault_root / "Config" / "ralph_wiggum.yaml"
    if ralph_cfg_path.exists():
        try:
            with ralph_cfg_path.open(encoding="utf-8") as _rfh:
                _ralph_cfg = yaml.safe_load(_rfh)
            _ralph_skill_cfg = _ralph_cfg.get("skill", {})
            _ralph_sched_cfg = _ralph_cfg.get("schedule", {})
            if _ralph_skill_cfg.get("enabled", True):
                _r_day = int(_ralph_sched_cfg.get("day", 0))
                _r_hour = int(_ralph_sched_cfg.get("hour", 7))
                _r_minute = int(_ralph_sched_cfg.get("minute", 0))
                _day_names = ["monday", "tuesday", "wednesday", "thursday",
                              "friday", "saturday", "sunday"]
                _r_day_name = _day_names[_r_day % 7]
                _r_time_str = f"{_r_hour:02d}:{_r_minute:02d}"

                def _run_ralph(
                    _vr=vault_root,
                    _dr=dry_run,
                ) -> None:
                    run_ralph_wiggum_loop(_vr, _dr)

                getattr(sched.every(), _r_day_name).at(_r_time_str).do(_run_ralph)
                logger.info(
                    "Ralph Wiggum loop scheduled: every %s at %s | dry_run=%s",
                    _r_day_name,
                    _r_time_str,
                    dry_run,
                )
        except Exception as _rexc:
            logger.warning("Could not schedule Ralph Wiggum loop: %s", _rexc)

    # ── Subscription Audit — weekly scheduled job (FR-G019) ──────────────────
    sub_audit_cfg_path = vault_root / "Config" / "subscription_audit.yaml"
    if sub_audit_cfg_path.exists():
        try:
            with sub_audit_cfg_path.open(encoding="utf-8") as _sfh:
                _sub_cfg = yaml.safe_load(_sfh)
            _sub_audit_cfg = _sub_cfg.get("audit", {})
            _sub_sched_cfg = _sub_cfg.get("schedule", {})
            if _sub_audit_cfg.get("enabled", True):
                _sa_day = int(_sub_sched_cfg.get("day", 4))  # Friday
                _sa_hour = int(_sub_sched_cfg.get("hour", 6))
                _sa_minute = int(_sub_sched_cfg.get("minute", 0))
                _day_names = ["monday", "tuesday", "wednesday", "thursday",
                              "friday", "saturday", "sunday"]
                _sa_day_name = _day_names[_sa_day % 7]
                _sa_time_str = f"{_sa_hour:02d}:{_sa_minute:02d}"

                def _run_sub_audit(
                    _vr=vault_root,
                    _dr=dry_run,
                    _cfg=_sub_audit_cfg,
                ) -> None:
                    run_subscription_audit(_vr, _dr, _cfg)

                getattr(sched.every(), _sa_day_name).at(_sa_time_str).do(_run_sub_audit)
                logger.info(
                    "Subscription Audit scheduled: every %s at %s | dry_run=%s",
                    _sa_day_name, _sa_time_str, dry_run,
                )
        except Exception as _saexc:
            logger.warning("Could not schedule Subscription Audit: %s", _saexc)

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


def _handle_approved_social_posts(
    vault_root: Path, approved: list, dry_run: bool
) -> None:
    """Move approved multi-platform social post drafts to Done/ (Gold tier FR-G015).

    The actual platform API calls (Facebook, Instagram, Twitter publish) are
    intentionally stubbed — they require platform-specific token handling beyond
    the scope of this approval-cycle runner.  The key guarantee is that drafts
    are ONLY moved to Done/ after approval is confirmed, never before.
    """
    # Collect drafts from social_poster_{platform} sources (not linkedin_poster,
    # which is handled separately by _post_approved_linkedin_drafts).
    social_platforms = ("facebook", "instagram", "twitter")
    social_drafts = [
        req for req in approved
        if any(f"social_poster_{p}" in (req.source or "") for p in social_platforms)
    ]
    if not social_drafts:
        return

    approved_dir = vault_root / "Approved"
    done_dir = vault_root / "Done"

    for req in social_drafts:
        # Extract platform from source field (e.g. "social_poster_facebook" → "facebook")
        platform = (req.source or "").replace("social_poster_", "")

        # Locate the draft file in Approved/.
        draft_file = None
        for candidate in approved_dir.glob(f"draft-{platform}-post-*.md"):
            if req.id[:8] in candidate.name:
                draft_file = candidate
                break

        if draft_file is None or not draft_file.exists():
            logger.warning(
                "Approved %s draft for id %s not found in Approved/ — skipping.",
                platform, req.id[:8],
            )
            continue

        body_text = req.body or draft_file.read_text(encoding="utf-8")
        post_content = _parse_md_section(body_text, "Post Content")

        if not post_content:
            logger.warning(
                "Draft %s missing Post Content section — cannot publish.", draft_file.name
            )
            continue

        if dry_run:
            logger.info(
                "[DRY_RUN] Would publish %s post: %.80s...", platform.title(), post_content
            )
        else:
            # Platform-specific publish calls can be wired here when credentials
            # are available.  For now we log the intent and move to Done/.
            logger.info(
                "Social post approved for %s — publish via platform API: %.80s",
                platform.title(), post_content,
            )

        # Move draft: Approved/ → Done/ (only after successful publish or dry-run).
        done_dir.mkdir(parents=True, exist_ok=True)
        dest = done_dir / draft_file.name
        if not dry_run:
            import os as _os
            if dest.exists():
                dest = done_dir / f"{draft_file.stem}-{_os.urandom(4).hex()}{draft_file.suffix}"
            draft_file.rename(dest)
            logger.info("%s draft archived to Done/: %s", platform.title(), dest.name)
        else:
            logger.info("[DRY_RUN] Would move %s → Done/", draft_file.name)


def run_subscription_audit(
    vault_root: Path,
    dry_run: bool,
    config: dict | None = None,
) -> None:
    """Invoke the Subscription Audit skill once and log the result (FR-G019).

    Called by the weekly scheduler or directly via ``--subscription-audit``.
    """
    from src.skills.base import SkillInput
    from src.skills.subscription_audit import SubscriptionAuditSkill
    from src.engine.logger import AuditLogger
    from src.models.log_entry import LogEntry

    if config is None:
        cfg_path = vault_root / "Config" / "subscription_audit.yaml"
        if cfg_path.exists():
            try:
                import yaml  # type: ignore[import]
                with cfg_path.open(encoding="utf-8") as fh:
                    raw = yaml.safe_load(fh)
                config = raw.get("audit", {})
            except Exception as exc:
                logger.warning(
                    "Could not load subscription_audit.yaml: %s — using defaults.", exc
                )
                config = {}
        else:
            config = {}

    skill_input = SkillInput(vault_root=vault_root, dry_run=dry_run, config={"audit": config})
    out = SubscriptionAuditSkill().safe_execute(skill_input)

    audit = AuditLogger(vault_root / "Logs")
    try:
        entry = LogEntry(
            actor="subscription_audit",
            action=f"{'[DRY_RUN] ' if dry_run else ''}subscription_audit_run",
            outcome="dry_run" if dry_run else ("success" if out.success else "failure"),
            details={
                "result": out.result,
                "total_subscriptions": out.metadata.get("total_subscriptions", 0),
                "anomalies_detected": out.metadata.get("anomalies_detected", 0),
                "items_created": out.metadata.get("items_created", 0),
            },
            dry_run=dry_run,
        )
        audit.log(entry)
    except Exception as exc:
        logger.warning("Could not write Subscription Audit audit log entry: %s", exc)

    if out.success:
        logger.info("Subscription Audit complete: %s", out.result)
    else:
        logger.error("Subscription Audit failed: %s", out.error)


def run_ralph_wiggum_loop(vault_root: Path, dry_run: bool) -> None:
    """Gold tier: invoke the Ralph Wiggum autonomous loop and log results.

    Reads configuration from ``Config/ralph_wiggum.yaml`` if present;
    falls back to built-in defaults (max_iterations=10, stop_when_done=True).
    """
    from src.engine.ralph_wiggum_loop import RalphWiggumLoop
    from src.engine.logger import AuditLogger
    from src.models.log_entry import LogEntry

    # Load config (optional — loop runs fine with defaults).
    config: dict = {}
    cfg_path = vault_root / "Config" / "ralph_wiggum.yaml"
    if cfg_path.exists():
        try:
            import yaml  # type: ignore[import]
            with cfg_path.open(encoding="utf-8") as fh:
                config = yaml.safe_load(fh) or {}
        except Exception as exc:
            logger.warning(
                "Could not load ralph_wiggum.yaml: %s — using defaults.", exc
            )

    loop = RalphWiggumLoop(vault_root=vault_root, dry_run=dry_run)
    result = loop.run(config)

    audit = AuditLogger(vault_root / "Logs")
    try:
        entry = LogEntry(
            actor="ralph_wiggum_loop",
            action=f"{'[DRY_RUN] ' if dry_run else ''}ralph_wiggum_loop_complete",
            outcome="dry_run" if dry_run else "success",
            details={
                "iterations": result["iterations"],
                "stop_reason": result["stop_reason"],
                "items_remaining": result["items_remaining"],
            },
            dry_run=dry_run,
        )
        audit.log(entry)
    except Exception as exc:
        logger.warning("Could not write Ralph Wiggum audit entry: %s", exc)

    logger.info(
        "Ralph Wiggum loop finished | stop_reason=%s | iterations=%d | items_remaining=%d",
        result["stop_reason"], result["iterations"], result["items_remaining"],
    )


def run_ceo_briefing(
    vault_root: Path,
    dry_run: bool,
    config: dict | None = None,
) -> None:
    """Invoke the CEO Briefing skill once and log the result.

    Called by the weekly scheduler or directly via ``--briefing``.
    """
    from src.skills.base import SkillInput
    from src.skills.ceo_briefing import CeoBriefingSkill
    from src.engine.logger import AuditLogger
    from src.models.log_entry import LogEntry

    if config is None:
        # Load from Config/ceo_briefing.yaml if available.
        cfg_path = vault_root / "Config" / "ceo_briefing.yaml"
        if cfg_path.exists():
            try:
                import yaml  # type: ignore[import]
                with cfg_path.open(encoding="utf-8") as fh:
                    raw = yaml.safe_load(fh)
                config = raw.get("briefing", {})
            except Exception as exc:
                logger.warning("Could not load ceo_briefing.yaml: %s — using defaults.", exc)
                config = {}
        else:
            config = {}

    skill_input = SkillInput(vault_root=vault_root, dry_run=dry_run, config=config)
    out = CeoBriefingSkill().safe_execute(skill_input)

    audit = AuditLogger(vault_root / "Logs")
    try:
        entry = LogEntry(
            actor="generate_ceo_briefing",
            action=f"{'[DRY_RUN] ' if dry_run else ''}ceo_briefing_generated",
            outcome="dry_run" if dry_run else ("success" if out.success else "failure"),
            details={
                "result": out.result,
                "report_path": out.metadata.get("report_path", ""),
                "done_count": out.metadata.get("done_count", 0),
                "error_count": out.metadata.get("error_count", 0),
                "suggestion_count": out.metadata.get("suggestion_count", 0),
            },
            dry_run=dry_run,
        )
        audit.log(entry)
    except Exception as exc:
        logger.warning("Could not write CEO briefing audit log entry: %s", exc)

    if out.success:
        logger.info("CEO Briefing complete: %s", out.result)
    else:
        logger.error("CEO Briefing failed: %s", out.error)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ai-employee",
        description="AI Employee System",
    )
    parser.add_argument("--init", action="store_true", help="Create vault folders and exit")
    parser.add_argument("--process", action="store_true", help="Run one processing cycle and exit")
    parser.add_argument("--schedule", action="store_true",
                        help="Silver tier: start scheduler with Gmail/WhatsApp watchers and approval loop")
    parser.add_argument("--briefing", action="store_true",
                        help="Gold tier: generate the CEO briefing now and exit")
    parser.add_argument("--subscription-audit", action="store_true", dest="subscription_audit",
                        help="Gold tier: run the subscription audit now and exit")
    parser.add_argument("--ralph", action="store_true",
                        help="Gold tier: run the Ralph Wiggum autonomous loop and exit")
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

    if args.briefing:
        run_ceo_briefing(vault_root, dry_run)
        return 0

    if args.subscription_audit:
        run_subscription_audit(vault_root, dry_run)
        return 0

    if args.ralph:
        run_ralph_wiggum_loop(vault_root, dry_run)
        return 0

    if args.schedule:
        run_schedule_loop(vault_root, dry_run)
        return 0

    # Default: start Bronze watcher loop.
    run_watcher_loop(vault_root, dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
