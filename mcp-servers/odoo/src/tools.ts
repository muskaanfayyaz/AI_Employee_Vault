/**
 * Tool handlers for the Odoo MCP server.
 *
 * Each handler:
 *   1. Validates input with Zod (returns structured failure on bad args).
 *   2. Short-circuits with a dry-run stub when dryRun=true.
 *   3. For approval-required operations: writes an approval file and returns
 *      requires_approval=true WITHOUT contacting Odoo (FR-G006, FR-G009).
 *   4. For read operations: calls the Odoo client, wraps errors.
 *   5. Logs every action to the vault audit log (FR-G046).
 *
 * Inviolable constraints (enforced here, not just in config):
 *   • create_invoice NEVER calls action_post — draft only (FR-G005).
 *   • create_payment NEVER calls Odoo directly — approval file only (FR-G006).
 */
import { z } from "zod";
import path from "path";
import type { OdooClientInterface, OdooToolResult } from "./types";
import { writeApprovalRequest } from "./approval";
import { appendLog, buildEntry } from "./logger";

// ── Response helpers ────────────────────────────────────────────────────────

function ok(
  data: Record<string, unknown>,
  dryRun: boolean
): OdooToolResult {
  return {
    success: true,
    dry_run: dryRun,
    requires_approval: false,
    data,
    error: null,
  };
}

function fail(message: string, dryRun: boolean): OdooToolResult {
  return {
    success: false,
    dry_run: dryRun,
    requires_approval: false,
    data: null,
    error: message,
  };
}

function pendingApproval(
  approvalFile: string,
  summary: string,
  dryRun: boolean
): OdooToolResult {
  return {
    success: true,
    dry_run: dryRun,
    requires_approval: true,
    data: { status: "approval_pending", approval_file: approvalFile, summary },
    approval_file: approvalFile,
    error: null,
  };
}

// ── Zod schemas ─────────────────────────────────────────────────────────────

const InvoiceLineSchema = z.object({
  product_id: z.number().int().positive().optional(),
  name: z.string().min(1, "'name' must not be empty"),
  quantity: z.number().positive("'quantity' must be positive"),
  price_unit: z.number().nonnegative("'price_unit' must be >= 0"),
  account_id: z.number().int().positive().optional(),
});

export const CreateInvoiceSchema = z.object({
  partner_id: z.number().int().positive("'partner_id' must be a valid Odoo partner id"),
  invoice_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "'invoice_date' must be YYYY-MM-DD")
    .optional(),
  narration: z.string().optional(),
  invoice_line_ids: z
    .array(InvoiceLineSchema)
    .min(1, "At least one invoice line is required"),
  currency_id: z.number().int().positive().optional(),
});

export const FetchTransactionsSchema = z.object({
  date_from: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "'date_from' must be YYYY-MM-DD")
    .optional(),
  date_to: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "'date_to' must be YYYY-MM-DD")
    .optional(),
  journal_type: z
    .enum(["bank", "cash", "sale", "purchase", "general"])
    .optional(),
  limit: z.number().int().positive().optional().default(50),
  offset: z.number().int().nonnegative().optional().default(0),
});

export const AnalyzeSubscriptionsSchema = z.object({
  overdue_days: z.number().int().nonnegative().optional().default(0),
  amount_deviation_pct: z.number().positive().optional().default(20),
  limit: z.number().int().positive().optional().default(200),
});

export const CreatePaymentSchema = z.object({
  partner_id: z.number().int().positive("'partner_id' must be a valid Odoo partner id"),
  amount: z.number().positive("'amount' must be positive"),
  currency_code: z.string().length(3).optional(),
  payment_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "'payment_date' must be YYYY-MM-DD"),
  journal_id: z.number().int().positive("'journal_id' must be a valid Odoo journal id"),
  memo: z.string().optional(),
  payment_type: z.enum(["inbound", "outbound"]),
  partner_type: z.enum(["customer", "supplier"]),
});

// ── Handlers ────────────────────────────────────────────────────────────────

/**
 * create_invoice — creates a DRAFT invoice in Odoo.
 *
 * INVIOLABLE: action_post is NEVER called. The invoice remains in 'draft'
 * state regardless of input. Posting requires a separate human-approved
 * workflow (FR-G005).
 */
export async function handleCreateInvoice(
  args: unknown,
  client: OdooClientInterface | null,
  dryRun: boolean,
  vaultPath: string
): Promise<OdooToolResult> {
  const t0 = Date.now();
  const parsed = CreateInvoiceSchema.safeParse(args);
  if (!parsed.success) {
    return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  }

  const { partner_id, invoice_date, narration, invoice_line_ids, currency_id } =
    parsed.data;

  // Build Odoo vals — state is forced to 'draft'; action_post is never called.
  const vals: Record<string, unknown> = {
    move_type: "out_invoice",
    partner_id,
    invoice_date: invoice_date ?? false,
    narration: narration ?? false,
    invoice_line_ids: invoice_line_ids.map((line) => [
      0,
      0,
      {
        ...(line.product_id ? { product_id: line.product_id } : {}),
        name: line.name,
        quantity: line.quantity,
        price_unit: line.price_unit,
        ...(line.account_id ? { account_id: line.account_id } : {}),
      },
    ]),
    ...(currency_id ? { currency_id } : {}),
  };

  if (dryRun) {
    appendLog(vaultPath, buildEntry(
      "create_invoice",
      "Draft invoice creation (DRY_RUN)",
      "dry_run",
      Date.now() - t0,
      `[DRY_RUN] Would create draft invoice for partner_id=${partner_id}`,
      { dry_run: true, approval_threshold: "auto" }
    ));
    return ok(
      {
        invoice_id: "dry-run-id",
        state: "draft",
        message: "[DRY_RUN] Draft invoice would be created — no Odoo write performed.",
      },
      true
    );
  }

  if (!client) {
    return fail("Odoo client not configured. Set ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY in .env.", false);
  }

  try {
    const invoiceId = await client.create("account.move", vals);
    const duration = Date.now() - t0;

    appendLog(vaultPath, buildEntry(
      "create_invoice",
      `Draft invoice created: account.move id=${invoiceId}`,
      "success",
      duration,
      `Draft invoice created for partner_id=${partner_id}. State=draft. action_post NOT called.`,
      {
        item_id: String(invoiceId),
        approval: { required: false, status: "auto", approver: "system" },
        approval_threshold: "auto",
      }
    ));

    return ok(
      {
        invoice_id: invoiceId,
        state: "draft",
        message: "Draft invoice created. Invoice is in DRAFT state — it has NOT been posted.",
        partner_id,
      },
      false
    );
  } catch (err) {
    appendLog(vaultPath, buildEntry(
      "create_invoice",
      "Draft invoice creation failed",
      "failure",
      Date.now() - t0,
      String(err),
      { approval_threshold: "auto" }
    ));
    return fail(String(err), false);
  }
}

/**
 * fetch_transactions — reads account.move.line entries from Odoo.
 *
 * Read-only operation; no approval required (FR-G018 / auto_approved_actions).
 */
export async function handleFetchTransactions(
  args: unknown,
  client: OdooClientInterface | null,
  dryRun: boolean,
  vaultPath: string
): Promise<OdooToolResult> {
  const t0 = Date.now();
  const parsed = FetchTransactionsSchema.safeParse(args);
  if (!parsed.success) {
    return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  }

  const { date_from, date_to, journal_type, limit, offset } = parsed.data;

  if (dryRun) {
    appendLog(vaultPath, buildEntry(
      "fetch_transactions",
      "Fetch transactions (DRY_RUN)",
      "dry_run",
      Date.now() - t0,
      `[DRY_RUN] Would fetch transactions date_from=${date_from ?? "any"} date_to=${date_to ?? "any"}`,
      { dry_run: true }
    ));
    return ok({ transactions: [], total: 0, message: "[DRY_RUN] No Odoo read performed." }, true);
  }

  if (!client) {
    return fail("Odoo client not configured.", false);
  }

  try {
    // Build domain
    const domain: unknown[] = [["move_id.state", "=", "posted"]];
    if (date_from) domain.push(["date", ">=", date_from]);
    if (date_to) domain.push(["date", "<=", date_to]);
    if (journal_type) domain.push(["journal_id.type", "=", journal_type]);

    const fields = [
      "id",
      "name",
      "date",
      "account_id",
      "journal_id",
      "debit",
      "credit",
      "amount_currency",
      "partner_id",
      "move_name",
    ];

    const lines = await client.searchRead("account.move.line", domain, fields, {
      limit,
      offset,
      order: "date desc",
    });

    const duration = Date.now() - t0;
    appendLog(vaultPath, buildEntry(
      "fetch_transactions",
      `Fetched ${lines.length} transaction lines`,
      "success",
      duration,
      `date_from=${date_from ?? "any"} date_to=${date_to ?? "any"} journal_type=${journal_type ?? "any"} count=${lines.length}`,
      { approval_threshold: "auto" }
    ));

    return ok({ transactions: lines, total: lines.length }, false);
  } catch (err) {
    appendLog(vaultPath, buildEntry(
      "fetch_transactions",
      "Fetch transactions failed",
      "failure",
      Date.now() - t0,
      String(err)
    ));
    return fail(String(err), false);
  }
}

/**
 * analyze_subscriptions — reads subscription records from Odoo and returns
 * a structured anomaly report.
 *
 * Read-only. Anomaly detection only — does NOT modify any Odoo record.
 * Supports Odoo's sale.subscription model (Odoo 14–16 Enterprise).
 */
export async function handleAnalyzeSubscriptions(
  args: unknown,
  client: OdooClientInterface | null,
  dryRun: boolean,
  vaultPath: string
): Promise<OdooToolResult> {
  const t0 = Date.now();
  const parsed = AnalyzeSubscriptionsSchema.safeParse(args);
  if (!parsed.success) {
    return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  }

  const { overdue_days, amount_deviation_pct, limit } = parsed.data;

  if (dryRun) {
    appendLog(vaultPath, buildEntry(
      "analyze_subscriptions",
      "Analyze subscriptions (DRY_RUN)",
      "dry_run",
      Date.now() - t0,
      "[DRY_RUN] Would analyse subscriptions — no Odoo read performed.",
      { dry_run: true }
    ));
    return ok({
      total_analysed: 0,
      anomalies: [],
      message: "[DRY_RUN] No Odoo read performed.",
    }, true);
  }

  if (!client) {
    return fail("Odoo client not configured.", false);
  }

  try {
    // Read active subscriptions. Model: sale.subscription (Odoo 14-16 Enterprise).
    // Note: some Odoo versions use 'sale.order' with is_subscription=True.
    const fields = [
      "id",
      "name",
      "partner_id",
      "stage_id",
      "recurring_next_date",
      "recurring_total",
      "date_start",
    ];

    const domain: unknown[] = [];
    const subscriptions = await client.searchRead(
      "sale.subscription",
      domain,
      fields,
      { limit, order: "recurring_next_date asc" }
    );

    const today = new Date();
    const todayStr = today.toISOString().split("T")[0];
    const overdueThreshold = new Date(today);
    overdueThreshold.setDate(overdueThreshold.getDate() - overdue_days);

    // Compute average recurring_total for deviation detection
    const amounts = subscriptions
      .map((s) => s.recurring_total as number)
      .filter((a) => typeof a === "number" && a > 0);
    const avgAmount =
      amounts.length > 0
        ? amounts.reduce((a, b) => a + b, 0) / amounts.length
        : 0;

    const anomalies: Record<string, unknown>[] = [];

    for (const sub of subscriptions) {
      const issues: string[] = [];

      // Overdue renewal
      const nextDate = sub.recurring_next_date as string | false;
      if (nextDate && nextDate < todayStr) {
        const msOverdue =
          today.getTime() - new Date(nextDate).getTime();
        const daysOverdue = Math.floor(msOverdue / 86_400_000);
        if (daysOverdue >= overdue_days) {
          issues.push(`Overdue renewal by ${daysOverdue} day(s) (next date: ${nextDate})`);
        }
      }

      // Amount deviation
      const amount = sub.recurring_total as number;
      if (avgAmount > 0 && typeof amount === "number") {
        const deviation = Math.abs(amount - avgAmount) / avgAmount * 100;
        if (deviation > amount_deviation_pct) {
          issues.push(
            `Amount ${amount} deviates ${deviation.toFixed(1)}% from avg ${avgAmount.toFixed(2)}`
          );
        }
      }

      if (issues.length > 0) {
        anomalies.push({
          subscription_id: sub.id,
          name: sub.name,
          partner: sub.partner_id,
          recurring_total: sub.recurring_total,
          recurring_next_date: sub.recurring_next_date,
          anomalies: issues,
        });
      }
    }

    const duration = Date.now() - t0;
    appendLog(vaultPath, buildEntry(
      "analyze_subscriptions",
      `Subscription audit: ${subscriptions.length} analysed, ${anomalies.length} anomalies`,
      "success",
      duration,
      `Analysed ${subscriptions.length} subscriptions. Found ${anomalies.length} anomalies.`,
      { approval_threshold: "auto" }
    ));

    return ok(
      {
        total_analysed: subscriptions.length,
        total_anomalies: anomalies.length,
        avg_recurring_total: avgAmount,
        anomalies,
        message: anomalies.length === 0
          ? "No anomalies detected."
          : `${anomalies.length} anomaly(ies) detected. Review the 'anomalies' array.`,
      },
      false
    );
  } catch (err) {
    appendLog(vaultPath, buildEntry(
      "analyze_subscriptions",
      "Subscription analysis failed",
      "failure",
      Date.now() - t0,
      String(err)
    ));
    return fail(String(err), false);
  }
}

// ── FR-G004 Read-only tools ──────────────────────────────────────────────────

export const FetchInvoicesSchema = z.object({
  move_type: z
    .enum(["out_invoice", "in_invoice", "out_refund", "in_refund"])
    .optional(),
  state: z.enum(["draft", "posted", "cancel"]).optional(),
  partner_id: z.number().int().positive().optional(),
  date_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  date_to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  limit: z.number().int().positive().optional().default(50),
  offset: z.number().int().nonnegative().optional().default(0),
});

export const FetchPaymentsSchema = z.object({
  payment_type: z.enum(["inbound", "outbound"]).optional(),
  state: z
    .enum(["draft", "posted", "sent", "reconciled", "cancelled"])
    .optional(),
  partner_id: z.number().int().positive().optional(),
  date_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  date_to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  limit: z.number().int().positive().optional().default(50),
  offset: z.number().int().nonnegative().optional().default(0),
});

export const FetchSubscriptionsSchema = z.object({
  state: z.string().optional(),
  partner_id: z.number().int().positive().optional(),
  limit: z.number().int().positive().optional().default(100),
  offset: z.number().int().nonnegative().optional().default(0),
});

export const FetchJournalEntriesSchema = z.object({
  journal_id: z.number().int().positive().optional(),
  state: z.enum(["draft", "posted"]).optional(),
  date_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  date_to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  limit: z.number().int().positive().optional().default(50),
  offset: z.number().int().nonnegative().optional().default(0),
});

/**
 * fetch_invoices — read account.move invoice/bill records from Odoo.
 * Read-only; no approval required (FR-G002, FR-G004).
 */
export async function handleFetchInvoices(
  args: unknown,
  client: OdooClientInterface | null,
  dryRun: boolean,
  vaultPath: string
): Promise<OdooToolResult> {
  const t0 = Date.now();
  const parsed = FetchInvoicesSchema.safeParse(args);
  if (!parsed.success) return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  const { move_type, state, partner_id, date_from, date_to, limit, offset } = parsed.data;

  if (dryRun) {
    appendLog(vaultPath, buildEntry("fetch_invoices", "Fetch invoices (DRY_RUN)", "dry_run", Date.now() - t0,
      "[DRY_RUN] Would fetch invoices — no Odoo read performed.", { dry_run: true, approval_threshold: "auto" }));
    return ok({ invoices: [], total: 0, message: "[DRY_RUN] No Odoo read performed." }, true);
  }
  if (!client) return fail("Odoo client not configured.", false);

  try {
    const domain: unknown[] = [["move_type", "in", move_type ? [move_type] : ["out_invoice", "in_invoice", "out_refund", "in_refund"]]];
    if (state) domain.push(["state", "=", state]);
    if (partner_id) domain.push(["partner_id", "=", partner_id]);
    if (date_from) domain.push(["invoice_date", ">=", date_from]);
    if (date_to) domain.push(["invoice_date", "<=", date_to]);

    const fields = ["id", "name", "move_type", "state", "partner_id", "invoice_date", "amount_total", "amount_residual", "currency_id", "ref"];
    const invoices = await client.searchRead("account.move", domain, fields, { limit, offset, order: "invoice_date desc" });
    const duration = Date.now() - t0;
    appendLog(vaultPath, buildEntry("fetch_invoices", `Fetched ${invoices.length} invoice(s)`, "success", duration,
      `move_type=${move_type ?? "any"} state=${state ?? "any"} count=${invoices.length}`, { approval_threshold: "auto" }));
    return ok({ invoices, total: invoices.length }, false);
  } catch (err) {
    appendLog(vaultPath, buildEntry("fetch_invoices", "Fetch invoices failed", "failure", Date.now() - t0, String(err)));
    return fail(String(err), false);
  }
}

/**
 * fetch_payments — read account.payment records from Odoo.
 * Read-only; no approval required (FR-G002, FR-G004).
 */
export async function handleFetchPayments(
  args: unknown,
  client: OdooClientInterface | null,
  dryRun: boolean,
  vaultPath: string
): Promise<OdooToolResult> {
  const t0 = Date.now();
  const parsed = FetchPaymentsSchema.safeParse(args);
  if (!parsed.success) return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  const { payment_type, state, partner_id, date_from, date_to, limit, offset } = parsed.data;

  if (dryRun) {
    appendLog(vaultPath, buildEntry("fetch_payments", "Fetch payments (DRY_RUN)", "dry_run", Date.now() - t0,
      "[DRY_RUN] Would fetch payments — no Odoo read performed.", { dry_run: true, approval_threshold: "auto" }));
    return ok({ payments: [], total: 0, message: "[DRY_RUN] No Odoo read performed." }, true);
  }
  if (!client) return fail("Odoo client not configured.", false);

  try {
    const domain: unknown[] = [];
    if (payment_type) domain.push(["payment_type", "=", payment_type]);
    if (state) domain.push(["state", "=", state]);
    if (partner_id) domain.push(["partner_id", "=", partner_id]);
    if (date_from) domain.push(["date", ">=", date_from]);
    if (date_to) domain.push(["date", "<=", date_to]);

    const fields = ["id", "name", "payment_type", "state", "partner_id", "amount", "currency_id", "date", "journal_id", "ref"];
    const payments = await client.searchRead("account.payment", domain, fields, { limit, offset, order: "date desc" });
    const duration = Date.now() - t0;
    appendLog(vaultPath, buildEntry("fetch_payments", `Fetched ${payments.length} payment(s)`, "success", duration,
      `payment_type=${payment_type ?? "any"} state=${state ?? "any"} count=${payments.length}`, { approval_threshold: "auto" }));
    return ok({ payments, total: payments.length }, false);
  } catch (err) {
    appendLog(vaultPath, buildEntry("fetch_payments", "Fetch payments failed", "failure", Date.now() - t0, String(err)));
    return fail(String(err), false);
  }
}

/**
 * fetch_subscriptions — list sale.subscription records from Odoo.
 * Read-only; no approval required (FR-G002, FR-G004).
 */
export async function handleFetchSubscriptions(
  args: unknown,
  client: OdooClientInterface | null,
  dryRun: boolean,
  vaultPath: string
): Promise<OdooToolResult> {
  const t0 = Date.now();
  const parsed = FetchSubscriptionsSchema.safeParse(args);
  if (!parsed.success) return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  const { state, partner_id, limit, offset } = parsed.data;

  if (dryRun) {
    appendLog(vaultPath, buildEntry("fetch_subscriptions", "Fetch subscriptions (DRY_RUN)", "dry_run", Date.now() - t0,
      "[DRY_RUN] Would fetch subscriptions — no Odoo read performed.", { dry_run: true, approval_threshold: "auto" }));
    return ok({ subscriptions: [], total: 0, message: "[DRY_RUN] No Odoo read performed." }, true);
  }
  if (!client) return fail("Odoo client not configured.", false);

  try {
    const domain: unknown[] = [];
    if (state) domain.push(["stage_id.name", "ilike", state]);
    if (partner_id) domain.push(["partner_id", "=", partner_id]);

    const fields = ["id", "name", "partner_id", "stage_id", "recurring_next_date", "recurring_total", "date_start", "date", "analytic_account_id"];
    const subscriptions = await client.searchRead("sale.subscription", domain, fields, { limit, offset, order: "recurring_next_date asc" });
    const duration = Date.now() - t0;
    appendLog(vaultPath, buildEntry("fetch_subscriptions", `Fetched ${subscriptions.length} subscription(s)`, "success", duration,
      `state=${state ?? "any"} count=${subscriptions.length}`, { approval_threshold: "auto" }));
    return ok({ subscriptions, total: subscriptions.length }, false);
  } catch (err) {
    appendLog(vaultPath, buildEntry("fetch_subscriptions", "Fetch subscriptions failed", "failure", Date.now() - t0, String(err)));
    return fail(String(err), false);
  }
}

/**
 * fetch_journal_entries — read account.move journal entry records.
 * Read-only; no approval required (FR-G002, FR-G004).
 */
export async function handleFetchJournalEntries(
  args: unknown,
  client: OdooClientInterface | null,
  dryRun: boolean,
  vaultPath: string
): Promise<OdooToolResult> {
  const t0 = Date.now();
  const parsed = FetchJournalEntriesSchema.safeParse(args);
  if (!parsed.success) return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  const { journal_id, state, date_from, date_to, limit, offset } = parsed.data;

  if (dryRun) {
    appendLog(vaultPath, buildEntry("fetch_journal_entries", "Fetch journal entries (DRY_RUN)", "dry_run", Date.now() - t0,
      "[DRY_RUN] Would fetch journal entries — no Odoo read performed.", { dry_run: true, approval_threshold: "auto" }));
    return ok({ entries: [], total: 0, message: "[DRY_RUN] No Odoo read performed." }, true);
  }
  if (!client) return fail("Odoo client not configured.", false);

  try {
    const domain: unknown[] = [["move_type", "=", "entry"]];
    if (journal_id) domain.push(["journal_id", "=", journal_id]);
    if (state) domain.push(["state", "=", state]);
    if (date_from) domain.push(["date", ">=", date_from]);
    if (date_to) domain.push(["date", "<=", date_to]);

    const fields = ["id", "name", "date", "journal_id", "state", "ref", "amount_total_signed", "move_type"];
    const entries = await client.searchRead("account.move", domain, fields, { limit, offset, order: "date desc" });
    const duration = Date.now() - t0;
    appendLog(vaultPath, buildEntry("fetch_journal_entries", `Fetched ${entries.length} journal entry(ies)`, "success", duration,
      `journal_id=${journal_id ?? "any"} state=${state ?? "any"} count=${entries.length}`, { approval_threshold: "auto" }));
    return ok({ entries, total: entries.length }, false);
  } catch (err) {
    appendLog(vaultPath, buildEntry("fetch_journal_entries", "Fetch journal entries failed", "failure", Date.now() - t0, String(err)));
    return fail(String(err), false);
  }
}

/**
 * create_payment — writes an approval file to VAULT_PATH/Pending_Approval/.
 *
 * INVIOLABLE: This handler NEVER creates a payment in Odoo directly.
 * It writes an approval request and returns requires_approval=true.
 * Only after a human approves the vault item should a separate execution
 * step call Odoo (FR-G006, FR-G009).
 */
export async function handleCreatePayment(
  args: unknown,
  client: OdooClientInterface | null,
  dryRun: boolean,
  vaultPath: string
): Promise<OdooToolResult> {
  const t0 = Date.now();
  const parsed = CreatePaymentSchema.safeParse(args);
  if (!parsed.success) {
    return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  }

  const {
    partner_id,
    amount,
    currency_code,
    payment_date,
    journal_id,
    memo,
    payment_type,
    partner_type,
  } = parsed.data;

  const odooPayload: Record<string, unknown> = {
    partner_id,
    amount,
    payment_date,
    journal_id,
    payment_type,
    partner_type,
    ...(currency_code ? { _currency_code_hint: currency_code } : {}),
    ...(memo ? { ref: memo } : {}),
  };

  if (dryRun) {
    appendLog(vaultPath, buildEntry(
      "create_payment",
      "Payment approval request (DRY_RUN)",
      "dry_run",
      Date.now() - t0,
      `[DRY_RUN] Would write approval request for payment: partner_id=${partner_id} amount=${amount}`,
      { dry_run: true, approval_threshold: "approval_required" }
    ));
    return ok(
      {
        status: "dry_run",
        message: "[DRY_RUN] Approval file would be written — no Odoo write, no file created.",
        payment_type,
        amount,
        partner_id,
      },
      true
    );
  }

  // Write approval request — do NOT call Odoo (FR-G006)
  try {
    const approvalFile = writeApprovalRequest(vaultPath, {
      proposed_action: `Create ${payment_type} payment of ${amount}${currency_code ? ` ${currency_code}` : ""} for partner_id=${partner_id} on ${payment_date}`,
      reasoning: `A ${payment_type} payment of ${amount} has been requested for partner ${partner_id}. Per FR-G006 and the approval policy, all payment creation requires human approval before any Odoo write.`,
      odoo_payload: odooPayload,
      odoo_model: "account.payment",
      odoo_method: "create",
      source_context: { memo, payment_date, journal_id },
    });

    const duration = Date.now() - t0;
    appendLog(vaultPath, buildEntry(
      "create_payment",
      `Payment approval requested: partner_id=${partner_id} amount=${amount}`,
      "approval_pending",
      duration,
      `Approval file written at ${path.basename(approvalFile)}. No Odoo write performed.`,
      {
        item_id: path.basename(approvalFile),
        to_state: "Pending_Approval",
        approval: { required: true, status: "pending", approver: null },
        approval_threshold: "approval_required",
      }
    ));

    return pendingApproval(
      approvalFile,
      `Payment of ${amount}${currency_code ? ` ${currency_code}` : ""} for partner_id=${partner_id} awaiting approval`,
      false
    );
  } catch (err) {
    appendLog(vaultPath, buildEntry(
      "create_payment",
      "Failed to write payment approval request",
      "failure",
      Date.now() - t0,
      String(err),
      { approval_threshold: "approval_required" }
    ));
    return fail(`Failed to write approval request: ${String(err)}`, false);
  }
}
