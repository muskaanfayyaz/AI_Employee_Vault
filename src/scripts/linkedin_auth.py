"""LinkedIn OAuth2 authentication setup — run once to generate an access token.

Usage
-----
    python -m src.scripts.linkedin_auth

Steps this script performs:
1. Reads credentials from Config/linkedin_credentials.json
   (created manually using your LinkedIn App's Client ID and Secret)
2. Prints the OAuth2 authorisation URL — open it in your Windows browser
3. You approve the app and your browser redirects to localhost:8080
   (page may fail to load — that is expected in WSL2)
4. Paste the full redirect URL back into the terminal
5. Script exchanges the code for an access token
6. Prints the token and the line to add to your .env file

Requirements
------------
- pip install -e ".[silver]"
- A LinkedIn App at https://www.linkedin.com/developers/apps with:
    * OAuth 2.0 settings → Redirect URL: http://localhost:8080/
    * Products: "Sign In with LinkedIn using OpenID Connect"
      (grants openid, profile, email scopes)
    * Optional: "Share on LinkedIn" for w_member_social scope
- Download credentials as Config/linkedin_credentials.json:
    {
        "client_id": "YOUR_CLIENT_ID",
        "client_secret": "YOUR_CLIENT_SECRET"
    }

Scopes requested
----------------
- openid   — OIDC sign-in (required for OpenID Connect product)
- profile  — basic profile (name, photo)
- email    — primary email address

Note: r_liteprofile is deprecated and removed.
w_member_social — post content to LinkedIn on behalf of the user.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("linkedin-auth")

# Redirect URI must be registered in your LinkedIn App's OAuth settings.
REDIRECT_URI = "http://localhost:8080/"

# Scopes for invitation polling.  Add "w_member_social" if you need to post.
SCOPES = ["openid", "profile", "email", "w_member_social"]

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


def main() -> int:
    # Resolve vault root.
    try:
        from src.config import VAULT_ROOT
    except ImportError:
        VAULT_ROOT = Path(os.getenv("VAULT_ROOT", str(Path.cwd()))).resolve()

    config_dir = VAULT_ROOT / "Config"
    credentials_path = config_dir / "linkedin_credentials.json"
    token_path = config_dir / "linkedin_token.json"

    # ── Step 1: read credentials.json ────────────────────────────────────────
    if not credentials_path.exists():
        logger.error(
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  linkedin_credentials.json NOT FOUND\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "  Create a LinkedIn App and get your credentials:\n"
            "\n"
            "  1. Go to: https://www.linkedin.com/developers/apps\n"
            "  2. Create a new app (or select existing)\n"
            "  3. Under 'Auth' tab, copy:\n"
            "     - Client ID\n"
            "     - Client Secret\n"
            "  4. Under 'Auth' tab → OAuth 2.0 settings:\n"
            "     Add Redirect URL: http://localhost:8080/\n"
            "  5. Under 'Products' tab, request:\n"
            "     'Sign In with LinkedIn using OpenID Connect'\n"
            "  6. Save your credentials as:\n"
            f"     {credentials_path}\n"
            "\n"
            "  File format:\n"
            "  {\n"
            '    "client_id": "YOUR_CLIENT_ID",\n'
            '    "client_secret": "YOUR_CLIENT_SECRET"\n'
            "  }\n"
            "\n"
            "  Then re-run this script.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        return 1

    try:
        creds = json.loads(credentials_path.read_text(encoding="utf-8"))
        client_id: str = creds["client_id"]
        client_secret: str = creds["client_secret"]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error(
            "Could not read %s: %s\n"
            "Ensure the file contains {\"client_id\": ..., \"client_secret\": ...}",
            credentials_path,
            exc,
        )
        return 1

    logger.info("Found credentials: %s (client_id=%s...)", credentials_path, client_id[:6])

    # ── Step 2: build authorisation URL ──────────────────────────────────────
    # LinkedIn uses a simple query-string OAuth2 flow (no PKCE required).
    import secrets
    state = secrets.token_urlsafe(16)

    auth_params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "scope": " ".join(SCOPES),
        }
    )
    auth_url = f"{LINKEDIN_AUTH_URL}?{auth_params}"

    print(
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  STEP 1 — Open this URL in your Windows browser:\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n{auth_url}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  STEP 2 — After you click 'Allow', your browser\n"
        "  will redirect to localhost:8080 (page may fail).\n"
        "  Copy the FULL URL from the browser address bar.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    redirect_response = input("Paste the full redirect URL here: ").strip()

    # ── Step 3: extract code from redirect URL ────────────────────────────────
    parsed = urllib.parse.urlparse(redirect_response)
    params = urllib.parse.parse_qs(parsed.query)

    if "error" in params:
        error = params.get("error", ["unknown"])[0]
        error_desc = params.get("error_description", [""])[0]
        logger.error("OAuth error: %s — %s", error, error_desc)
        return 1

    code_list = params.get("code", [])
    if not code_list:
        logger.error(
            "No 'code' parameter found in the redirect URL.\n"
            "Make sure you copied the full URL (including ?code=...)."
        )
        return 1
    code = code_list[0]

    returned_state = params.get("state", [""])[0]
    if returned_state != state:
        logger.warning(
            "State mismatch (expected %s, got %s) — possible CSRF. "
            "Proceeding anyway for local setup.",
            state,
            returned_state,
        )

    # ── Step 4: exchange code for access token ────────────────────────────────
    token_data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        LINKEDIN_TOKEN_URL,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_response = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Token exchange failed: %s", exc)
        return 1

    access_token: str = token_response.get("access_token", "")
    expires_in: int = token_response.get("expires_in", 0)  # seconds; ~5184000 = 60 days
    refresh_token: str = token_response.get("refresh_token", "")

    if not access_token:
        logger.error("No access_token in response: %s", token_response)
        return 1

    # ── Step 5: save token file ───────────────────────────────────────────────
    from datetime import datetime, timezone, timedelta

    expires_at = (
        (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        if expires_in
        else "unknown"
    )

    token_payload = {
        "access_token": access_token,
        "token_type": token_response.get("token_type", "Bearer"),
        "expires_in": expires_in,
        "expires_at": expires_at,
        "refresh_token": refresh_token,
        "scope": token_response.get("scope", " ".join(SCOPES)),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    config_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token_payload, indent=2), encoding="utf-8")
    logger.info("Token saved: %s", token_path)

    # ── Step 6: instruct user ─────────────────────────────────────────────────
    days = expires_in // 86400 if expires_in else "?"
    print(
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  SUCCESS — LinkedIn token saved!\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        f"  Token expires in approximately {days} days ({expires_at}).\n"
        "\n"
        "  Add this line to your .env file:\n"
        "\n"
        f"  LINKEDIN_ACCESS_TOKEN={access_token}\n"
        "\n"
        "  Then enable the watcher in Config/linkedin_watcher.yaml:\n"
        "    enabled: true\n"
        "\n"
        "  Then start the system:\n"
        "  python -m src.main --schedule\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
