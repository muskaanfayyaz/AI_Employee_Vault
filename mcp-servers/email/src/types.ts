/**
 * Shared types for the email MCP server.
 */

/** Standard structured response returned by every tool. */
export interface EmailToolResult {
  success: boolean;
  dry_run: boolean;
  data: Record<string, unknown> | null;
  error: string | null;
}

// ── Tool argument interfaces ────────────────────────────────────────────────

export interface SendEmailArgs {
  to: string;
  subject: string;
  body: string;
  cc?: string | null;
  bcc?: string | null;
  reply_to_message_id?: string | null;
}

export interface DraftEmailArgs {
  to: string;
  subject: string;
  body: string;
  cc?: string | null;
  bcc?: string | null;
}

export interface SearchEmailArgs {
  query: string;
  max_results?: number;
}

export interface GetEmailArgs {
  message_id: string;
}

export interface MarkReadArgs {
  message_id: string;
}

// ── Client interface (injectable for testing) ──────────────────────────────

export interface EmailSummary {
  id: string;
  from: string;
  subject: string;
  date: string;
  snippet: string;
}

export interface EmailDetail {
  from: string;
  to: string;
  subject: string;
  body: string;
  date: string;
  attachments: { name: string; mime_type: string; size: number }[];
}

export interface GmailClientInterface {
  sendEmail(args: SendEmailArgs): Promise<{ message_id: string; status: string }>;
  draftEmail(args: DraftEmailArgs): Promise<{ draft_id: string; thread_id: string | null }>;
  searchEmails(args: SearchEmailArgs): Promise<EmailSummary[]>;
  getEmail(args: GetEmailArgs): Promise<EmailDetail>;
  markRead(args: MarkReadArgs): Promise<{ status: string }>;
}
