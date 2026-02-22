---
id: "0011"
title: gmail-oauth-setup
stage: green
date: 2026-02-19
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.implement
labels: ["gmail","oauth","setup","real-time","silver"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/scripts/__init__.py
  - src/scripts/gmail_auth.py
tests: []
---

## Prompt

i want to link my gmail to this model so it can work on real time

## Response snapshot

Created `src/scripts/gmail_auth.py` — a one-time OAuth2 setup script that walks
the user through generating a Gmail token.json for real-time inbox watching.

The script:
- Validates credentials.json exists (downloaded from Google Cloud Console)
- Runs the OAuth2 browser consent flow (InstalledAppFlow)
- Saves token.json to Config/gmail_token.json
- Prints the exact .env line to add (GMAIL_OAUTH_TOKEN_PATH)

After setup, `python -m src.main --schedule` starts the real-time Gmail watcher.

## Outcome

- ✅ src/scripts/gmail_auth.py created (OAuth2 flow + clear setup instructions)
- ✅ Silver dependencies already installed (google-api-python-client, google-auth-oauthlib)
- 📋 No code changes to the watcher — credentials path wires in via .env

## Evaluation notes

- Graders run: none (setup script, no unit tests needed)
- Next: user runs `python -m src.scripts.gmail_auth` after getting credentials.json
