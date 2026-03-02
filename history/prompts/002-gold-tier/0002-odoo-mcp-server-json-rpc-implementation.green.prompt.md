---
id: "0002"
title: odoo-mcp-server-json-rpc-implementation
stage: green
date: 2026-02-26
surface: agent
model: claude-sonnet-4-6
feature: 002-gold-tier
branch: 002-gold-tier
user: muskaan
command: /sp.implement
labels: [green, odoo, mcp-server, json-rpc, typescript, approval-workflow, audit-log]
links:
  spec: specs/002-gold-tier/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - mcp-servers/odoo/src/index.ts
  - mcp-servers/odoo/src/client.ts
  - mcp-servers/odoo/src/tools.ts
  - mcp-servers/odoo/src/types.ts
  - mcp-servers/odoo/src/approval.ts
  - mcp-servers/odoo/src/logger.ts
  - mcp-servers/odoo/package.json
  - mcp-servers/odoo/tsconfig.json
  - mcp-servers/odoo/.env.example
  - mcp-servers/email/tsconfig.json
tests:
  - npx tsc --noEmit (odoo-mcp) — PASS
  - npx tsc emit (odoo-mcp) — PASS (6 modules in dist/)
  - npx tsc --noEmit (email-mcp) — PASS
---

## Prompt

Create Odoo MCP server using JSON-RPC.

Capabilities:
- create_invoice (draft only)
- fetch_transaction
- analyze_subscriptions
- create_payment (requires approval)

Must:
- Never auto-post invoices
- Use approval file system
- Log all actions - Use JSON-RPC

## Response snapshot

Created `mcp-servers/odoo/` (9 files). TypeScript build: PASS. Key design decisions:

- `client.ts`: `OdooClient` uses native `fetch` for JSON-RPC to `POST {url}/jsonrpc`. Handles `common/authenticate` + `object/execute_kw`. Lazy auth (first call triggers authenticate). Credentials sourced from constructor (from .env); never in vault.
- `tools.ts`: All 4 handlers enforce inviolable constraints in code: `create_invoice` forces `state=draft` and never calls `action_post`; `create_payment` writes approval file and returns `requires_approval=true` without touching Odoo.
- `approval.ts`: Writes YAML-frontmatter `.md` files to `VAULT_PATH/Pending_Approval/` matching the vault item format (FR-002).
- `logger.ts`: Appends Gold Tier extended log entries to `VAULT_PATH/Logs/YYYY-MM-DD.json` (FR-038 + FR-G046).
- Fixed pre-existing `moduleResolution: "bundler"` error in both email and odoo tsconfigs.

## Outcome

- ✅ Impact: Odoo MCP server fully implemented and compiled. All inviolable constraints enforced at handler level.
- 🧪 Tests: tsc --noEmit PASS; tsc emit PASS (6 modules); email server tsconfig fix verified.
- 📁 Files: 9 new files in mcp-servers/odoo/; 1 fix in mcp-servers/email/tsconfig.json
- 🔁 Next prompts: Add vitest unit tests; register in `.claude/settings.json`; run `/sp.plan` for Gold Tier architecture
- 🧠 Reflection: Inviolable constraints (no auto-post, no direct payment write) are in handler code paths, not config — audit-visible and harder to bypass accidentally.

## Evaluation notes (flywheel)

- Failure modes observed: tsconfig moduleResolution bundler+commonjs incompatible in TS 5.5+ — pre-existing in email server, fixed in both
- Graders run and results (PASS/FAIL): tsc --noEmit PASS; tsc emit PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Add fetch_invoices tool (FR-G004) to complete read-side Odoo capability
