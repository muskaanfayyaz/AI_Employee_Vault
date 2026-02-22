---
id: 2
title: Amend Constitution v2 Immutable Principles
stage: constitution
date: 2026-02-17
surface: agent
model: claude-opus-4-6
feature: none
branch: 001-ai-employee-system
user: muskaan
command: /sp.constitution
labels: ["constitution", "principles", "governance", "v2"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - .specify/memory/constitution.md
tests:
  - n/a
---

## Prompt

Create a PROJECT CONSTITUTION for a Personal AI Employee.

Project Name: AI_Employee

Purpose:
Build a local-first autonomous Digital FTE using Claude Code, Obsidian, Python Watchers, MCP servers, and a Ralph Wiggum loop.

Core Principles (Immutable):

1. Human Sovereignty
- AI suggests, human approves sensitive actions.
- No autonomous payments above threshold.

2. Privacy First
- All data stored locally in Obsidian vault.
- Secrets in .env only.
- Never store credentials in markdown.

3. Agent Skills First
- All AI functionality must be implemented as Claude Agent Skills.
- No random prompt scripting outside Skills.

4. File-Based State
- State is stored in vault folders.
- Movement of files represents workflow transitions.

5. Human-in-the-Loop
- Payments, new contacts, deletions require approval.

6. Audit Logging
- Every action logged in /Logs/YYYY-MM-DD.json

7. Graceful Failure
- No infinite loops.
- Use retry with backoff.
- Use DRY_RUN mode in development.

Lock these as immutable rules.

## Response snapshot

Amended the project constitution from v1.0.0 to v2.0.0 (MAJOR). Replaced the original 5 principles with 7 immutable principles as specified. Removed Spec-Driven Development and Incremental Delivery principles; split Safety by Design into Audit Logging and Graceful Failure; added Agent Skills First, File-Based State, and Human-in-the-Loop. Updated purpose to reflect Digital FTE scope with Claude Code, Obsidian, Python Watchers, MCP servers, and Ralph Wiggum loop. All templates verified compatible — no updates required.

## Outcome

- Impact: MAJOR constitution rewrite — 7 immutable principles locked
- Tests: n/a (governance document)
- Files: .specify/memory/constitution.md
- Next prompts: Define payment threshold for Principle V; create first feature spec with /sp.specify
- Reflection: User has clear vision of 7 non-negotiable rules. The split of Safety by Design into Audit Logging + Graceful Failure gives each concern dedicated enforcement surface.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): manual review PASS — no unresolved placeholders, all 7 principles present
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
