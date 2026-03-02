/**
 * Shared types for the Odoo MCP server.
 */

/** Standard structured response returned by every tool. */
export interface OdooToolResult {
  success: boolean;
  dry_run: boolean;
  requires_approval: boolean;
  data: Record<string, unknown> | null;
  /** Path to the approval file written to /Pending_Approval — set when requires_approval=true */
  approval_file?: string;
  error: string | null;
}

// ── Tool argument interfaces ────────────────────────────────────────────────

export interface CreateInvoiceArgs {
  /** Customer name or Odoo partner ID (res.partner record id) */
  partner_id: number;
  /** ISO date string YYYY-MM-DD — invoice date */
  invoice_date?: string;
  /** Optional note / narration on the invoice */
  narration?: string;
  /** Line items */
  invoice_line_ids: InvoiceLineInput[];
  /** Currency ID (Odoo many2one id). Defaults to company currency if omitted. */
  currency_id?: number;
}

export interface InvoiceLineInput {
  /** Product ID (product.product) — optional */
  product_id?: number;
  /** Free-text description */
  name: string;
  quantity: number;
  /** Unit price */
  price_unit: number;
  /** Odoo account ID (account.account) — optional */
  account_id?: number;
}

export interface FetchTransactionsArgs {
  /** ISO date string YYYY-MM-DD — start of date range */
  date_from?: string;
  /** ISO date string YYYY-MM-DD — end of date range */
  date_to?: string;
  /** Filter by journal type: 'bank', 'cash', 'sale', 'purchase', 'general' */
  journal_type?: string;
  /** Maximum records to return (default: 50) */
  limit?: number;
  /** Offset for pagination (default: 0) */
  offset?: number;
}

export interface AnalyzeSubscriptionsArgs {
  /** Only flag subscriptions overdue by this many days (default: 0 = any overdue) */
  overdue_days?: number;
  /** Alert if renewal amount deviates more than this % from historical avg (default: 20) */
  amount_deviation_pct?: number;
  /** Maximum subscription records to analyse (default: 200) */
  limit?: number;
}

export interface CreatePaymentArgs {
  /** Odoo partner ID (res.partner) */
  partner_id: number;
  /** Payment amount — must be positive */
  amount: number;
  /** ISO 4217 currency code (informational only — server resolves Odoo currency_id) */
  currency_code?: string;
  /** ISO date string YYYY-MM-DD */
  payment_date: string;
  /** Journal to post payment to (Odoo account.journal id) */
  journal_id: number;
  /** Optional memo / communication */
  memo?: string;
  /** 'outbound' (vendor payment) or 'inbound' (customer payment) */
  payment_type: "inbound" | "outbound";
  /** Partner type: 'customer' or 'supplier' */
  partner_type: "customer" | "supplier";
}

// ── Odoo record shapes (minimal) ───────────────────────────────────────────

export interface OdooInvoice {
  id: number;
  name: string;
  state: string;
  move_type: string;
  partner_id: [number, string];
  invoice_date: string | false;
  amount_total: number;
  currency_id: [number, string];
}

export interface OdooMoveLine {
  id: number;
  name: string;
  date: string;
  account_id: [number, string];
  journal_id: [number, string];
  debit: number;
  credit: number;
  amount_currency: number;
  partner_id: [number, string] | false;
  move_name: string;
}

export interface OdooSubscription {
  id: number;
  name: string;
  partner_id: [number, string];
  stage_id?: [number, string];
  state?: string;
  recurring_next_date?: string | false;
  recurring_total?: number;
  date_start?: string | false;
  date?: string | false;
}

// ── Client interface (injectable for testing) ──────────────────────────────

export interface OdooClientInterface {
  authenticate(): Promise<number>;
  searchRead(
    model: string,
    domain: unknown[],
    fields: string[],
    opts?: { limit?: number; offset?: number; order?: string }
  ): Promise<Record<string, unknown>[]>;
  create(model: string, vals: Record<string, unknown>): Promise<number>;
  write(model: string, ids: number[], vals: Record<string, unknown>): Promise<boolean>;
}
