"""Integration tests for Gold Tier social media pipeline (FR-G012/FR-G015).

Coverage:
- _handle_approved_social_posts: routes twitter/facebook/instagram through SocialMCPServer
- Draft only moved to Done/ after confirmed API success
- Draft stays in Approved/ when API returns failure
- No crash when approved list has no social drafts
- No crash when draft file is missing from Approved/
- _log_social_post writes audit log entry detectable by CEO Briefing Section 8
- CEO Briefing social_events populated from log (end-to-end)
- Instagram missing image_url handled gracefully
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.approval import ApprovalRequest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def vault(tmp_path: Path) -> Path:
    for folder in ("Approved", "Done", "Logs", "Config"):
        (tmp_path / folder).mkdir()
    return tmp_path


def _social_request(platform: str, req_id: str = "abcd1234efgh5678") -> ApprovalRequest:
    """Create an approved ApprovalRequest for a social post."""
    req = ApprovalRequest(
        id=req_id,
        type="social_post",
        source=f"social_poster_{platform}",
        priority="medium",
        proposed_action=f"Publish {platform} post",
    )
    req.approve()
    return req


def _write_draft(vault: Path, platform: str, req_id: str, content: str,
                 image_url: str = "") -> Path:
    """Write a draft markdown file to Approved/ matching _handle_approved_social_posts lookup."""
    short_id = req_id[:8]
    draft_path = vault / "Approved" / f"draft-{platform}-post-{short_id}.md"
    image_section = (
        f"\n\n## Image URL\n\n{image_url}" if image_url else ""
    )
    draft_path.write_text(
        f"## Post Content\n\n{content}{image_section}\n",
        encoding="utf-8",
    )
    return draft_path


# ── Twitter routing ───────────────────────────────────────────────────────────

def test_handle_twitter_success_moves_to_done(vault):
    from src.main import _handle_approved_social_posts

    req_id = "twitter-uuid-0001"
    req = _social_request("twitter", req_id)
    _write_draft(vault, "twitter", req_id, "AI Employee is live 24/7! #AI")

    mock_result = {"tweet_id": "tw-999", "status": "sent", "error": None}
    with patch("src.mcp.social_server.SocialMCPServer.post_to_twitter",
               return_value=mock_result):
        _handle_approved_social_posts(vault, [req], dry_run=False)

    done_files = list((vault / "Done").glob("draft-twitter-post-*.md"))
    assert len(done_files) == 1
    assert not (vault / "Approved" / f"draft-twitter-post-{req_id[:8]}.md").exists()


def test_handle_twitter_failure_keeps_in_approved(vault):
    from src.main import _handle_approved_social_posts

    req_id = "twitter-uuid-0002"
    req = _social_request("twitter", req_id)
    draft = _write_draft(vault, "twitter", req_id, "Post that will fail")

    mock_result = {"tweet_id": "", "status": "failed", "error": "401 Unauthorized"}
    with patch("src.mcp.social_server.SocialMCPServer.post_to_twitter",
               return_value=mock_result):
        _handle_approved_social_posts(vault, [req], dry_run=False)

    assert draft.exists(), "Draft must stay in Approved/ when API returns failure"
    done_files = list((vault / "Done").glob("draft-twitter-post-*.md"))
    assert len(done_files) == 0


# ── Facebook routing ──────────────────────────────────────────────────────────

def test_handle_facebook_success_moves_to_done(vault):
    from src.main import _handle_approved_social_posts

    req_id = "facebook-uuid-0001"
    req = _social_request("facebook", req_id)
    _write_draft(vault, "facebook", req_id, "Check out our new product!")

    mock_result = {"post_id": "fb-42", "status": "sent", "error": None}
    with patch("src.mcp.social_server.SocialMCPServer.post_to_facebook",
               return_value=mock_result):
        _handle_approved_social_posts(vault, [req], dry_run=False)

    done_files = list((vault / "Done").glob("draft-facebook-post-*.md"))
    assert len(done_files) == 1


def test_handle_facebook_failure_keeps_in_approved(vault):
    from src.main import _handle_approved_social_posts

    req_id = "facebook-uuid-0002"
    req = _social_request("facebook", req_id)
    draft = _write_draft(vault, "facebook", req_id, "This will fail")

    mock_result = {"post_id": "", "status": "failed", "error": "HTTP 403 — Forbidden"}
    with patch("src.mcp.social_server.SocialMCPServer.post_to_facebook",
               return_value=mock_result):
        _handle_approved_social_posts(vault, [req], dry_run=False)

    assert draft.exists()
    assert len(list((vault / "Done").glob("*.md"))) == 0


# ── Instagram routing ─────────────────────────────────────────────────────────

def test_handle_instagram_success_moves_to_done(vault):
    from src.main import _handle_approved_social_posts

    req_id = "instagram-uuid-001"
    req = _social_request("instagram", req_id)
    _write_draft(vault, "instagram", req_id, "Beautiful photo caption!",
                 image_url="https://cdn.example.com/photo.jpg")

    mock_result = {"media_id": "ig-777", "status": "sent", "error": None}
    with patch("src.mcp.social_server.SocialMCPServer.post_to_instagram",
               return_value=mock_result) as mock_ig:
        _handle_approved_social_posts(vault, [req], dry_run=False)

    # Verify image_url was passed through
    call_args = mock_ig.call_args
    assert "https://cdn.example.com/photo.jpg" in call_args.args

    done_files = list((vault / "Done").glob("draft-instagram-post-*.md"))
    assert len(done_files) == 1


def test_handle_instagram_missing_image_url_graceful(vault):
    """Instagram draft without Image URL section: post_to_instagram called with empty string."""
    from src.main import _handle_approved_social_posts

    req_id = "instagram-uuid-002"
    req = _social_request("instagram", req_id)
    # Draft has no ## Image URL section
    _write_draft(vault, "instagram", req_id, "Caption without image")

    mock_result = {"media_id": "", "status": "failed",
                   "error": "image_url is required for Instagram feed posts"}
    with patch("src.mcp.social_server.SocialMCPServer.post_to_instagram",
               return_value=mock_result):
        # Should not raise — failure handled gracefully
        _handle_approved_social_posts(vault, [req], dry_run=False)

    draft = vault / "Approved" / f"draft-instagram-post-{req_id[:8]}.md"
    assert draft.exists(), "Draft must stay in Approved/ when image_url missing"


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_no_social_drafts_returns_immediately(vault):
    from src.main import _handle_approved_social_posts

    email_req = ApprovalRequest(
        id="email-uuid-0001",
        type="email",
        source="gmail",
        priority="low",
        proposed_action="Send reply",
    )
    email_req.approve()

    # Should not crash and not touch Done/
    _handle_approved_social_posts(vault, [email_req], dry_run=False)
    assert len(list((vault / "Done").glob("*.md"))) == 0


def test_missing_draft_file_skips_gracefully(vault):
    """Approved request exists but draft file is missing from Approved/ — skip it."""
    from src.main import _handle_approved_social_posts

    req = _social_request("twitter", "missing-file-0001")
    # Do NOT write any draft file

    with patch("src.mcp.social_server.SocialMCPServer.post_to_twitter") as mock_tw:
        _handle_approved_social_posts(vault, [req], dry_run=False)

    mock_tw.assert_not_called()


def test_dry_run_does_not_move_file(vault):
    """In dry_run mode the draft stays in Approved/ even on API success."""
    from src.main import _handle_approved_social_posts

    req_id = "dry-run-uuid-001"
    req = _social_request("twitter", req_id)
    draft = _write_draft(vault, "twitter", req_id, "Dry run tweet")

    mock_result = {"tweet_id": "tw-dry", "status": "sent", "error": None}
    with patch("src.mcp.social_server.SocialMCPServer.post_to_twitter",
               return_value=mock_result):
        _handle_approved_social_posts(vault, [req], dry_run=True)

    assert draft.exists(), "dry_run=True must not rename/move files"


# ── Audit log → CEO Briefing pipeline ────────────────────────────────────────

def test_log_social_post_written_to_log_file(vault):
    from src.main import _log_social_post

    _log_social_post(vault, "twitter", "tw-001", "Test tweet content", dry_run=False)

    log_files = list((vault / "Logs").glob("*.json"))
    assert len(log_files) == 1
    entries = json.loads(log_files[0].read_text())
    assert len(entries) == 1
    e = entries[0]
    assert e["actor"] == "social_poster_twitter"
    assert e["action"] == "twitter_post_published"
    assert e["outcome"] == "success"
    assert e["details"]["platform"] == "twitter"
    assert e["details"]["post_id"] == "tw-001"
    assert "Test tweet" in e["details"]["content_preview"]


def test_log_social_post_dry_run_outcome(vault):
    from src.main import _log_social_post

    _log_social_post(vault, "facebook", "fb-dry", "Dry run post", dry_run=True)

    entries = json.loads(next((vault / "Logs").glob("*.json")).read_text())
    assert entries[0]["outcome"] == "dry_run"


def test_ceo_briefing_section8_detects_social_log(vault):
    """End-to-end: _log_social_post → _read_log_summary → social_events populated."""
    from src.main import _log_social_post
    from src.skills.ceo_briefing import _read_log_summary

    _log_social_post(vault, "linkedin", "li-post-99", "LinkedIn content here", dry_run=False)

    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=1)
    summary = _read_log_summary(vault / "Logs", period_start, now)

    assert len(summary.social_events) == 1
    ev = summary.social_events[0]
    assert ev["platform"] == "linkedin"
    assert ev["post_id"] == "li-post-99"
    assert ev["operation"] == "linkedin_post_published"
    assert ev["outcome"] == "success"
    assert "LinkedIn content" in ev["content_preview"]


def test_ceo_briefing_section8_platform_breakdown(vault):
    """Multiple posts across platforms all appear in social_events."""
    from src.main import _log_social_post
    from src.skills.ceo_briefing import _read_log_summary

    _log_social_post(vault, "twitter", "tw-1", "Tweet one", dry_run=False)
    _log_social_post(vault, "twitter", "tw-2", "Tweet two", dry_run=False)
    _log_social_post(vault, "facebook", "fb-1", "Facebook post", dry_run=False)

    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=1)
    summary = _read_log_summary(vault / "Logs", period_start, now)

    assert len(summary.social_events) == 3
    platforms = [ev["platform"] for ev in summary.social_events]
    assert platforms.count("twitter") == 2
    assert platforms.count("facebook") == 1
