/**
 * Odoo MCP Server — stdio transport.
 *
 * Tools exposed:
 *   ping                   — health check
 *   create_invoice         — create a DRAFT invoice only (NEVER auto-posts, FR-G005)
 *   fetch_transactions     — read account.move.line entries (read-only)
 *   analyze_subscriptions  — audit sale.subscription records for anomalies (read-only)
 *   create_payment         — write approval request file only (NEVER writes to Odoo, FR-G006)
 *
 * Security invariants:
 *   • No credential values appear in tool results, logs, or vault files (FR-G040).
 *   • create_invoice: state is always 'draft'; action_post is never called.
 *   • create_payment: writes Pending_Approval file only; no Odoo write.
 *   • DRY_RUN=true → all tools return stubs without contacting Odoo.
 *
 * Start:
 *   node dist/index.js
 */
import path from "path";
import { config as loadEnv } from "dotenv";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { OdooClient } from "./client";
import {
  handleCreateInvoice,
  handleFetchTransactions,
  handleAnalyzeSubscriptions,
  handleCreatePayment,
  handleFetchInvoices,
  handleFetchPayments,
  handleFetchSubscriptions,
  handleFetchJournalEntries,
} from "./tools";
import type { OdooToolResult } from "./types";

// ── Environment ──────────────────────────────────────────────────────────────

// Load .env from the mcp-servers/odoo directory first.
loadEnv({ path: path.resolve(__dirname, "..", ".env") });
// Allow vault-root .env to supply shared settings without overriding.
loadEnv({ override: false });

const DRY_RUN =
  process.env.DRY_RUN?.toLowerCase() === "true" ||
  process.env.DRY_RUN === "1";

const ODOO_URL = process.env.ODOO_URL ?? "";
const ODOO_DB = process.env.ODOO_DB ?? "";
const ODOO_USERNAME = process.env.ODOO_USERNAME ?? "";
const ODOO_API_KEY = process.env.ODOO_API_KEY ?? "";
const VAULT_PATH = process.env.VAULT_PATH ?? path.resolve(__dirname, "..", "..", "..");

// Build client — null when credentials are not set (tools degrade gracefully).
const client =
  ODOO_URL && ODOO_DB && ODOO_USERNAME && ODOO_API_KEY
    ? new OdooClient(ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY)
    : null;

// ── MCP Server ───────────────────────────────────────────────────────────────

const server = new Server(
  { name: "odoo-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

// ── Tool list ─────────────────────────────────────────────────────────────────

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "ping",
      description:
        "Health check — returns server status, dry_run flag, and Odoo connectivity state.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "create_invoice",
      description:
        "Create a DRAFT invoice in Odoo (account.move with move_type=out_invoice). " +
        "The invoice is ALWAYS created in draft state — it is NEVER posted automatically. " +
        "Posting requires a separate human-approved workflow (FR-G005). " +
        "No approval required for draft creation.",
      inputSchema: {
        type: "object",
        properties: {
          partner_id: {
            type: "number",
            description: "Odoo res.partner record id (customer)",
          },
          invoice_date: {
            type: "string",
            description: "Invoice date in YYYY-MM-DD format (optional)",
          },
          narration: {
            type: "string",
            description: "Optional notes or narration on the invoice",
          },
          invoice_line_ids: {
            type: "array",
            description: "Invoice line items (at least one required)",
            items: {
              type: "object",
              properties: {
                product_id: {
                  type: "number",
                  description: "Odoo product.product id (optional)",
                },
                name: {
                  type: "string",
                  description: "Line description",
                },
                quantity: { type: "number", description: "Quantity" },
                price_unit: { type: "number", description: "Unit price" },
                account_id: {
                  type: "number",
                  description: "Odoo account.account id (optional)",
                },
              },
              required: ["name", "quantity", "price_unit"],
            },
          },
          currency_id: {
            type: "number",
            description: "Odoo res.currency id (optional — defaults to company currency)",
          },
        },
        required: ["partner_id", "invoice_line_ids"],
      },
    },
    {
      name: "fetch_transactions",
      description:
        "Fetch posted account.move.line transaction entries from Odoo. " +
        "Read-only operation — no approval required.",
      inputSchema: {
        type: "object",
        properties: {
          date_from: {
            type: "string",
            description: "Start date YYYY-MM-DD (optional)",
          },
          date_to: {
            type: "string",
            description: "End date YYYY-MM-DD (optional)",
          },
          journal_type: {
            type: "string",
            enum: ["bank", "cash", "sale", "purchase", "general"],
            description: "Filter by journal type (optional)",
          },
          limit: {
            type: "number",
            description: "Max records to return (default: 50)",
          },
          offset: {
            type: "number",
            description: "Pagination offset (default: 0)",
          },
        },
      },
    },
    {
      name: "analyze_subscriptions",
      description:
        "Analyse sale.subscription records in Odoo for anomalies: overdue renewals, " +
        "amount deviations from historical average. " +
        "Read-only — does NOT modify any Odoo record. " +
        "Returns a structured anomaly report.",
      inputSchema: {
        type: "object",
        properties: {
          overdue_days: {
            type: "number",
            description:
              "Flag subscriptions overdue by at least this many days (default: 0 = any overdue)",
          },
          amount_deviation_pct: {
            type: "number",
            description:
              "Flag subscriptions whose recurring amount deviates more than this % from the average (default: 20)",
          },
          limit: {
            type: "number",
            description: "Max subscription records to analyse (default: 200)",
          },
        },
      },
    },
    {
      name: "fetch_invoices",
      description:
        "Fetch invoice/bill records from Odoo (account.move). " +
        "Read-only — no approval required (FR-G002, FR-G004). " +
        "Filter by move_type, state, partner, and date range.",
      inputSchema: {
        type: "object",
        properties: {
          move_type: { type: "string", enum: ["out_invoice", "in_invoice", "out_refund", "in_refund"], description: "Invoice type (optional — all types if omitted)" },
          state: { type: "string", enum: ["draft", "posted", "cancel"], description: "Filter by state (optional)" },
          partner_id: { type: "number", description: "Filter by Odoo partner id (optional)" },
          date_from: { type: "string", description: "Start date YYYY-MM-DD (optional)" },
          date_to: { type: "string", description: "End date YYYY-MM-DD (optional)" },
          limit: { type: "number", description: "Max records (default 50)" },
          offset: { type: "number", description: "Pagination offset (default 0)" },
        },
      },
    },
    {
      name: "fetch_payments",
      description:
        "Fetch payment records from Odoo (account.payment). " +
        "Read-only — no approval required (FR-G002, FR-G004).",
      inputSchema: {
        type: "object",
        properties: {
          payment_type: { type: "string", enum: ["inbound", "outbound"], description: "Payment direction (optional)" },
          state: { type: "string", enum: ["draft", "posted", "sent", "reconciled", "cancelled"], description: "Filter by state (optional)" },
          partner_id: { type: "number", description: "Filter by partner id (optional)" },
          date_from: { type: "string", description: "Start date YYYY-MM-DD (optional)" },
          date_to: { type: "string", description: "End date YYYY-MM-DD (optional)" },
          limit: { type: "number", description: "Max records (default 50)" },
          offset: { type: "number", description: "Pagination offset (default 0)" },
        },
      },
    },
    {
      name: "fetch_subscriptions",
      description:
        "List sale.subscription records from Odoo. " +
        "Read-only — no approval required (FR-G002, FR-G004). " +
        "Use analyze_subscriptions for anomaly detection.",
      inputSchema: {
        type: "object",
        properties: {
          state: { type: "string", description: "Filter by stage name (optional)" },
          partner_id: { type: "number", description: "Filter by partner id (optional)" },
          limit: { type: "number", description: "Max records (default 100)" },
          offset: { type: "number", description: "Pagination offset (default 0)" },
        },
      },
    },
    {
      name: "fetch_journal_entries",
      description:
        "Fetch accounting journal entries from Odoo (account.move with move_type=entry). " +
        "Read-only — no approval required (FR-G002, FR-G004).",
      inputSchema: {
        type: "object",
        properties: {
          journal_id: { type: "number", description: "Filter by journal id (optional)" },
          state: { type: "string", enum: ["draft", "posted"], description: "Filter by state (optional)" },
          date_from: { type: "string", description: "Start date YYYY-MM-DD (optional)" },
          date_to: { type: "string", description: "End date YYYY-MM-DD (optional)" },
          limit: { type: "number", description: "Max records (default 50)" },
          offset: { type: "number", description: "Pagination offset (default 0)" },
        },
      },
    },
    {
      name: "create_payment",
      description:
        "Request creation of a payment in Odoo. " +
        "REQUIRES HUMAN APPROVAL — this tool writes an approval request file to " +
        "the vault's Pending_Approval folder and returns requires_approval=true. " +
        "NO Odoo write occurs until the human approves the vault item (FR-G006, FR-G009).",
      inputSchema: {
        type: "object",
        properties: {
          partner_id: {
            type: "number",
            description: "Odoo res.partner id",
          },
          amount: {
            type: "number",
            description: "Payment amount (must be positive)",
          },
          currency_code: {
            type: "string",
            description: "ISO 4217 currency code e.g. USD (informational, optional)",
          },
          payment_date: {
            type: "string",
            description: "Payment date YYYY-MM-DD",
          },
          journal_id: {
            type: "number",
            description: "Odoo account.journal id for the payment",
          },
          memo: {
            type: "string",
            description: "Payment memo / communication (optional)",
          },
          payment_type: {
            type: "string",
            enum: ["inbound", "outbound"],
            description: "inbound = customer receipt, outbound = vendor payment",
          },
          partner_type: {
            type: "string",
            enum: ["customer", "supplier"],
            description: "Partner type",
          },
        },
        required: [
          "partner_id",
          "amount",
          "payment_date",
          "journal_id",
          "payment_type",
          "partner_type",
        ],
      },
    },
  ],
}));

// ── Tool dispatch ─────────────────────────────────────────────────────────────

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  let result:
    | OdooToolResult
    | { status: string; server: string; version: string; dry_run: boolean; odoo_configured: boolean };

  if (name === "ping") {
    result = {
      status: "ok",
      server: "odoo-mcp",
      version: "0.1.0",
      dry_run: DRY_RUN,
      odoo_configured: client !== null,
    };
  } else if (name === "create_invoice") {
    result = await handleCreateInvoice(args, client, DRY_RUN, VAULT_PATH);
  } else if (name === "fetch_transactions") {
    result = await handleFetchTransactions(args, client, DRY_RUN, VAULT_PATH);
  } else if (name === "analyze_subscriptions") {
    result = await handleAnalyzeSubscriptions(args, client, DRY_RUN, VAULT_PATH);
  } else if (name === "fetch_invoices") {
    result = await handleFetchInvoices(args, client, DRY_RUN, VAULT_PATH);
  } else if (name === "fetch_payments") {
    result = await handleFetchPayments(args, client, DRY_RUN, VAULT_PATH);
  } else if (name === "fetch_subscriptions") {
    result = await handleFetchSubscriptions(args, client, DRY_RUN, VAULT_PATH);
  } else if (name === "fetch_journal_entries") {
    result = await handleFetchJournalEntries(args, client, DRY_RUN, VAULT_PATH);
  } else if (name === "create_payment") {
    result = await handleCreatePayment(args, client, DRY_RUN, VAULT_PATH);
  } else {
    result = {
      success: false,
      dry_run: DRY_RUN,
      requires_approval: false,
      data: null,
      error: `Unknown tool: ${name}`,
    } as OdooToolResult;
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
    [
      `odoo-mcp server started`,
      `dry_run=${DRY_RUN}`,
      `odoo_configured=${client !== null}`,
      `vault_path=${VAULT_PATH}`,
    ].join(" | ")
  );
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
