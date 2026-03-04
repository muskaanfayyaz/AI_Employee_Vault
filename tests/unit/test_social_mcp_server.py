"""Unit tests for SocialMCPServer (Gold Tier FR-G012/FR-G015).

Coverage:
- dry_run mode: all four tools return synthetic success, no HTTP calls
- post_to_linkedin: success, non-retryable auth error, URN lookup failure
- post_to_facebook: success, non-retryable error, generic exception
- post_to_instagram: success (two-step), missing image_url, container failure
- post_to_twitter: success, tweepy not installed, 401 error, generic error
- health_check(): all creds present vs missing
- ping(): returns status dict with 'ok'
- _http_post helper: NonRetryableError on 4xx, re-raises HTTPError on 5xx, parses JSON
"""
from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from src.engine.retry import NonRetryableError
from src.mcp.social_server import SocialMCPServer


# ── Credentials fixture ───────────────────────────────────────────────────────

_CREDS = {
    "LINKEDIN_ACCESS_TOKEN": "test-li-token",
    "FACEBOOK_ACCESS_TOKEN": "test-fb-token",
    "FACEBOOK_PAGE_ID": "123456789",
    "INSTAGRAM_ACCESS_TOKEN": "test-ig-token",
    "INSTAGRAM_ACCOUNT_ID": "987654321",
    "TWITTER_API_KEY": "tw-key",
    "TWITTER_API_KEY_SECRET": "tw-key-secret",
    "TWITTER_ACCESS_TOKEN": "tw-access",
    "TWITTER_ACCESS_TOKEN_SECRET": "tw-access-secret",
}


@pytest.fixture()
def creds(monkeypatch):
    """Patch all social credential env vars for the duration of each test."""
    for k, v in _CREDS.items():
        monkeypatch.setenv(k, v)


@pytest.fixture()
def server(creds):
    return SocialMCPServer(dry_run=False)


@pytest.fixture()
def dry_server(creds):
    return SocialMCPServer(dry_run=True)


# ── Identity ──────────────────────────────────────────────────────────────────

def test_name_and_version(server):
    assert server.name == "social-mcp"
    assert server.version == "1.0.0"


def test_ping(server):
    result = server.ping()
    assert isinstance(result, dict)
    assert result.get("status") == "ok"
    assert result.get("server") == "social-mcp"


# ── Health check ──────────────────────────────────────────────────────────────

def test_health_check_all_creds_present(server):
    assert server.health_check() is True


def test_health_check_missing_cred(server, monkeypatch):
    monkeypatch.delenv("TWITTER_API_KEY", raising=False)
    assert server.health_check() is False


# ── dry_run mode ──────────────────────────────────────────────────────────────

def test_dry_run_linkedin_no_http(dry_server):
    with patch("src.mcp.social_server._http_post") as mock_post:
        result = dry_server.post_to_linkedin("Hello LinkedIn!")
    mock_post.assert_not_called()
    assert result == {"post_id": "dry-run-id", "status": "sent", "error": None}


def test_dry_run_facebook_no_http(dry_server):
    with patch("src.mcp.social_server._http_post") as mock_post:
        result = dry_server.post_to_facebook("Hello Facebook!")
    mock_post.assert_not_called()
    assert result["status"] == "sent"
    assert result["post_id"] == "dry-run-id"


def test_dry_run_instagram_no_http(dry_server):
    with patch("src.mcp.social_server._http_post") as mock_post:
        result = dry_server.post_to_instagram("Hello Instagram!", "https://example.com/img.jpg")
    mock_post.assert_not_called()
    assert result["status"] == "sent"
    assert result["media_id"] == "dry-run-id"


def test_dry_run_twitter_no_api_call(dry_server):
    result = dry_server.post_to_twitter("Hello Twitter!")
    assert result == {"tweet_id": "dry-run-id", "status": "sent", "error": None}


# ── LinkedIn ──────────────────────────────────────────────────────────────────

def test_post_to_linkedin_success(server):
    with patch.object(server, "_get_linkedin_person_urn", return_value="urn:li:person:abc123"), \
         patch("src.mcp.social_server._http_post", return_value={"id": "li-post-999"}):
        result = server.post_to_linkedin("My LinkedIn post")

    assert result == {"post_id": "li-post-999", "status": "sent", "error": None}


def test_post_to_linkedin_no_urn(server):
    with patch.object(server, "_get_linkedin_person_urn", return_value=""):
        result = server.post_to_linkedin("My LinkedIn post")

    assert result["status"] == "failed"
    assert "URN" in result["error"]


def test_post_to_linkedin_non_retryable_401(server):
    with patch.object(server, "_get_linkedin_person_urn", return_value="urn:li:person:x"), \
         patch("src.mcp.social_server._http_post",
               side_effect=NonRetryableError("HTTP 401 — Unauthorized")):
        result = server.post_to_linkedin("My post")

    assert result["status"] == "failed"
    assert "401" in result["error"]


# ── Facebook ──────────────────────────────────────────────────────────────────

def test_post_to_facebook_success(server):
    with patch("src.mcp.social_server._http_post", return_value={"id": "fb-post-42"}):
        result = server.post_to_facebook("Hello Facebook!")

    assert result == {"post_id": "fb-post-42", "status": "sent", "error": None}


def test_post_to_facebook_non_retryable_403(server):
    with patch("src.mcp.social_server._http_post",
               side_effect=NonRetryableError("HTTP 403 — Forbidden")):
        result = server.post_to_facebook("Hello Facebook!")

    assert result["status"] == "failed"
    assert "403" in result["error"]


def test_post_to_facebook_generic_exception(server):
    with patch("src.mcp.social_server._http_post",
               side_effect=ConnectionError("network failure")):
        result = server.post_to_facebook("Hello Facebook!")

    assert result["status"] == "failed"
    assert result["error"] is not None


# ── Instagram ─────────────────────────────────────────────────────────────────

def test_post_to_instagram_success(server):
    http_responses = [{"id": "container-001"}, {"id": "media-published-999"}]
    with patch("src.mcp.social_server._http_post", side_effect=http_responses):
        result = server.post_to_instagram("Great photo!", "https://example.com/photo.jpg")

    assert result == {"media_id": "media-published-999", "status": "sent", "error": None}


def test_post_to_instagram_missing_image_url(server):
    with patch("src.mcp.social_server._http_post") as mock_post:
        result = server.post_to_instagram("Caption only", "")
    mock_post.assert_not_called()
    assert result["status"] == "failed"
    assert "image_url" in result["error"]


def test_post_to_instagram_container_returns_no_id(server):
    with patch("src.mcp.social_server._http_post", return_value={}):
        result = server.post_to_instagram("Caption", "https://example.com/img.jpg")

    assert result["status"] == "failed"
    assert result["error"]  # non-empty error message


def test_post_to_instagram_non_retryable_error(server):
    with patch("src.mcp.social_server._http_post",
               side_effect=NonRetryableError("HTTP 400 — Bad Request")):
        result = server.post_to_instagram("Caption", "https://example.com/img.jpg")

    assert result["status"] == "failed"
    assert "400" in result["error"]


# ── Twitter ───────────────────────────────────────────────────────────────────

def test_post_to_twitter_tweepy_missing(server):
    """ImportError for tweepy returns a clear failure dict without raising."""
    import sys
    original = sys.modules.pop("tweepy", None)
    try:
        result = server.post_to_twitter("Hello Twitter!")
    finally:
        if original is not None:
            sys.modules["tweepy"] = original
        elif "tweepy" in sys.modules:
            del sys.modules["tweepy"]

    assert result["status"] == "failed"
    assert "tweepy" in result["error"].lower()


def test_post_to_twitter_success(server):
    mock_tweepy = MagicMock()
    mock_response = MagicMock()
    mock_response.data = {"id": "tweet-123456"}
    mock_tweepy.Client.return_value.create_tweet.return_value = mock_response

    with patch.dict("sys.modules", {"tweepy": mock_tweepy}):
        result = server.post_to_twitter("Hello Twitter!")

    assert result == {"tweet_id": "tweet-123456", "status": "sent", "error": None}


def test_post_to_twitter_401_raises_non_retryable(server):
    mock_tweepy = MagicMock()
    mock_tweepy.Client.return_value.create_tweet.side_effect = Exception(
        "401 Unauthorized: Could not authenticate"
    )

    with patch.dict("sys.modules", {"tweepy": mock_tweepy}):
        with pytest.raises(NonRetryableError):
            server.post_to_twitter("Hello Twitter!")


def test_post_to_twitter_generic_error_returns_failed(server):
    mock_tweepy = MagicMock()
    mock_tweepy.Client.return_value.create_tweet.side_effect = Exception(
        "503 Service Unavailable"
    )

    with patch.dict("sys.modules", {"tweepy": mock_tweepy}):
        result = server.post_to_twitter("Hello Twitter!")

    assert result["status"] == "failed"
    assert result["tweet_id"] == ""


# ── _http_post helper ─────────────────────────────────────────────────────────

def test_http_post_non_retryable_on_401():
    from src.mcp.social_server import _http_post
    import io

    exc = urllib.error.HTTPError(
        url="https://example.com", code=401,
        msg="Unauthorized", hdrs={}, fp=io.BytesIO(b"auth failed"),
    )
    with patch("urllib.request.urlopen", side_effect=exc):
        with pytest.raises(NonRetryableError):
            _http_post("https://example.com", {}, {})


def test_http_post_reraises_retryable_5xx():
    from src.mcp.social_server import _http_post
    import io

    exc = urllib.error.HTTPError(
        url="https://example.com", code=503,
        msg="Service Unavailable", hdrs={}, fp=io.BytesIO(b"down"),
    )
    with patch("urllib.request.urlopen", side_effect=exc):
        with pytest.raises(urllib.error.HTTPError):
            _http_post("https://example.com", {}, {})


def test_http_post_success_returns_json():
    from src.mcp.social_server import _http_post
    import json

    payload = {"id": "post-abc"}
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(payload).encode()

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _http_post("https://example.com", {}, {})

    assert result == payload
