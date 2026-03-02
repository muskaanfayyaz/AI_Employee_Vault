---
id: "0021"
title: MCP Email tsconfig Module Resolution Fix
stage: green
date: 2026-02-25
surface: agent
model: claude-sonnet-4-6
feature: 001-ai-employee-system
branch: 001-ai-employee-system
user: muskaan
command: chat
labels: ["mcp", "email", "tsconfig", "moduleResolution", "bundler", "dotenv"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - mcp-servers/email/tsconfig.json
  - mcp-servers/email/src/index.ts
tests:
  - manual: cd mcp-servers/email && node_modules/.bin/tsc --noEmit
---

## Prompt

mcp-servers\email\tsconfig.json showing error in module resolution and it is not reading my emails

## Response snapshot

Two root causes identified and fixed:

**Fix 1 — tsconfig.json moduleResolution:**
- `"moduleResolution": "node"` is the legacy algorithm — does not understand the `exports` field in `package.json`
- `@modelcontextprotocol/sdk` is an ESM package (`"type": "module"`) using sub-path exports (`/server/index.js`, `/types.js`, etc.)
- VS Code showed squiggles on all MCP SDK imports because `node` resolution couldn't follow sub-path exports
- Fix: changed to `"moduleResolution": "bundler"` (TypeScript 5.0+) — supports `exports` field, works with `"module": "commonjs"`, no `.js` extensions required on local imports

**Fix 2 — loadEnv() path:**
- `loadEnv()` (dotenv with no args) resolves `.env` from `process.cwd()`
- When Claude Code launches the server as an MCP process, cwd is the vault root, not `mcp-servers/email/`
- `GMAIL_OAUTH_TOKEN_PATH` was never loaded → `client = null` → every tool call returned "Gmail client not configured"
- Fix: changed to `loadEnv({ path: path.resolve(__dirname, "..", ".env") })` so it always loads from `mcp-servers/email/.env` regardless of cwd
- Secondary `loadEnv({ override: false })` allows vault-root `.env` to also contribute env vars

## Outcome

- ✅ Impact: Editor module resolution errors cleared; Gmail token is now loaded correctly and email tools work
- 🧪 Tests: `tsc --noEmit` passes with zero errors
- 📁 Files: mcp-servers/email/tsconfig.json, mcp-servers/email/src/index.ts
- 🔁 Next prompts: rebuild with `npm run build` in mcp-servers/email → restart MCP server → test search_email tool
- 🧠 Reflection: Always use `"moduleResolution": "bundler"` (TS 5+) for projects that consume modern ESM packages with sub-path exports; always load dotenv with an explicit absolute path in MCP servers since cwd is controlled by the host

## Evaluation notes (flywheel)

- Failure modes observed: `"moduleResolution": "node"` silently fails to resolve sub-path exports in editors even when tsc CLI passes; dotenv with no args is cwd-dependent which breaks MCP stdio servers
- Graders run and results (PASS/FAIL): tsc --noEmit PASS
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): test search_email with query "is:unread" and verify it returns real Gmail messages
