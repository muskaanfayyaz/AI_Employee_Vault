/**
 * Unit tests for email MCP tool handlers.
 *
 * All tests use an injectable mock client — no real Gmail API calls.
 * DRY_RUN is passed explicitly to each handler so tests are isolated
 * from process.env.
 */
import { describe, expect, it, vi } from "vitest";
import { handleDraftEmail, handleSearchEmail, handleSendEmail } from "../src/tools";
import type { GmailClientInterface } from "../src/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockClient(overrides: Partial<GmailClientInterface> = {}): GmailClientInterface {
  return {
    sendEmail: vi.fn().mockResolvedValue({ message_id: "msg123", status: "sent" }),
    draftEmail: vi.fn().mockResolvedValue({ draft_id: "draft456", thread_id: null }),
    searchEmails: vi.fn().mockResolvedValue([
      {
        id: "msg001",
        from: "boss@example.com",
        subject: "Review needed",
        date: "2026-02-19",
        snippet: "Please review...",
      },
    ]),
    getEmail: vi.fn().mockResolvedValue({
      from: "boss@example.com",
      to: "me@example.com",
      subject: "Review needed",
      body: "Please review the attached.",
      date: "2026-02-19",
      attachments: [],
    }),
    markRead: vi.fn().mockResolvedValue({ status: "ok" }),
    ...overrides,
  };
}

// ── handleSendEmail ───────────────────────────────────────────────────────────

describe("handleSendEmail", () => {
  it("returns success with message_id on valid input", async () => {
    const client = mockClient();
    const result = await handleSendEmail(
      { to: "user@example.com", subject: "Hello", body: "World" },
      client,
      false
    );
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(false);
    expect(result.data?.message_id).toBe("msg123");
    expect(result.error).toBeNull();
  });

  it("calls client.sendEmail with parsed args", async () => {
    const client = mockClient();
    await handleSendEmail(
      { to: "user@example.com", subject: "Hello", body: "World" },
      client,
      false
    );
    expect(client.sendEmail).toHaveBeenCalledWith(
      expect.objectContaining({ to: "user@example.com", subject: "Hello", body: "World" })
    );
  });

  it("passes optional cc, bcc, reply_to_message_id to client", async () => {
    const client = mockClient();
    await handleSendEmail(
      {
        to: "user@example.com",
        subject: "Re: Hello",
        body: "Response",
        cc: "cc@example.com",
        reply_to_message_id: "thread123",
      },
      client,
      false
    );
    expect(client.sendEmail).toHaveBeenCalledWith(
      expect.objectContaining({ cc: "cc@example.com", reply_to_message_id: "thread123" })
    );
  });

  it("no-ops and returns dry_run stub when dryRun=true", async () => {
    const client = mockClient();
    const result = await handleSendEmail(
      { to: "user@example.com", subject: "Hello", body: "World" },
      client,
      true
    );
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(true);
    expect(result.data?.status).toBe("dry_run");
    expect(result.data?.recipient).toBe("user@example.com");
    expect(client.sendEmail).not.toHaveBeenCalled();
  });

  it("no-ops with null client in dry-run mode", async () => {
    const result = await handleSendEmail(
      { to: "user@example.com", subject: "Hello", body: "World" },
      null,
      true
    );
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(true);
  });

  it("returns failure when client is null and not dry-run", async () => {
    const result = await handleSendEmail(
      { to: "user@example.com", subject: "Hello", body: "World" },
      null,
      false
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("GMAIL_OAUTH_TOKEN_PATH");
  });

  it("returns failure on invalid email address", async () => {
    const client = mockClient();
    const result = await handleSendEmail(
      { to: "not-an-email", subject: "Hello", body: "World" },
      client,
      false
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("Invalid arguments");
  });

  it("returns failure when subject is missing", async () => {
    const client = mockClient();
    const result = await handleSendEmail(
      { to: "user@example.com", body: "World" },
      client,
      false
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("Invalid arguments");
  });

  it("returns failure when body is missing", async () => {
    const client = mockClient();
    const result = await handleSendEmail(
      { to: "user@example.com", subject: "Hello" },
      client,
      false
    );
    expect(result.success).toBe(false);
  });

  it("returns failure when client.sendEmail throws", async () => {
    const client = mockClient({
      sendEmail: vi.fn().mockRejectedValue(new Error("Gmail API Error")),
    });
    const result = await handleSendEmail(
      { to: "user@example.com", subject: "Hello", body: "World" },
      client,
      false
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("Gmail API Error");
  });
});

// ── handleDraftEmail ──────────────────────────────────────────────────────────

describe("handleDraftEmail", () => {
  it("returns success with draft_id on valid input", async () => {
    const client = mockClient();
    const result = await handleDraftEmail(
      { to: "user@example.com", subject: "Draft Subject", body: "Draft body" },
      client,
      false
    );
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(false);
    expect(result.data?.draft_id).toBe("draft456");
    expect(result.data?.thread_id).toBeNull();
    expect(result.error).toBeNull();
  });

  it("calls client.draftEmail with parsed args", async () => {
    const client = mockClient();
    await handleDraftEmail(
      { to: "user@example.com", subject: "Draft", body: "Body" },
      client,
      false
    );
    expect(client.draftEmail).toHaveBeenCalledWith(
      expect.objectContaining({ to: "user@example.com", subject: "Draft" })
    );
  });

  it("no-ops and returns dry_run stub when dryRun=true", async () => {
    const client = mockClient();
    const result = await handleDraftEmail(
      { to: "user@example.com", subject: "Draft", body: "Body" },
      client,
      true
    );
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(true);
    expect(result.data?.draft_id).toBe("dry-run-draft-id");
    expect(client.draftEmail).not.toHaveBeenCalled();
  });

  it("no-ops with null client in dry-run mode", async () => {
    const result = await handleDraftEmail(
      { to: "user@example.com", subject: "Draft", body: "Body" },
      null,
      true
    );
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(true);
  });

  it("returns failure when client is null and not dry-run", async () => {
    const result = await handleDraftEmail(
      { to: "user@example.com", subject: "Draft", body: "Body" },
      null,
      false
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("GMAIL_OAUTH_TOKEN_PATH");
  });

  it("returns failure on invalid email address", async () => {
    const client = mockClient();
    const result = await handleDraftEmail(
      { to: "bad-email", subject: "Draft", body: "Body" },
      client,
      false
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("Invalid arguments");
  });

  it("returns failure when client.draftEmail throws", async () => {
    const client = mockClient({
      draftEmail: vi.fn().mockRejectedValue(new Error("Draft API Error")),
    });
    const result = await handleDraftEmail(
      { to: "user@example.com", subject: "Draft", body: "Body" },
      client,
      false
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("Draft API Error");
  });
});

// ── handleSearchEmail ─────────────────────────────────────────────────────────

describe("handleSearchEmail", () => {
  it("returns emails list on valid query", async () => {
    const client = mockClient();
    const result = await handleSearchEmail({ query: "is:unread" }, client, false);
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(false);
    expect(Array.isArray(result.data?.emails)).toBe(true);
    expect((result.data?.emails as unknown[]).length).toBe(1);
    expect(result.error).toBeNull();
  });

  it("calls client.searchEmails with parsed args", async () => {
    const client = mockClient();
    await handleSearchEmail({ query: "from:boss@example.com", max_results: 5 }, client, false);
    expect(client.searchEmails).toHaveBeenCalledWith(
      expect.objectContaining({ query: "from:boss@example.com", max_results: 5 })
    );
  });

  it("uses default max_results=10 when not specified", async () => {
    const client = mockClient();
    await handleSearchEmail({ query: "is:important" }, client, false);
    expect(client.searchEmails).toHaveBeenCalledWith(
      expect.objectContaining({ max_results: 10 })
    );
  });

  it("returns dry_run=true and empty emails when dryRun=true", async () => {
    const client = mockClient();
    const result = await handleSearchEmail({ query: "is:unread" }, client, true);
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(true);
    expect((result.data?.emails as unknown[]).length).toBe(0);
    expect(client.searchEmails).not.toHaveBeenCalled();
  });

  it("no-ops with null client in dry-run mode", async () => {
    const result = await handleSearchEmail({ query: "is:unread" }, null, true);
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(true);
  });

  it("returns failure when client is null and not dry-run", async () => {
    const result = await handleSearchEmail({ query: "is:unread" }, null, false);
    expect(result.success).toBe(false);
    expect(result.error).toContain("GMAIL_OAUTH_TOKEN_PATH");
  });

  it("returns failure when query is empty string", async () => {
    const client = mockClient();
    const result = await handleSearchEmail({ query: "" }, client, false);
    expect(result.success).toBe(false);
    expect(result.error).toContain("Invalid arguments");
  });

  it("returns failure when client.searchEmails throws", async () => {
    const client = mockClient({
      searchEmails: vi.fn().mockRejectedValue(new Error("Search API Error")),
    });
    const result = await handleSearchEmail({ query: "is:important" }, client, false);
    expect(result.success).toBe(false);
    expect(result.error).toContain("Search API Error");
  });

  it("includes the query in dry_run data", async () => {
    const result = await handleSearchEmail({ query: "is:starred" }, null, true);
    expect(result.data?.query).toBe("is:starred");
  });
});
