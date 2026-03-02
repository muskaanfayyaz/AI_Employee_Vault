---
id: "0006"
title: "Gold Tier Run Instructions and Env Setup"
stage: general
date: "2026-02-28"
surface: agent
model: claude-sonnet-4-6
feature: "002-gold-tier"
branch: "002-gold-tier"
user: muskaan
command: "chat"
labels: ["runbook", "setup", "env", "gold-tier", "instructions"]
links:
  spec: "specs/002-gold-tier/spec.md"
  ticket: "null"
  adr: "null"
  pr: "null"
files: []
tests: []
---

## Prompt

now give complete step by step instruction run this gold tier with all steps also tell to add things in .env for this tier

## Response

Delivered a complete step-by-step Gold Tier setup guide covering:

1. Python dependency installation (watchdog, schedule, python-dotenv, pyyaml, requests, google-generativeai)
2. Odoo MCP Server build (npm install + npm run build in mcp-servers/odoo/)
3. Full .env configuration for vault root — all Gold Tier keys: ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, FACEBOOK_ACCESS_TOKEN, FACEBOOK_PAGE_ID, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID, TWITTER_API_KEY, TWITTER_API_KEY_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET, TWITTER_BEARER_TOKEN
4. Odoo MCP server .env configuration (mcp-servers/odoo/.env)
5. Enabling integrations in Config YAML files (odoo_watcher.yaml, facebook_watcher.yaml, instagram_watcher.yaml, twitter_watcher.yaml)
6. Vault initialisation: python -m src.main --init
7. All run modes documented: --schedule (full), --briefing, --subscription-audit, --ralph, --process, --dry-run
8. Approval workflow file-based instructions
9. Social post trigger via drop_folder/
10. Monitoring commands for Dashboard, Logs, Errors, Reports
11. Go-live checklist (DRY_RUN=false)
12. Quick reference table for all Gold Tier .env keys with sources

## Outcome

Complete operational runbook delivered. No code changes made. Pure documentation/guidance response.
