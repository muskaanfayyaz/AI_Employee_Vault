---
id: "0012"
title: Silver Tier Gmail Run Commands
stage: general
date: 2026-02-21
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: chat
labels: ["gmail","oauth","silver-tier","run-commands"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - none
tests:
  - none
---

## Prompt

give cmds so i can run silver tier with my gmail i have created oath in google console and save as json in /config make sure to give cmds

## Response snapshot

Provided 4-step command sequence:
1. `pip install -e ".[silver]"` — install silver deps
2. `python -m src.scripts.gmail_auth` — OAuth2 browser flow → saves Config/gmail_token.json
3. `echo "GMAIL_OAUTH_TOKEN_PATH=..." >> .env` — register token path
4. `python -m src.main --schedule` — start Silver tier

Noted WSL browser caveat: if browser doesn't open, run Step 2 from Windows terminal.

## Outcome

- ✅ Impact: User has exact commands to authenticate Gmail and start Silver mode
- 🧪 Tests: none — runtime/ops guidance only
- 📁 Files: none modified
- 🔁 Next prompts: run the OAuth flow, then start --schedule
- 🧠 Reflection: credentials.json already existed at Config/gmail_credentials.json; gmail_watcher.yaml already enabled; .env missing GMAIL_OAUTH_TOKEN_PATH — token generation was the only missing step

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): n/a
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
