<!--
  ╔══════════════════════════════════════════════════════════════╗
  ║                   SYNC IMPACT REPORT                       ║
  ╠══════════════════════════════════════════════════════════════╣
  ║ Version Change: 1.0.0 → 2.0.0 (MAJOR — principles         ║
  ║   removed, redefined, and added)                           ║
  ║                                                            ║
  ║ Modified Principles:                                       ║
  ║  - I.  Human Sovereignty (updated: payment threshold)      ║
  ║  - II. Privacy First (updated: Obsidian vault specifics)   ║
  ║                                                            ║
  ║ Added Principles:                                          ║
  ║  - III. Agent Skills First                                 ║
  ║  - IV.  File-Based State                                   ║
  ║  - V.   Human-in-the-Loop                                  ║
  ║  - VI.  Audit Logging                                      ║
  ║  - VII. Graceful Failure                                   ║
  ║                                                            ║
  ║ Removed Principles:                                        ║
  ║  - III. Safety by Design (split → VI + VII)                ║
  ║  - IV.  Spec-Driven Development                            ║
  ║  - V.   Incremental Delivery                               ║
  ║                                                            ║
  ║ Added Sections:                                            ║
  ║  - Purpose rewritten for Digital FTE scope                 ║
  ║                                                            ║
  ║ Removed Sections:                                          ║
  ║  - Success Definition (deferred to feature specs)          ║
  ║                                                            ║
  ║ Templates Requiring Updates:                               ║
  ║  ✅ .specify/templates/plan-template.md                    ║
  ║     — "Constitution Check" is dynamic; no change needed    ║
  ║  ✅ .specify/templates/spec-template.md                    ║
  ║     — No direct constitution references; compatible        ║
  ║  ✅ .specify/templates/tasks-template.md                   ║
  ║     — Phase structure still compatible                     ║
  ║  ✅ .claude/commands/*.md                                  ║
  ║     — No outdated constitution references found            ║
  ║                                                            ║
  ║ Deferred TODOs:                                            ║
  ║  - Payment threshold amount not specified (see V.)         ║
  ╚══════════════════════════════════════════════════════════════╝
-->

# AI Employee Project Constitution

## Purpose

Build a local-first autonomous Digital FTE (Full-Time Employee)
using Claude Code, Obsidian, Python Watchers, MCP servers, and
a Ralph Wiggum loop. The system manages personal and business
affairs while maintaining human control over sensitive operations.

All data lives in the local Obsidian vault. The AI operates as
a skills-based agent that watches for work, executes tasks, and
logs every action — with human approval gates for anything
irreversible or sensitive.

## Core Principles

> All seven principles below are **immutable**. Amendments to
> any principle require a constitutional amendment with written
> rationale, impact assessment, and explicit user approval.

### I. Human Sovereignty

- The AI MUST suggest actions; humans approve all sensitive
  operations.
- No autonomous payment or financial transaction above the
  configured threshold is permitted without human approval.
- No autonomous action may override an explicit human directive.
- All AI decisions MUST be transparent and auditable.

**Rationale**: An AI employee that acts without human oversight
creates unacceptable risk. Trust is built through transparency
and deference to human judgment on consequential decisions.

### II. Privacy First

- All data MUST be stored locally in the Obsidian vault.
- Credentials, tokens, and secrets MUST reside in `.env` files
  only — NEVER in markdown, version control, or logs.
- External data transmission MUST require explicit user consent.
- No cloud sync of sensitive data unless explicitly configured
  and approved by the user.

**Rationale**: A system managing personal and business affairs
handles inherently sensitive information. Local-first storage
protects the user from data exposure; `.env`-only secrets
prevent accidental credential leaks.

### III. Agent Skills First

- All AI functionality MUST be implemented as Claude Agent
  Skills (structured, versioned, testable units of capability).
- No ad-hoc prompt scripting outside the Skills framework.
- Each skill MUST have a defined interface: inputs, outputs,
  and error contract.
- Skills MUST be discoverable and documented in the vault.

**Rationale**: Structured skills enforce consistency, enable
testing, and prevent the system from devolving into fragile
prompt spaghetti. Every capability is a first-class artifact.

### IV. File-Based State

- System state MUST be stored in vault folders as files.
- Movement of files between folders represents workflow
  transitions (e.g., `Inbox/` → `Processing/` → `Done/`).
- State MUST be human-readable (markdown, JSON) — never
  opaque binary unless absolutely required.
- No external database is permitted for core workflow state;
  the vault IS the database.

**Rationale**: File-based state keeps the system inspectable,
version-controllable, and recoverable. If the AI breaks, the
human can read and manually process any queued work.

### V. Human-in-the-Loop

- Payments and financial transactions MUST require human
  approval.
- Adding new contacts or external integrations MUST require
  human approval.
- Deletions of any user data MUST require human approval.
- The system MUST present a clear approval prompt with context
  before any gated action.

**Rationale**: Irreversible or externally-visible actions carry
outsized risk. A mandatory approval gate ensures the human
retains control over actions that cannot be undone.

### VI. Audit Logging

- Every action taken by the system MUST be logged in
  `/Logs/YYYY-MM-DD.json`.
- Each log entry MUST include: timestamp, actor (skill name),
  action, input summary, outcome, and duration.
- Logs MUST be append-only; retroactive modification is
  prohibited.
- Logs MUST be retained for a minimum of 90 days.

**Rationale**: Comprehensive audit trails make the system
predictable, debuggable, and accountable. When something goes
wrong, the log provides the full story.

### VII. Graceful Failure

- The system MUST NOT enter infinite loops; all retry logic
  MUST use exponential backoff with a maximum retry count.
- Development and testing MUST use `DRY_RUN` mode for
  destructive or irreversible operations.
- The system MUST degrade gracefully on errors — partial
  functionality is preferable to total failure.
- Unrecoverable errors MUST be logged and surfaced to the
  user, not silently swallowed.

**Rationale**: An AI employee that fails silently or loops
endlessly erodes trust. Safe defaults, backoff strategies, and
dry-run modes make the system predictable and recoverable.

## Governance

- This constitution is the highest-authority document in the
  project. All architectural decisions, specifications, and
  plans MUST reference and comply with it.
- All seven Core Principles are **immutable**. Amendments MUST
  include: a written rationale, an impact assessment, a
  migration plan for affected artifacts, and explicit user
  approval.
- Violations of Core Principles require a constitutional
  amendment before proceeding — no exceptions.
- Compliance with this constitution MUST be verified during
  specification review, plan review, and code review.
- The constitution follows semantic versioning: MAJOR for
  principle changes or removals, MINOR for new sections or
  expanded guidance, PATCH for clarifications.

**Version**: 2.0.0 | **Ratified**: 2026-02-16 | **Last Amended**: 2026-02-17
