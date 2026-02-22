"""Unit tests for src/watchers/gmail.py (T035 / T028 partial).

Gmail API is mocked throughout — no real network calls.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.watchers.gmail import (
    GmailWatcher,
    _decode_b64,
    _find_text_plain,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**watcher_overrides) -> dict:
    """Build a minimal watcher config dict."""
    cfg: dict = {
        "watcher": {
            "name": "gmail-inbox",
            "type": "gmail",
            "enabled": True,
            "polling_interval_seconds": 10,
            "max_results": 50,
            "state_file": "Config/gmail_processed_ids.json",
            "filters": {"keywords": [], "senders": [], "labels": []},
            "credential_ref": "GMAIL_OAUTH_TOKEN_PATH",
        }
    }
    cfg["watcher"].update(watcher_overrides)
    return cfg


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _make_api_message(
    msg_id: str,
    subject: str = "Test Subject",
    from_addr: str = "sender@example.com",
    body_text: str = "Email body.",
    date: str = "Mon, 19 Feb 2026 12:00:00 +0000",
) -> dict:
    """Build a minimal Gmail API message dict."""
    return {
        "id": msg_id,
        "snippet": body_text[:100],
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": from_addr},
                {"name": "Date", "value": date},
            ],
            "mimeType": "text/plain",
            "body": {"data": _b64(body_text)},
            "parts": [],
        },
    }


def _watcher_with_mock_service(config=None) -> tuple[GmailWatcher, MagicMock]:
    """Return (watcher, mock_service) with the service pre-injected."""
    w = GmailWatcher(config or _make_config())
    svc = MagicMock()
    w._service = svc
    w._processed_ids = set()
    return w, svc


# ---------------------------------------------------------------------------
# _decode_b64
# ---------------------------------------------------------------------------


def test_decode_b64_roundtrip():
    original = "Hello, Gmail!"
    assert _decode_b64(_b64(original)) == original


def test_decode_b64_handles_missing_padding():
    # Strip padding and verify restoration.
    encoded = base64.urlsafe_b64encode(b"hello").decode().rstrip("=")
    assert _decode_b64(encoded) == "hello"


def test_decode_b64_empty_string():
    assert _decode_b64("") == ""


# ---------------------------------------------------------------------------
# _find_text_plain
# ---------------------------------------------------------------------------


def test_find_text_plain_simple():
    parts = [{"mimeType": "text/plain", "body": {"data": _b64("plain text")}}]
    assert _find_text_plain(parts) == "plain text"


def test_find_text_plain_skips_html():
    parts = [{"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}}]
    assert _find_text_plain(parts) == ""


def test_find_text_plain_nested_multipart():
    parts = [
        {
            "mimeType": "multipart/alternative",
            "body": {},
            "parts": [
                {"mimeType": "text/html", "body": {"data": _b64("<p>hi</p>")}},
                {"mimeType": "text/plain", "body": {"data": _b64("nested plain")}},
            ],
        }
    ]
    assert _find_text_plain(parts) == "nested plain"


def test_find_text_plain_empty_parts():
    assert _find_text_plain([]) == ""


# ---------------------------------------------------------------------------
# GmailWatcher initialisation
# ---------------------------------------------------------------------------


def test_watcher_name():
    w = GmailWatcher(_make_config())
    assert w.name == "gmail-inbox"


def test_watcher_type():
    w = GmailWatcher(_make_config())
    assert w.watcher_type == "gmail"


def test_watcher_polling_interval():
    w = GmailWatcher(_make_config(polling_interval_seconds=30))
    assert w.polling_interval == 30


def test_watcher_max_results():
    w = GmailWatcher(_make_config(max_results=25))
    assert w._max_results == 25


# ---------------------------------------------------------------------------
# _build_query
# ---------------------------------------------------------------------------


def test_build_query_default_requires_unread_and_important():
    w = GmailWatcher(_make_config())
    q = w._build_query()
    assert "is:unread" in q
    assert "is:important" in q


def test_build_query_keywords_added():
    w = GmailWatcher(_make_config(filters={"keywords": ["invoice", "urgent"]}))
    q = w._build_query()
    assert "invoice" in q
    assert "urgent" in q


def test_build_query_senders_added():
    w = GmailWatcher(_make_config(filters={"senders": ["boss@example.com"]}))
    q = w._build_query()
    assert "from:" in q
    assert "boss@example.com" in q


def test_build_query_labels_added():
    w = GmailWatcher(_make_config(filters={"labels": ["STARRED", "WORK"]}))
    q = w._build_query()
    assert "label:STARRED" in q
    assert "label:WORK" in q


def test_build_query_all_filters():
    w = GmailWatcher(
        _make_config(
            filters={
                "keywords": ["invoice"],
                "senders": ["cfo@example.com"],
                "labels": ["IMPORTANT"],
            }
        )
    )
    q = w._build_query()
    assert "invoice" in q
    assert "cfo@example.com" in q
    assert "label:IMPORTANT" in q


# ---------------------------------------------------------------------------
# check_for_updates — credential missing
# ---------------------------------------------------------------------------


def test_check_for_updates_returns_empty_when_no_credentials():
    w = GmailWatcher(_make_config())
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GMAIL_OAUTH_TOKEN_PATH", None)
        result = w.check_for_updates()
    assert result == []


# ---------------------------------------------------------------------------
# check_for_updates — mocked Gmail API: 3 messages, 2 new, 1 duplicate
# ---------------------------------------------------------------------------


def test_check_for_updates_returns_new_events():
    """3 messages in inbox, 2 new (1 already processed) → 2 events."""
    w, svc = _watcher_with_mock_service()
    w._processed_ids = {"msg002"}  # already processed

    svc.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg001"}, {"id": "msg002"}, {"id": "msg003"}]
    }
    svc.users().messages().get().execute.side_effect = [
        _make_api_message("msg001", subject="New invoice", from_addr="a@x.com"),
        _make_api_message("msg003", subject="Urgent request", from_addr="b@x.com"),
    ]

    events = w.check_for_updates()

    assert len(events) == 2
    ids = {e["message_id"] for e in events}
    assert ids == {"msg001", "msg003"}
    assert "msg002" not in ids


def test_check_for_updates_skips_all_if_all_processed():
    w, svc = _watcher_with_mock_service()
    w._processed_ids = {"msg001", "msg002", "msg003"}

    svc.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg001"}, {"id": "msg002"}, {"id": "msg003"}]
    }

    events = w.check_for_updates()
    assert events == []


def test_check_for_updates_empty_inbox():
    w, svc = _watcher_with_mock_service()
    svc.users().messages().list().execute.return_value = {"messages": []}

    events = w.check_for_updates()
    assert events == []


def test_check_for_updates_event_fields():
    """Event dict contains required fields."""
    w, svc = _watcher_with_mock_service()

    svc.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg_x1"}]
    }
    svc.users().messages().get().execute.return_value = _make_api_message(
        "msg_x1", subject="Hello", from_addr="hi@example.com", body_text="body"
    )

    events = w.check_for_updates()
    assert len(events) == 1
    e = events[0]
    assert e["message_id"] == "msg_x1"
    assert e["subject"] == "Hello"
    assert e["from_addr"] == "hi@example.com"
    assert "body" in e
    assert "detected_at" in e


def test_check_for_updates_api_list_error_returns_empty():
    w, svc = _watcher_with_mock_service()
    svc.users().messages().list().execute.side_effect = Exception("API down")

    events = w.check_for_updates()
    assert events == []


# ---------------------------------------------------------------------------
# create_action_file
# ---------------------------------------------------------------------------


def test_create_action_file_writes_md_with_correct_metadata(tmp_path):
    inbox = tmp_path / "Needs_Action"
    inbox.mkdir()

    w = GmailWatcher(_make_config())
    w._processed_ids = set()
    w._state_file = tmp_path / "Config" / "gmail_processed_ids.json"

    event = {
        "message_id": "abc12345xyz",
        "item_id": str(uuid.uuid4()),
        "subject": "Invoice #1234",
        "from_addr": "finance@example.com",
        "date": "Mon, 19 Feb 2026 12:00:00 +0000",
        "body": "Please find the invoice attached.",
        "snippet": "Please find the invoice",
        "source": "gmail:abc12345xyz",
    }

    path = w.create_action_file(event, inbox)

    assert path.exists()
    text = path.read_text()
    assert "type: email" in text
    assert "source: gmail" in text
    assert "source_id: abc12345xyz" in text
    assert "Invoice #1234" in text
    assert "finance@example.com" in text
    assert "status: needs_action" in text
    assert "- [ ] Review email content" in text


def test_create_action_file_slug_is_safe(tmp_path):
    """Filename contains only safe characters."""
    inbox = tmp_path / "Needs_Action"
    inbox.mkdir()

    w = GmailWatcher(_make_config())
    w._processed_ids = set()
    w._state_file = tmp_path / "Config" / "state.json"

    event = {
        "message_id": "abc00001",
        "item_id": str(uuid.uuid4()),
        "subject": "Hello World! Special@Chars#Here",
        "from_addr": "x@example.com",
        "date": "",
        "body": "body",
        "snippet": "body",
        "source": "gmail:abc00001",
    }

    path = w.create_action_file(event, inbox)
    name = path.name
    assert name.startswith("email-")
    assert " " not in name
    assert "@" not in name
    assert "#" not in name


def test_create_action_file_marks_id_processed(tmp_path):
    """Message ID is added to processed_ids after file creation."""
    inbox = tmp_path / "Needs_Action"
    inbox.mkdir()
    (tmp_path / "Config").mkdir()

    w = GmailWatcher(_make_config())
    w._processed_ids = set()
    w._state_file = tmp_path / "Config" / "state.json"

    event = {
        "message_id": "tracked_001",
        "item_id": str(uuid.uuid4()),
        "subject": "Test",
        "from_addr": "t@example.com",
        "date": "",
        "body": "content",
        "snippet": "content",
        "source": "gmail:tracked_001",
    }

    w.create_action_file(event, inbox)

    assert "tracked_001" in w._processed_ids


def test_create_action_file_persists_state(tmp_path):
    """State file is written with the processed ID."""
    inbox = tmp_path / "Needs_Action"
    inbox.mkdir()
    (tmp_path / "Config").mkdir()

    w = GmailWatcher(_make_config())
    w._processed_ids = set()
    w._state_file = tmp_path / "Config" / "state.json"

    event = {
        "message_id": "persist_001",
        "item_id": str(uuid.uuid4()),
        "subject": "Persist Test",
        "from_addr": "p@example.com",
        "date": "",
        "body": "content",
        "snippet": "content",
        "source": "gmail:persist_001",
    }

    w.create_action_file(event, inbox)

    state = json.loads(w._state_file.read_text())
    assert "persist_001" in state["processed_ids"]


# ---------------------------------------------------------------------------
# Processed ID persistence
# ---------------------------------------------------------------------------


def test_load_processed_ids_returns_empty_when_no_file(tmp_path):
    w = GmailWatcher(_make_config())
    w._state_file = tmp_path / "Config" / "state.json"
    assert w._load_processed_ids() == set()


def test_save_and_load_roundtrip(tmp_path):
    state_dir = tmp_path / "Config"
    state_dir.mkdir()

    w = GmailWatcher(_make_config())
    w._state_file = state_dir / "state.json"
    w._processed_ids = {"id-a", "id-b", "id-c"}
    w._save_processed_ids()

    # Fresh watcher loads same IDs.
    w2 = GmailWatcher(_make_config())
    w2._state_file = state_dir / "state.json"
    loaded = w2._load_processed_ids()
    assert loaded == {"id-a", "id-b", "id-c"}


def test_save_creates_config_dir_if_missing(tmp_path):
    w = GmailWatcher(_make_config())
    w._state_file = tmp_path / "Config" / "nested" / "state.json"
    w._processed_ids = {"x1"}
    w._save_processed_ids()
    assert w._state_file.exists()


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


def test_health_check_false_when_no_env(tmp_path):
    w = GmailWatcher(_make_config())
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GMAIL_OAUTH_TOKEN_PATH", None)
        assert w.health_check() is False


def test_health_check_true_when_token_exists(tmp_path):
    token = tmp_path / "token.json"
    token.write_text("{}")
    w = GmailWatcher(_make_config())
    with patch.dict(os.environ, {"GMAIL_OAUTH_TOKEN_PATH": str(token)}):
        assert w.health_check() is True


def test_health_check_false_when_token_missing(tmp_path):
    w = GmailWatcher(_make_config())
    with patch.dict(os.environ, {"GMAIL_OAUTH_TOKEN_PATH": "/nonexistent/token.json"}):
        assert w.health_check() is False


def test_health_check_false_when_disabled(tmp_path):
    w = GmailWatcher(_make_config(enabled=False))
    token = tmp_path / "token.json"
    token.write_text("{}")
    with patch.dict(os.environ, {"GMAIL_OAUTH_TOKEN_PATH": str(token)}):
        assert w.health_check() is False


# ---------------------------------------------------------------------------
# DRY_RUN — inherited base watcher behaviour
# ---------------------------------------------------------------------------


def test_dry_run_does_not_create_file(tmp_path):
    """In dry_run mode the base watcher skips create_action_file entirely."""
    inbox = tmp_path / "Needs_Action"
    inbox.mkdir()

    w = GmailWatcher(_make_config())
    w._state_file = tmp_path / "Config" / "state.json"
    w._processed_ids = set()

    event = {
        "message_id": "dry_001",
        "source": "gmail:dry_001",
        "subject": "dry test",
    }

    # Call base watcher's _process_event directly.
    w._process_event(event, inbox, dry_run=True)

    assert list(inbox.iterdir()) == []
    assert "dry_001" not in w._processed_ids  # not tracked in dry_run


def test_dry_run_live_comparison(tmp_path):
    """Live mode creates a file; dry_run mode does not."""
    inbox_dry = tmp_path / "dry" / "Needs_Action"
    inbox_dry.mkdir(parents=True)
    inbox_live = tmp_path / "live" / "Needs_Action"
    inbox_live.mkdir(parents=True)

    event = {
        "message_id": "cmp_001",
        "item_id": str(uuid.uuid4()),
        "subject": "comparison test",
        "from_addr": "a@b.com",
        "date": "",
        "body": "body",
        "snippet": "body",
        "source": "gmail:cmp_001",
    }

    # Dry run — no file.
    w_dry = GmailWatcher(_make_config())
    w_dry._processed_ids = set()
    w_dry._state_file = tmp_path / "dry_state.json"
    w_dry._process_event(event, inbox_dry, dry_run=True)
    assert list(inbox_dry.iterdir()) == []

    # Live run — file created.
    w_live = GmailWatcher(_make_config())
    w_live._processed_ids = set()
    w_live._state_file = tmp_path / "live_state.json"
    w_live._process_event(event, inbox_live, dry_run=False)
    files = list(inbox_live.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".md"
