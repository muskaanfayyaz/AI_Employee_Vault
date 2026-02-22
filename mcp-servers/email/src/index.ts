/**
 * Email MCP Server — stdio transport.
 *
 * Tools exposed:
 *   ping          — health check
 *   send_email    — send a Gmail message (requires approval, FR-017)
 *   draft_email   — create a Gmail draft (safe, no approval)
 *   search_email  — search Gmail using standard search syntax
 *
 * DRY_RUN=true → all tools return success stubs without contacting Gmail.
 *
 * Start:
 *   node dist/index.js
 */
import { config as loadEnv } from "dotenv";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { GmailClient } from "./gmail";
import { handleDraftEmail, handleSearchEmail, handleSendEmail } from "./tools";
import type { EmailToolResult } from "./types";

loadEnv();

const DRY_RUN =
  process.env.DRY_RUN?.toLowerCase() === "true" ||
  process.env.DRY_RUN === "1";

const tokenPath = process.env.GMAIL_OAUTH_TOKEN_PATH ?? "";
const client = tokenPath ? new GmailClient(tokenPath) : null;

// ── MCP Server ───────────────────────────────────────────────────────────────

const server = new Server(
  { name: "email-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

// ── Tool list ─────────────────────────────────────────────────────────────────

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "ping",
      description: "Health check — returns server status and dry_run flag.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "send_email",
      description:
        "Send an email via Gmail. Requires human approval (FR-017). No-op in DRY_RUN mode.",
      inputSchema: {
        type: "object",
        properties: {
          to: { type: "string", description: "Recipient email address" },
          subject: { type: "string", description: "Email subject line" },
          body: { type: "string", description: "Email body (plain text)" },
          cc: { type: "string", description: "CC addresses (optional)", nullable: true },
          bcc: { type: "string", description: "BCC addresses (optional)", nullable: true },
          reply_to_message_id: {
            type: "string",
            description: "Thread message ID to reply under (optional)",
            nullable: true,
          },
        },
        required: ["to", "subject", "body"],
      },
    },
    {
      name: "draft_email",
      description:
        "Create a Gmail draft without sending. Safe to use without approval. No-op in DRY_RUN mode.",
      inputSchema: {
        type: "object",
        properties: {
          to: { type: "string", description: "Recipient email address" },
          subject: { type: "string", description: "Email subject line" },
          body: { type: "string", description: "Email body (plain text)" },
          cc: { type: "string", description: "CC addresses (optional)", nullable: true },
          bcc: { type: "string", description: "BCC addresses (optional)", nullable: true },
        },
        required: ["to", "subject", "body"],
      },
    },
    {
      name: "search_email",
      description:
        "Search Gmail using standard Gmail search syntax. Returns matching email summaries.",
      inputSchema: {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: 'Gmail search query (e.g. "is:unread from:boss@example.com")',
          },
          max_results: {
            type: "number",
            description: "Maximum number of emails to return (default: 10)",
          },
        },
        required: ["query"],
      },
    },
  ],
}));

// ── Tool dispatch ─────────────────────────────────────────────────────────────

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  let result: EmailToolResult | { status: string; server: string; version: string; dry_run: boolean };

  if (name === "ping") {
    result = { status: "ok", server: "email-mcp", version: "0.1.0", dry_run: DRY_RUN };
  } else if (name === "send_email") {
    result = await handleSendEmail(args, client, DRY_RUN);
  } else if (name === "draft_email") {
    result = await handleDraftEmail(args, client, DRY_RUN);
  } else if (name === "search_email") {
    result = await handleSearchEmail(args, client, DRY_RUN);
  } else {
    result = {
      success: false,
      dry_run: DRY_RUN,
      data: null,
      error: `Unknown tool: ${name}`,
    } as EmailToolResult;
  }

  return {
    content: [{ type: "text", text: JSON.stringify(result) }],
  };
});

// ── Entry point ───────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(
    `email-mcp server started | dry_run=${DRY_RUN} | credentials=${tokenPath ? "configured" : "not set"}`
  );
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
