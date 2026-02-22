---
id: 3
title: Create Implementation Plan Bronze Silver Gold
stage: plan
date: 2026-02-17
surface: agent
model: claude-opus-4-6
feature: ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.plan
labels: ["plan", "architecture", "bronze", "silver", "gold", "implementation"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/001-ai-employee-system/plan.md
  - specs/001-ai-employee-system/research.md
  - specs/001-ai-employee-system/data-model.md
  - specs/001-ai-employee-system/contracts/skill-interfaces.md
  - specs/001-ai-employee-system/contracts/mcp-interfaces.md
  - specs/001-ai-employee-system/quickstart.md
  - CLAUDE.md
tests:
  - n/a
---

## Prompt

Create a step-by-step implementation roadmap:

Phase 1: Bronze
Phase 2: Silver
Phase 3: Gold

For each phase:
- Dependencies
- Files to create
- Skills to implement
- MCP servers required
- Watchers required
- Test cases
- Demo scenario

Make tasks small and executable.

## Response snapshot

Created comprehensive implementation plan with 6 artifacts:

1. **plan.md**: Full implementation roadmap covering Bronze (Phase 1), Silver (Phase 2), Gold (Phase 3), Platinum (Phase 4 — deferred). Each phase details: dependencies, files to create, skills to implement, MCP servers, watchers, test cases, and demo scenarios. Includes constitution check (all 7 gates PASS), project structure (~40 source files), cross-cutting concerns (DRY_RUN, security, retry, logging).

2. **research.md**: 12 technology decisions with rationale and alternatives — watchdog, YAML front-matter, JSON logs, schedule library, MCP stdio, Gmail API, WhatsApp Business API, Odoo JSON-RPC, social media adapters, Jinja2 templating, custom state machine, pyproject.toml.

3. **data-model.md**: 7 entity schemas with YAML/JSON definitions, validation rules, and state transition diagram — Task Item, Plan, Approval Request, Audit Log Entry, Watcher Configuration, Agent Skill, Dashboard State.

4. **contracts/skill-interfaces.md**: Interface contracts for all 9 skills (4 Bronze, 1 Silver, 4 Gold) with input/output/side-effects/Claude prompt contracts.

5. **contracts/mcp-interfaces.md**: Interface contracts for 3 MCP servers (Email, Odoo, Social Media) with tool definitions, approval requirements, and credential references.

6. **quickstart.md**: Step-by-step setup guide for all 3 tiers with verification checklists.

Also updated CLAUDE.md agent context with active technologies.

## Outcome

- Impact: Complete architecture and implementation roadmap for 3-tier delivery
- Tests: n/a (planning document)
- Files: plan.md, research.md, data-model.md, contracts/skill-interfaces.md, contracts/mcp-interfaces.md, quickstart.md, CLAUDE.md
- Next prompts: Run /sp.tasks to generate executable task list, or /sp.adr for architectural decisions
- Reflection: The plan is implementation-ready. Key architectural decisions (watchdog, file-based state, MCP stdio) align cleanly with all 7 constitutional principles. Ralph Wiggum loop and multi-MCP orchestration are the most complex Gold features.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): constitution check PASS (7/7 gates), research complete (12 decisions), all contracts defined
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
