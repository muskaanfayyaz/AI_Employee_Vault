---
id: 41436c7b-ec20-4c85-b562-bbca21c0c22a
type: social
source: drop_folder
priority: high
status: in_progress
requires_approval: true
classification: local_only
created_at: 2026-03-07T12:49:31.030302+00:00
updated_at: 2026-03-07T13:07:18.436361+00:00
tags: []
platforms: [linkedin]
---

## Image URL

https://www.google.com/imgres?q=ai%20employees&imgurl=https%3A%2F%2Fwww.techfinitive.com%2Fwp-content%2Fuploads%2F2025%2F02%2Fimage_fx_-3-1.jpg&imgrefurl=https%3A%2F%2Fwww.techfinitive.com%2Fai-at-work-employees-want-a-say-in-how-ai-is-used%2F&docid=lfameNBN-zAZ8M&tbnid=StLMQ4ffH3QfOM&vet=12ahUKEwiKgIXp4Y2TAxWSSKQEHcWxB_cQnPAOegQITBAB..i&w=1000&h=545&hcb=2&ved=2ahUKEwiKgIXp4Y2TAxWSSKQEHcWxB_cQnPAOegQITBAB

## Post

Excited to share a major milestone — we've just completed the **Gold Tier** of our AI Employee system, a local-first autonomous Digital FTE built on Claude, Python, and an Obsidian vault as a state machine.

Here's what we've shipped across three tiers 👇

---

**Bronze Tier — The Foundation**
- Filesystem watcher: detects files dropped into /Inbox within 30 seconds
- AI Triage Skill: classifies and prioritizes every incoming item automatically
- Planning Skill: generates a structured Plan.md with sequenced steps for each task
- Autonomous executor: works through plan steps and moves items to /Done without human intervention
- Live Dashboard: real-time view of every item across all pipeline stages
- Full audit log: every state transition recorded with timestamp, actor, and outcome
- DRY_RUN mode: safe testing without touching any real system

**Silver Tier — Communication & Scheduling**
- Gmail watcher: polls inbox, detects important emails, and creates action items automatically
- Human-in-the-loop approval workflow: sensitive actions route to /Pending_Approval — nothing sends without your sign-off
- Email MCP server: drafts and sends emails via OAuth-authenticated Gmail
- Cron-based scheduling: the entire pipeline runs on a configurable schedule — no manual triggers needed
- Retry logic: exponential backoff on all external calls (2s → 4s → 8s), failed items move to /Errors with full diagnostics
- LinkedIn social poster: drafts platform-appropriate posts and queues them for approval

**Gold Tier — Full Business Integration**
- Odoo ERP watcher: polls project tasks, sales orders, and invoices — every business event becomes a vault item
- Social media MCP server: integrates LinkedIn, Facebook, Instagram, and Twitter with full retry handling
- Multi-platform social drafting: AI drafts posts per platform, routes all to approval — never posts autonomously
- CEO Briefing generation: weekly summary covering tasks, errors, approvals, and social activity
- Ralph Wiggum self-improvement loop: AI reviews its own past logs, identifies failure patterns, and proposes corrections as new action items
- Accounting audit skill: scans ERP entries for anomalies, duplicates, and missing references
- Multi-MCP orchestration: sequences calls across email, ERP, and social services with partial-failure handling

---

The entire system is file-based, runs locally, and keeps humans in control of every sensitive action. The vault folder structure IS the state machine — /Needs_Action → /In_Progress → /Pending_Approval → /Approved → /Done.

Next up: **Platinum Tier** — 24/7 cloud deployment, bidirectional vault sync, and zero-downtime production orchestration.

Building a Digital FTE that actually replaces routine work, one tier at a time.

#AI #Automation #ProductivityTools #AIEmployee #LLM #ClaudeAI #BuildInPublic #SoftwareEngineering