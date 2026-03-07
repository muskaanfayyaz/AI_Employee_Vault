"""Social Media MCP server — Gold tier (FR-G012).

Implements platform publish tools for LinkedIn, Facebook, Instagram,
and Twitter/X through the standard ``BaseMCPServer`` pattern.

Tools (all require human approval before being called — FR-G015):
    post_to_linkedin   — POST /v2/ugcPosts
    post_to_facebook   — POST /v18.0/{page_id}/feed
    post_to_instagram  — POST /v18.0/{account_id}/media + /media_publish
    post_to_twitter    — tweepy.Client.create_tweet

All tools are wrapped in ``@with_retry(base_delay=2, max_retries=3)``
and only surface retryable HTTP codes (408, 429, 5xx).  Auth errors
(401, 403) are non-retryable and fail immediately.

Credential refs (env var names):
    linkedin_token          → LINKEDIN_ACCESS_TOKEN
    facebook_token          → FACEBOOK_ACCESS_TOKEN
    facebook_page_id        → FACEBOOK_PAGE_ID
    instagram_token         → INSTAGRAM_ACCESS_TOKEN
    instagram_account_id    → INSTAGRAM_ACCOUNT_ID
    twitter_api_key         → TWITTER_API_KEY
    twitter_api_secret      → TWITTER_API_KEY_SECRET
    twitter_access_token    → TWITTER_ACCESS_TOKEN
    twitter_access_secret   → TWITTER_ACCESS_TOKEN_SECRET

Transport: in-process (called directly from the approval runner).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from src.engine.retry import NonRetryableError, with_retry
from src.mcp.base import BaseMCPServer

logger = logging.getLogger(__name__)

_NON_RETRYABLE_HTTP = frozenset({400, 401, 403, 404, 405, 409, 422})


def _http_post(url: str, payload: dict, headers: dict, timeout: int = 15) -> dict:
    """Execute an HTTP POST and return a dict with the response.

    The LinkedIn Posts API returns 201 with an empty body and puts the
    created resource URN in the ``X-RestLi-Id`` response header.  This
    function normalises that pattern: if the body is empty the returned
    dict will contain ``{"id": <X-RestLi-Id header value>}``.

    Raises
    ------
    NonRetryableError
        For 4xx responses that should never be retried (bad auth, bad request).
    urllib.error.HTTPError
        For retryable 5xx / 429 responses (the retry decorator handles these).
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            restli_id = resp.headers.get("X-RestLi-Id", "")
        if raw.strip():
            result = json.loads(raw)
        else:
            result = {}
        if restli_id and not result.get("id"):
            result["id"] = restli_id
        return result
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in _NON_RETRYABLE_HTTP:
            raise NonRetryableError(
                f"HTTP {exc.code} (non-retryable) — {body[:300]}"
            ) from exc
        raise  # retryable — let the decorator handle it


class SocialMCPServer(BaseMCPServer):
    """Multi-platform social media MCP server.

    Wraps LinkedIn, Facebook, Instagram, and Twitter API calls behind the
    standard ``BaseMCPServer`` interface so they benefit from:

    - Credential-ref validation at construction time
    - ``health_check()`` that reports missing env vars
    - ``@with_retry`` exponential backoff on every tool
    - ``ping()`` liveness endpoint

    Parameters
    ----------
    credential_refs:
        Override the default env-var mapping.  Keys must be the logical
        names listed in the module docstring.
    dry_run:
        When True all tools log their intent but make no API calls and
        return synthetic success responses.
    """

    _DEFAULT_REFS: dict[str, str] = {
        "linkedin_token": "LINKEDIN_ACCESS_TOKEN",
        "facebook_token": "FACEBOOK_ACCESS_TOKEN",
        "facebook_page_id": "FACEBOOK_PAGE_ID",
        "instagram_token": "INSTAGRAM_ACCESS_TOKEN",
        "instagram_account_id": "INSTAGRAM_ACCOUNT_ID",
        "twitter_api_key": "TWITTER_API_KEY",
        "twitter_api_secret": "TWITTER_API_KEY_SECRET",
        "twitter_access_token": "TWITTER_ACCESS_TOKEN",
        "twitter_access_secret": "TWITTER_ACCESS_TOKEN_SECRET",
    }

    def __init__(
        self,
        credential_refs: dict[str, str] | None = None,
        *,
        dry_run: bool = False,
    ) -> None:
        super().__init__(credential_refs or self._DEFAULT_REFS)
        self._dry_run = dry_run

    # ── identity ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "social-mcp"

    @property
    def version(self) -> str:
        return "1.0.0"

    # ── LinkedIn ──────────────────────────────────────────────────────────────

    @with_retry(base_delay=2, max_retries=3)
    def post_to_linkedin(self, content: str, image_url: str = "") -> dict[str, Any]:
        """Publish a text or image post to LinkedIn via the UGC Posts API.

        Parameters
        ----------
        content:
            Post body text (max 3 000 chars for LinkedIn).
        image_url:
            Optional public image URL. When provided the image is downloaded
            and uploaded to LinkedIn via the Assets API, then attached to the
            post as ``shareMediaCategory: IMAGE``.

        Returns
        -------
        dict
            ``{post_id, status, error}``
        """
        if self._dry_run:
            logger.info("[DRY_RUN] Would post to LinkedIn: %.80s...", content)
            return {"post_id": "dry-run-id", "status": "sent", "error": None}

        token = self._resolve_credential("linkedin_token")
        person_urn = self._get_linkedin_person_urn(token)
        if not person_urn:
            return {"post_id": "", "status": "failed",
                    "error": "Could not resolve LinkedIn person URN"}

        li_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        asset_urn = ""
        if image_url:
            asset_urn = self._upload_linkedin_image(token, person_urn, image_url)
            if not asset_urn:
                logger.warning("LinkedIn image upload failed — falling back to text-only post.")

        if asset_urn:
            share_content = {
                "shareCommentary": {"text": content},
                "shareMediaCategory": "IMAGE",
                "media": [{"status": "READY", "media": asset_urn}],
            }
        else:
            share_content = {
                "shareCommentary": {"text": content},
                "shareMediaCategory": "NONE",
            }

        try:
            result = _http_post(
                url="https://api.linkedin.com/v2/ugcPosts",
                payload={
                    "author": person_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": share_content,
                    },
                    "visibility": {
                        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                    },
                },
                headers=li_headers,
            )
            # UGC Posts API returns 201; post URN is in `id` field or X-RestLi-Id header.
            post_id = result.get("id", "")
            logger.info("LinkedIn post published — post_id=%s", post_id)
            return {"post_id": post_id, "status": "sent", "error": None}
        except NonRetryableError as exc:
            logger.error("LinkedIn post failed (non-retryable): %s", exc)
            return {"post_id": "", "status": "failed", "error": str(exc)}
        except Exception as exc:
            logger.error("LinkedIn post failed: %s", exc)
            return {"post_id": "", "status": "failed", "error": str(exc)}

    def _upload_linkedin_image(self, token: str, person_urn: str, image_url: str) -> str:
        """Download image from ``image_url`` and upload it to LinkedIn Assets API.

        Returns the asset URN string on success, or empty string on failure.
        """
        # Step 1: register the upload
        try:
            reg_resp = _http_post(
                url="https://api.linkedin.com/v2/assets?action=registerUpload",
                payload={
                    "registerUploadRequest": {
                        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                        "owner": person_urn,
                        "serviceRelationships": [{
                            "relationshipType": "OWNER",
                            "identifier": "urn:li:userGeneratedContent",
                        }],
                    }
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
            )
        except Exception as exc:
            logger.error("LinkedIn registerUpload failed: %s", exc)
            return ""

        upload_url = (
            reg_resp
            .get("value", {})
            .get("uploadMechanism", {})
            .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
            .get("uploadUrl", "")
        )
        asset_urn = reg_resp.get("value", {}).get("asset", "")
        if not upload_url or not asset_urn:
            logger.error("LinkedIn registerUpload missing uploadUrl or asset: %s", reg_resp)
            return ""

        # Step 2: download image bytes from the provided URL
        try:
            req = urllib.request.Request(image_url, headers={"User-Agent": "AI-Employee/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                image_bytes = resp.read()
        except Exception as exc:
            logger.error("Could not download image from %s: %s", image_url, exc)
            return ""

        # Step 3: upload binary to LinkedIn
        try:
            upload_req = urllib.request.Request(
                upload_url,
                data=image_bytes,
                method="PUT",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/octet-stream",
                },
            )
            with urllib.request.urlopen(upload_req, timeout=30) as resp:
                resp.read()  # drain response
            logger.info("LinkedIn image uploaded — asset=%s", asset_urn)
            return asset_urn
        except Exception as exc:
            logger.error("LinkedIn image PUT failed: %s", exc)
            return ""

    def _get_linkedin_person_urn(self, token: str) -> str:
        """Fetch the LinkedIn member URN via /v2/userinfo."""
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
            logger.warning("LinkedIn /v2/userinfo returned no 'sub': %s", data)
            return ""
        except urllib.error.HTTPError as exc:
            logger.error("LinkedIn /v2/userinfo HTTP %d", exc.code)
            return ""
        except Exception as exc:
            logger.error("LinkedIn person URN lookup failed: %s", exc)
            return ""

    # ── Facebook ──────────────────────────────────────────────────────────────

    @with_retry(base_delay=2, max_retries=3)
    def post_to_facebook(self, content: str) -> dict[str, Any]:
        """Publish a post to a Facebook Page via Graph API v18.

        Parameters
        ----------
        content:
            Post message text.

        Returns
        -------
        dict
            ``{post_id, status, error}``
        """
        if self._dry_run:
            logger.info("[DRY_RUN] Would post to Facebook: %.80s...", content)
            return {"post_id": "dry-run-id", "status": "sent", "error": None}

        token = self._resolve_credential("facebook_token")
        page_id = self._resolve_credential("facebook_page_id")

        try:
            result = _http_post(
                url=f"https://graph.facebook.com/v18.0/{page_id}/feed",
                payload={"message": content, "access_token": token},
                headers={"Content-Type": "application/json"},
            )
            post_id = result.get("id", "")
            logger.info("Facebook post published — post_id=%s", post_id)
            return {"post_id": post_id, "status": "sent", "error": None}
        except NonRetryableError as exc:
            logger.error("Facebook post failed (non-retryable): %s", exc)
            return {"post_id": "", "status": "failed", "error": str(exc)}
        except Exception as exc:
            logger.error("Facebook post failed: %s", exc)
            return {"post_id": "", "status": "failed", "error": str(exc)}

    # ── Instagram ─────────────────────────────────────────────────────────────

    @with_retry(base_delay=2, max_retries=3)
    def post_to_instagram(self, caption: str, image_url: str) -> dict[str, Any]:
        """Publish an image post to Instagram via Facebook Graph API v18.

        Instagram requires a two-step process: create a media container,
        then publish it.  A public ``image_url`` is mandatory for feed posts.

        Parameters
        ----------
        caption:
            Post caption (max 2 200 chars).
        image_url:
            Publicly accessible URL of the image to post.

        Returns
        -------
        dict
            ``{media_id, status, error}``
        """
        if self._dry_run:
            logger.info("[DRY_RUN] Would post to Instagram: %.80s...", caption)
            return {"media_id": "dry-run-id", "status": "sent", "error": None}

        if not image_url:
            return {
                "media_id": "", "status": "failed",
                "error": "image_url is required for Instagram feed posts",
            }

        token = self._resolve_credential("instagram_token")
        account_id = self._resolve_credential("instagram_account_id")

        try:
            # Step 1: create media container
            container = _http_post(
                url=f"https://graph.facebook.com/v18.0/{account_id}/media",
                payload={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": token,
                },
                headers={"Content-Type": "application/json"},
            )
            container_id = container.get("id", "")
            if not container_id:
                return {"media_id": "", "status": "failed",
                        "error": f"Container creation returned no id: {container}"}
            logger.info("Instagram container created: %s", container_id)

            # Step 2: publish the container
            published = _http_post(
                url=f"https://graph.facebook.com/v18.0/{account_id}/media_publish",
                payload={"creation_id": container_id, "access_token": token},
                headers={"Content-Type": "application/json"},
            )
            media_id = published.get("id", "")
            logger.info("Instagram post published — media_id=%s", media_id)
            return {"media_id": media_id, "status": "sent", "error": None}

        except NonRetryableError as exc:
            logger.error("Instagram post failed (non-retryable): %s", exc)
            return {"media_id": "", "status": "failed", "error": str(exc)}
        except Exception as exc:
            logger.error("Instagram post failed: %s", exc)
            return {"media_id": "", "status": "failed", "error": str(exc)}

    # ── Twitter/X ─────────────────────────────────────────────────────────────

    @with_retry(base_delay=2, max_retries=3)
    def post_to_twitter(self, content: str) -> dict[str, Any]:
        """Publish a tweet via Twitter API v2 (OAuth 1.0a).

        Parameters
        ----------
        content:
            Tweet text (max 280 chars).

        Returns
        -------
        dict
            ``{tweet_id, status, error}``
        """
        if self._dry_run:
            logger.info("[DRY_RUN] Would tweet: %.80s...", content)
            return {"tweet_id": "dry-run-id", "status": "sent", "error": None}

        try:
            import tweepy  # type: ignore[import]
        except ImportError:
            return {
                "tweet_id": "", "status": "failed",
                "error": "tweepy not installed — run: pip install tweepy",
            }

        try:
            client = tweepy.Client(
                consumer_key=self._resolve_credential("twitter_api_key"),
                consumer_secret=self._resolve_credential("twitter_api_secret"),
                access_token=self._resolve_credential("twitter_access_token"),
                access_token_secret=self._resolve_credential("twitter_access_secret"),
            )
            response = client.create_tweet(text=content)
            tweet_id = response.data["id"]
            logger.info("Twitter post published — tweet_id=%s", tweet_id)
            return {"tweet_id": tweet_id, "status": "sent", "error": None}
        except Exception as exc:
            # tweepy wraps HTTP errors — check for non-retryable codes
            err_str = str(exc)
            if any(code in err_str for code in ("401", "403", "400")):
                raise NonRetryableError(err_str) from exc
            logger.error("Twitter post failed: %s", exc)
            return {"tweet_id": "", "status": "failed", "error": err_str}
