---
id: "0008"
title: nodejs-email-mcp-server
stage: green
date: 2026-02-19
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: /sp.implement
labels: ["silver","mcp","email","gmail","nodejs","typescript","dry-run","unit-tests"]
links:
  spec: specs/001-ai-employee-system/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - mcp-servers/email/package.json
  - mcp-servers/email/tsconfig.json
  - mcp-servers/email/.env.example
  - mcp-servers/email/src/types.ts
  - mcp-servers/email/src/gmail.ts
  - mcp-servers/email/src/tools.ts
  - mcp-servers/email/src/index.ts
  - mcp-servers/email/tests/tools.test.ts
  - specs/001-ai-employee-system/tasks.md
tests:
  - mcp-servers/email/tests/tools.test.ts (26/26 passed)
---

## Prompt

Create Node.js email MCP server.

Capabilities:
- send_email
- draft_email
- search_email

Add DRY_RUN support.
Return structured JSON responses.

## Response snapshot

Implemented T034b — Node.js TypeScript email MCP server at `mcp-servers/email/`.

**Architecture**: stdio transport via `@modelcontextprotocol/sdk`. TypeScript + CommonJS (compatible with vitest + Node 20). Injectable `GmailClientInterface` makes all three tool handlers unit-testable without real credentials.

**`src/types.ts`**: `EmailToolResult { success, dry_run, data, error }`, `GmailClientInterface`, and input arg interfaces.

**`src/gmail.ts`**: `GmailClient` wraps `googleapis` v1. Lazy auth init on first call (safe to construct without credentials). `buildRaw()` encodes MIME messages as base64url for Gmail API. Handles send, draft, search, get, markRead.

**`src/tools.ts`**: Three pure handlers — `handleSendEmail`, `handleDraftEmail`, `handleSearchEmail`. Each: (1) Zod parse with descriptive errors, (2) short-circuit on `dryRun=true` (stub response, client never touched), (3) null-client guard with actionable error message, (4) client call wrapped in try/catch → structured fail.

**`src/index.ts`**: MCP Server with `ListToolsRequestSchema` + `CallToolRequestSchema` handlers. Exposes 4 tools: `ping`, `send_email`, `draft_email`, `search_email`. `DRY_RUN` from env, `GmailClient` from `GMAIL_OAUTH_TOKEN_PATH` env.

**DRY_RUN semantics**: `DRY_RUN=true` → all tool handlers return `{ success: true, dry_run: true, data: {stub}, error: null }` without any Gmail API calls. Validated by 3 dedicated tests per handler.

**Tests (26, all passing)**:
- `handleSendEmail`: 9 tests — success, optional args forwarding, dry_run no-op, null-client dry-run, null-client live error, invalid email, missing subject/body, client throw
- `handleDraftEmail`: 7 tests — success, args forwarding, dry_run no-op, null-client dry-run, null-client live error, invalid email, client throw
- `handleSearchEmail`: 10 tests — success, args forwarding, default max_results=10, dry_run no-op, null-client dry-run, null-client live error, empty query, client throw, dry_run data includes query

## Outcome

- ✅ Impact: T034b implemented and marked [x] in tasks.md
- 🧪 Tests: `npm test` → 26 passed, 0 failed; `npm run build` → 0 TypeScript errors
- 📁 Files: mcp-servers/email/src/{types,gmail,tools,index}.ts, tests/tools.test.ts, package.json, tsconfig.json, .env.example
- 🔁 Next prompts: T033 (Python BaseMCPServer), T034 (Python email_server.py), T030 (approval model), T031 (approval manager), T032 (approval_policy.yaml), T037 (WhatsApp watcher)
- 🧠 Reflection: Passing `dryRun` explicitly to handlers (rather than reading from `process.env`) made tests trivially simple and completely isolated. The null-client pattern (GmailClient only created when token path is set) gives graceful degradation without a separate DryRunClient class.

## Evaluation notes (flywheel)

- Failure modes observed: None — 26/26 tests passed on first run, build clean
- Graders run and results (PASS/FAIL): vitest 26/26 PASS, tsc PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Implement T030 approval model + T031 approval manager
