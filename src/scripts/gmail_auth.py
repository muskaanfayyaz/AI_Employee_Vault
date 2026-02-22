"""Gmail OAuth2 authentication setup — run once to generate token.json.

Usage
-----
    python -m src.scripts.gmail_auth

Steps this script performs:
1. Reads credentials.json from Config/gmail_credentials.json
   (download this from Google Cloud Console → APIs & Services → Credentials)
2. Opens your browser to complete the OAuth2 consent flow
3. Saves the resulting token.json to Config/gmail_token.json
4. Prints the path to add to your .env as GMAIL_OAUTH_TOKEN_PATH

Requirements
------------
- pip install -e ".[silver]"  (google-auth-oauthlib already installed)
- A Google Cloud project with Gmail API enabled
- An OAuth 2.0 Client ID (Desktop app type) downloaded as credentials.json
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gmail-auth")

# Scopes required by the Gmail watcher and email MCP server.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",   # search + read emails
    "https://www.googleapis.com/auth/gmail.modify",     # mark as read
    "https://www.googleapis.com/auth/gmail.send",       # send emails (FR-017, approval required)
]


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import]
        from google.oauth2.credentials import Credentials  # type: ignore[import]
    except ImportError:
        logger.error(
            "Missing dependencies. Run: pip install -e '.[silver]'"
        )
        return 1

    # Resolve vault root.
    try:
        from src.config import VAULT_ROOT
    except ImportError:
        VAULT_ROOT = Path(os.getenv("VAULT_ROOT", str(Path.cwd()))).resolve()

    config_dir = VAULT_ROOT / "Config"
    credentials_path = config_dir / "gmail_credentials.json"
    token_path = config_dir / "gmail_token.json"

    if not credentials_path.exists():
        logger.error(
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  credentials.json NOT FOUND\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "  Follow these steps to get it:\n"
            "\n"
            "  1. Go to: https://console.cloud.google.com/\n"
            "  2. Create a project (or select existing)\n"
            "  3. Enable 'Gmail API':\n"
            "     APIs & Services → Enable APIs → search Gmail API → Enable\n"
            "  4. Create OAuth credentials:\n"
            "     APIs & Services → Credentials → Create Credentials\n"
            "     → OAuth client ID → Desktop app → Download JSON\n"
            "  5. Save the downloaded file as:\n"
            f"     {credentials_path}\n"
            "\n"
            "  Then re-run this script.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        return 1

    logger.info("Found credentials: %s", credentials_path)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path), SCOPES
    )
    # WSL2-compatible manual flow: browser can't reach WSL2's localhost server,
    # so we print the auth URL and ask the user to paste back the redirect URL.
    flow.redirect_uri = "http://localhost:8080/"
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

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
    # Allow http://localhost redirect — safe for local auth scripts only.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    flow.fetch_token(authorization_response=redirect_response)
    creds = flow.credentials

    token_path.write_text(creds.to_json(), encoding="utf-8")
    logger.info("Token saved: %s", token_path)

    print(
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  SUCCESS — Gmail token saved!\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "  Add this line to your .env file:\n"
        f"\n"
        f"  GMAIL_OAUTH_TOKEN_PATH={token_path}\n"
        "\n"
        "  Then start the system:\n"
        "  python -m src.main --schedule\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
