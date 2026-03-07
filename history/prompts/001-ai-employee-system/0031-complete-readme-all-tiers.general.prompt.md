---
id: "0031"
title: Complete README All Tiers Documentation
stage: general
date: 2026-03-07
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: "write a complete readme for this project explaining all tier features and implementation their function and achievement explain all workflow"
labels: ["docs", "readme", "bronze", "silver", "gold", "platinum"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - README.md
tests:
  - null
---

## Prompt

write a complete readme for this project explaining all tier features and implementation their function and achievement explain all workflow

## Response

Created comprehensive README.md covering:
- Architecture overview with ASCII diagram
- Vault state machine (folder = status, move = transition)
- Bronze Tier: filesystem watcher, triage, planner, executor, dashboard, audit logger, DRY_RUN
- Silver Tier: Gmail/WhatsApp/LinkedIn watchers, EmailDrafterSkill, EmailMCPServer, ApprovalManager, Scheduler, retry system
- Gold Tier: Odoo watcher, SocialPosterSkill (4 platforms), SocialMCPServer, CeoBriefing (10 sections), RalphWiggum loop, SubscriptionAudit
- Platinum Tier: cloud/local architecture, data classification (local_only/syncable/redacted_summary), bidirectional sync, health monitoring, zero-downtime deployments
- Core engine details: retry decorator, state machine transitions, audit log schema, MCP base server
- Security model table
- Full CLI command reference
- Configuration reference (all YAML files + scheduler defaults)
- Complete project structure tree
- Technology stack table
- Tier completion status table
