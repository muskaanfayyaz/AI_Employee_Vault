/**
 * GmailClient — thin wrapper around the googleapis Gmail v1 API.
 *
 * Credential loading is deferred until the first API call so the client
 * can be constructed without credentials (useful in DRY_RUN mode).
 */
import { readFile } from "fs/promises";
import { google } from "googleapis";
import type {
  DraftEmailArgs,
  EmailDetail,
  EmailSummary,
  GetEmailArgs,
  GmailClientInterface,
  MarkReadArgs,
  SearchEmailArgs,
  SendEmailArgs,
} from "./types";

type GmailService = ReturnType<typeof google.gmail>;

export class GmailClient implements GmailClientInterface {
  private _service: GmailService | null = null;

  constructor(private readonly tokenPath: string) {}

  // ── Private ───────────────────────────────────────────────────────────────

  private async service(): Promise<GmailService> {
    if (this._service) return this._service;

    const raw = await readFile(this.tokenPath, "utf-8");
    const token = JSON.parse(raw);

    const auth = new google.auth.OAuth2(
      token.client_id,
      token.client_secret,
      token.redirect_uri
    );
    auth.setCredentials(token);

    this._service = google.gmail({ version: "v1", auth });
    return this._service;
  }

  private buildRaw(args: { to: string; subject: string; body: string; cc?: string | null; bcc?: string | null }): string {
    const lines = [
      `To: ${args.to}`,
      `Subject: ${args.subject}`,
      ...(args.cc ? [`Cc: ${args.cc}`] : []),
      ...(args.bcc ? [`Bcc: ${args.bcc}`] : []),
      "Content-Type: text/plain; charset=utf-8",
      "",
      args.body,
    ];
    return Buffer.from(lines.join("\r\n")).toString("base64url");
  }

  // ── Public API ────────────────────────────────────────────────────────────

  async sendEmail(args: SendEmailArgs): Promise<{ message_id: string; status: string }> {
    const svc = await this.service();
    const raw = this.buildRaw(args);
    const requestBody: Record<string, unknown> = { raw };
    if (args.reply_to_message_id) {
      requestBody.threadId = args.reply_to_message_id;
    }
    const res = await svc.users.messages.send({ userId: "me", requestBody });
    return { message_id: res.data.id ?? "", status: "sent" };
  }

  async draftEmail(args: DraftEmailArgs): Promise<{ draft_id: string; thread_id: string | null }> {
    const svc = await this.service();
    const raw = this.buildRaw(args);
    const res = await svc.users.drafts.create({
      userId: "me",
      requestBody: { message: { raw } },
    });
    return {
      draft_id: res.data.id ?? "",
      thread_id: res.data.message?.threadId ?? null,
    };
  }

  async searchEmails(args: SearchEmailArgs): Promise<EmailSummary[]> {
    const svc = await this.service();
    const maxResults = args.max_results ?? 10;

    const list = await svc.users.messages.list({
      userId: "me",
      q: args.query,
      maxResults,
    });

    const messages = list.data.messages ?? [];
    const results: EmailSummary[] = [];

    for (const msg of messages) {
      const detail = await svc.users.messages.get({
        userId: "me",
        id: msg.id!,
        format: "metadata",
        metadataHeaders: ["From", "Subject", "Date"],
      });

      const headers: Record<string, string> = {};
      for (const h of detail.data.payload?.headers ?? []) {
        if (h.name && h.value) headers[h.name] = h.value;
      }

      results.push({
        id: msg.id!,
        from: headers["From"] ?? "",
        subject: headers["Subject"] ?? "",
        date: headers["Date"] ?? "",
        snippet: detail.data.snippet ?? "",
      });
    }

    return results;
  }

  async getEmail(args: GetEmailArgs): Promise<EmailDetail> {
    const svc = await this.service();
    const detail = await svc.users.messages.get({
      userId: "me",
      id: args.message_id,
      format: "full",
    });

    const headers: Record<string, string> = {};
    for (const h of detail.data.payload?.headers ?? []) {
      if (h.name && h.value) headers[h.name] = h.value;
    }

    return {
      from: headers["From"] ?? "",
      to: headers["To"] ?? "",
      subject: headers["Subject"] ?? "",
      body: detail.data.snippet ?? "",
      date: headers["Date"] ?? "",
      attachments: [],
    };
  }

  async markRead(args: MarkReadArgs): Promise<{ status: string }> {
    const svc = await this.service();
    await svc.users.messages.modify({
      userId: "me",
      id: args.message_id,
      requestBody: { removeLabelIds: ["UNREAD"] },
    });
    return { status: "ok" };
  }
}
