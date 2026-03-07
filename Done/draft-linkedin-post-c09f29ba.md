---
id: c09f29ba-4d3b-49bd-934c-3baebe139b33
type: social
source: social_poster_linkedin
priority: medium
status: pending_approval
requires_approval: true
classification: local_only
created_at: 2026-03-07T13:07:18.550568+00:00
updated_at: 2026-03-07T13:07:18.550568+00:00
tags: [draft, linkedin-post]
approval:
  proposed_action: "Post to LinkedIn"
  reasoning: "FR-G015 — outbound social post requires human approval"
  original_item_id: 41436c7b-ec20-4c85-b562-bbca21c0c22a
  requested_at: 2026-03-07T13:07:18.550568+00:00
  decision: approved
  decided_at: null
  feedback: null
---

# LinkedIn Post Draft

**Platform**: LinkedIn  
**Character Count**: 2917 / 3000  
**Original Item**: linkedin-gold-tier-announcement.md  

## Post Content

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

#linkedin

## Image URL

https://www.techfinitive.com/wp-content/uploads/2025/02/image_fx_-3-1.jpg

## Original Context

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

## Approval Instructions

- [ ] Review draft post above
- [ ] Optionally add a public image URL in the Image URL section above
- [ ] Edit if needed (editing resets approval)
- [ ] Change `decision: pending` → `decision: approved` to schedule publish
- [ ] Change `decision: pending` → `decision: rejected` to discard
- [ ] Note: any edit to Post Content requires a new approval cycle
