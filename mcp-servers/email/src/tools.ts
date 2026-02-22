/**
 * Tool handlers for the email MCP server.
 *
 * Each handler:
 *   1. Validates input with Zod (returns structured failure on bad args).
 *   2. Short-circuits with a dry-run stub when dryRun=true (client is never called).
 *   3. Delegates to the injectable GmailClientInterface.
 *   4. Wraps any client error and returns a structured failure.
 *
 * All return EmailToolResult: { success, dry_run, data, error }.
 */
import { z } from "zod";
import type { EmailToolResult, GmailClientInterface } from "./types";

// ── Response helpers ────────────────────────────────────────────────────────

function ok(data: Record<string, unknown>, dryRun: boolean): EmailToolResult {
  return { success: true, dry_run: dryRun, data, error: null };
}

function fail(message: string, dryRun: boolean): EmailToolResult {
  return { success: false, dry_run: dryRun, data: null, error: message };
}

// ── Zod schemas ─────────────────────────────────────────────────────────────

export const SendEmailSchema = z.object({
  to: z.string().email("'to' must be a valid email address"),
  subject: z.string().min(1, "'subject' must not be empty"),
  body: z.string().min(1, "'body' must not be empty"),
  cc: z.string().nullable().optional(),
  bcc: z.string().nullable().optional(),
  reply_to_message_id: z.string().nullable().optional(),
});

export const DraftEmailSchema = z.object({
  to: z.string().email("'to' must be a valid email address"),
  subject: z.string().min(1, "'subject' must not be empty"),
  body: z.string().min(1, "'body' must not be empty"),
  cc: z.string().nullable().optional(),
  bcc: z.string().nullable().optional(),
});

export const SearchEmailSchema = z.object({
  query: z.string().min(1, "'query' must not be empty"),
  max_results: z.number().int().positive().optional().default(10),
});

// ── Handlers ────────────────────────────────────────────────────────────────

/**
 * send_email — sends a real Gmail message. Requires approval (FR-017).
 * No-ops in DRY_RUN mode without touching the Gmail API.
 */
export async function handleSendEmail(
  args: unknown,
  client: GmailClientInterface | null,
  dryRun: boolean
): Promise<EmailToolResult> {
  const parsed = SendEmailSchema.safeParse(args);
  if (!parsed.success) {
    return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  }

  if (dryRun) {
    return ok(
      { message_id: "dry-run-id", status: "dry_run", recipient: parsed.data.to },
      true
    );
  }

  if (!client) {
    return fail(
      "Gmail client not configured. Set GMAIL_OAUTH_TOKEN_PATH in .env.",
      false
    );
  }

  try {
    const result = await client.sendEmail(parsed.data);
    return ok(result as Record<string, unknown>, false);
  } catch (err) {
    return fail(String(err), false);
  }
}

/**
 * draft_email — creates a Gmail draft without sending.
 * No-ops in DRY_RUN mode.
 */
export async function handleDraftEmail(
  args: unknown,
  client: GmailClientInterface | null,
  dryRun: boolean
): Promise<EmailToolResult> {
  const parsed = DraftEmailSchema.safeParse(args);
  if (!parsed.success) {
    return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  }

  if (dryRun) {
    return ok(
      { draft_id: "dry-run-draft-id", thread_id: null, status: "dry_run" },
      true
    );
  }

  if (!client) {
    return fail(
      "Gmail client not configured. Set GMAIL_OAUTH_TOKEN_PATH in .env.",
      false
    );
  }

  try {
    const result = await client.draftEmail(parsed.data);
    return ok(result as Record<string, unknown>, false);
  } catch (err) {
    return fail(String(err), false);
  }
}

/**
 * search_email — searches Gmail using standard search syntax.
 * Returns an empty list in DRY_RUN mode.
 */
export async function handleSearchEmail(
  args: unknown,
  client: GmailClientInterface | null,
  dryRun: boolean
): Promise<EmailToolResult> {
  const parsed = SearchEmailSchema.safeParse(args);
  if (!parsed.success) {
    return fail(`Invalid arguments: ${parsed.error.message}`, dryRun);
  }

  if (dryRun) {
    return ok({ emails: [], query: parsed.data.query }, true);
  }

  if (!client) {
    return fail(
      "Gmail client not configured. Set GMAIL_OAUTH_TOKEN_PATH in .env.",
      false
    );
  }

  try {
    const emails = await client.searchEmails(parsed.data);
    return ok({ emails }, false);
  } catch (err) {
    return fail(String(err), false);
  }
}
