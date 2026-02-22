# MCP Server Interface Contracts

**Date**: 2026-02-17

## Base MCP Server Interface

All MCP servers expose these standard tools:

```
ping()
  Input: none
  Output: { "status": "ok", "server": "<name>", "version": "<semver>" }
  Purpose: Health check for orchestrator polling.
```

---

## Email MCP Server (Silver)

**Transport**: stdio
**Credential Ref**: `GMAIL_OAUTH_TOKEN_PATH` (env var)

### Tools

```
send_email(to, subject, body, cc?, bcc?, reply_to_message_id?)
  Input:
    to: string              # Recipient email
    subject: string
    body: string            # Plain text or HTML
    cc: string | null
    bcc: string | null
    reply_to_message_id: string | null  # For threading
  Output:
    message_id: string
    status: "sent" | "failed"
    error: string | null
  Approval: REQUIRED (FR-017)

search_emails(query, max_results?)
  Input:
    query: string           # Gmail search syntax
    max_results: int        # Default: 10
  Output:
    emails: list[{id, from, subject, date, snippet}]
  Approval: auto (read-only)

get_email(message_id)
  Input:
    message_id: string
  Output:
    from: string
    to: string
    subject: string
    body: string
    date: string
    attachments: list[{name, mime_type, size}]
  Approval: auto (read-only)

mark_read(message_id)
  Input:
    message_id: string
  Output:
    status: "ok" | "failed"
  Approval: auto
```

---

## Odoo MCP Server (Gold)

**Transport**: stdio
**Credential Refs**: `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`,
  `ODOO_API_KEY` (env vars)

### Tools

```
search_records(model, domain, fields?, limit?)
  Input:
    model: string           # e.g., "sale.order", "account.move"
    domain: list            # Odoo domain filter
    fields: list[string]    # Fields to return
    limit: int              # Default: 50
  Output:
    records: list[dict]
    count: int
  Approval: auto (read-only)

read_record(model, record_id, fields?)
  Input:
    model: string
    record_id: int
    fields: list[string]
  Output:
    record: dict
  Approval: auto (read-only)

create_record(model, values)
  Input:
    model: string
    values: dict
  Output:
    record_id: int
    status: "created" | "failed"
    error: string | null
  Approval: REQUIRED (FR-017 — Odoo write operation)

update_record(model, record_id, values)
  Input:
    model: string
    record_id: int
    values: dict
  Output:
    status: "updated" | "failed"
    error: string | null
  Approval: REQUIRED (FR-017 — Odoo write operation)
```

---

## Social Media MCP Server (Gold)

**Transport**: stdio
**Credential Refs**: `LINKEDIN_TOKEN`, `FACEBOOK_TOKEN`,
  `INSTAGRAM_TOKEN`, `TWITTER_TOKEN` (env vars)

### Tools

```
draft_post(platform, text, media_url?)
  Input:
    platform: "linkedin" | "facebook" | "instagram" | "twitter"
    text: string
    media_url: string | null
  Output:
    draft_id: string
    character_count: int
    platform_limit: int
    within_limit: bool
  Approval: REQUIRED (always — FR-017)

publish_post(platform, draft_id)
  Input:
    platform: string
    draft_id: string
  Output:
    post_id: string
    post_url: string
    status: "published" | "failed"
    error: string | null
  Approval: REQUIRED (always — FR-017)
  Precondition: Draft must be approved

get_mentions(platform, since?)
  Input:
    platform: string
    since: string           # ISO-8601 datetime
  Output:
    mentions: list[{id, author, text, date, url}]
  Approval: auto (read-only)

get_analytics(platform, period_days?)
  Input:
    platform: string
    period_days: int        # Default: 7
  Output:
    impressions: int
    engagements: int
    followers_change: int
    top_posts: list[{id, impressions, engagements}]
  Approval: auto (read-only)
```
