---
id: 1
title: Create AI Employee Constitution
stage: constitution
date: 2026-02-16
surface: agent
model: claude-opus-4-6
feature: none
branch: master
user: unknown
command: /sp.constitution
labels: ["constitution", "governance", "initial-setup"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - .specify/memory/constitution.md
tests:
  - N/A
---

## Prompt

Create the project constitution - the highest-level governing document

# AI Employee Project Constitution

## Purpose
This project exists to create an autonomous, local-first AI employee that manages personal and business affairs while maintaining human control over sensitive operations.

## Core Principles (Immutable)

### 1. Human Sovereignty
- Humans maintain final decision authority
- AI suggests, humans approve critical actions
- Transparency in all AI decisions

### 2. Privacy First
- All data stored locally by default
- No credentials in version control
- Encryption for sensitive data

### 3. Safety by Design
- Fail-safe defaults (dry-run mode)
- Comprehensive audit logging
- Graceful degradation on errors

### 4. Spec-Driven Development
- Constitution → Specification → Plan → Task → Implementation
- No implementation without specification
- All changes documented and versioned

### 5. Incremental Delivery
- Bronze → Silver → Gold → Platinum tiers
- Each tier must be fully functional before advancing
- No premature optimization

## Governance
- All architectural decisions reference this constitution
- Violations of core principles require constitutional amendment
- Security and privacy principles are non-negotiable

## Success Definition
The project is successful when:
1. AI autonomously handles 80% of routine tasks
2. Human approval time < 5 minutes per day
3. Zero unauthorized actions logged
4. System uptime > 95% over 30 days
5. User reports reduced workload and increased productivity

## Response snapshot

Created the initial AI Employee Project Constitution v1.0.0. Replaced all template placeholders with concrete values derived from user input. The constitution establishes 5 core principles (Human Sovereignty, Privacy First, Safety by Design, Spec-Driven Development, Incremental Delivery), a measurable Success Definition, and a Governance section with amendment procedures and semantic versioning policy. All dependent templates (plan, spec, tasks, commands) were verified for compatibility — no updates required. A Sync Impact Report is embedded as an HTML comment at the top of the constitution file.

## Outcome

- Impact: Initial constitution established — all future specs, plans, and tasks are now governed by these 5 principles
- Tests: N/A (documentation artifact)
- Files: .specify/memory/constitution.md (created v1.0.0)
- Next prompts: /sp.specify to create the first feature spec; /sp.adr if architectural decisions arise
- Reflection: User provided comprehensive input; all 5 principles mapped cleanly to the template with rationale added for each

## Evaluation notes (flywheel)

- Failure modes observed: None — user input was complete and unambiguous
- Graders run and results (PASS/FAIL): Manual placeholder check PASS, version validation PASS, date format PASS
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): N/A
