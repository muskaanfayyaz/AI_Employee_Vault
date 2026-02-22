---
id: "0015"
title: Claude Email Drafter Contextual
stage: green
date: 2026-02-21
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: chat
labels: ["silver-tier","email-drafter","claude-api","contextual-reply"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/skills/email_drafter.py
  - pyproject.toml
  - .env.example
tests:
  - none
---

## Prompt

but the draft email is not satisfied with the requirement [...] make the draft more accurate and relevant to the context of email

## Response snapshot

Issue: _draft_reply() was a static stub returning a generic placeholder.

Fix:
- Added `anthropic>=0.40` to silver deps in pyproject.toml
- Added `ANTHROPIC_API_KEY=` to .env.example under Silver section
- Replaced stub with _claude_draft_reply() using claude-haiku-4-5 with contextual prompt
- Graceful fallback to stub if ANTHROPIC_API_KEY not set or API call fails
- Prompt instructs Claude: write only reply body, address specific content, be professional, end with Best regards + placeholder name
- User must set ANTHROPIC_API_KEY=<their key> in .env

## Outcome

- ✅ Impact: Email drafts now use Claude to generate contextual, relevant replies
- 🧪 Tests: requires ANTHROPIC_API_KEY in .env + live email to test
- 📁 Files: email_drafter.py, pyproject.toml, .env.example
- 🔁 Next prompts: add ANTHROPIC_API_KEY to .env, restart, send test email
- 🧠 Reflection: Used claude-haiku-4-5 (cheapest/fastest) for email drafting — right model for the task

## Evaluation notes (flywheel)

- Failure modes observed: static stub was completely context-unaware
- Graders run and results (PASS/FAIL): n/a
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): tune the prompt for specific reply styles
