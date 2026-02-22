---
id: 1
title: Create Tiered System Spec
stage: spec
date: 2026-02-17
surface: agent
model: claude-opus-4-6
feature: ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.specify
labels: ["spec", "system-design", "tiered-delivery", "bronze-silver-gold"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/001-ai-employee-system/spec.md
  - specs/001-ai-employee-system/checklists/requirements.md
tests:
  - n/a
---

## Prompt

Create a complete SYSTEM SPEC for AI_Employee covering:

Bronze Tier:
- Obsidian vault structure
- One Watcher (FileSystem)
- Claude reads /Needs_Action and creates Plans
- Move completed tasks to /Done
- Agent Skills for reasoning

Silver Tier:
- Gmail Watcher
- WhatsApp Watcher
- One MCP server (email)
- Human-in-the-loop workflow
- Cron scheduling
- Plan.md auto creation

Gold Tier:
- Odoo integration via JSON-RPC MCP
- Social media integration (LinkedIn, Facebook, Instagram, Twitter)
- Weekly CEO Briefing generator
- Accounting audit
- Ralph Wiggum loop
- Multi-MCP orchestration
- Error handling & retry system

Include:
- Folder structure
- Event flow diagram (text)
- State transitions
- Security model
- Logging schema
- DRY_RUN flag behavior

Make it implementation-ready.

## Response snapshot

Rewrote the AI Employee System spec from scratch with 3 user stories (one per tier: Bronze, Silver, Gold), 49 functional requirements, 8 key entities, and 10 success criteria. Included all requested cross-cutting concerns: vault folder structure (FR-001), event flow diagram (FR-004), state transition table (FR-006), security model (FR-033–036), JSON logging schema (FR-037–040), DRY_RUN flag behavior (FR-041–043), and error handling with retry (FR-044–046). Removed the previous 6-story/4-tier structure (which included Platinum/cloud deployment). Quality checklist passes all items — zero NEEDS CLARIFICATION markers.

## Outcome

- Impact: Complete system spec rewrite — 49 FRs, 3 tiers, implementation-ready
- Tests: n/a (specification document)
- Files: specs/001-ai-employee-system/spec.md, specs/001-ai-employee-system/checklists/requirements.md
- Next prompts: Run /sp.clarify to identify gaps, or /sp.plan to begin architecture
- Reflection: User provided extremely detailed tier breakdown which eliminated the need for clarification questions. The Ralph Wiggum loop and Odoo JSON-RPC MCP are the most architecturally complex Gold features — these will need ADR consideration during planning.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): checklist validation PASS — all items checked
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
