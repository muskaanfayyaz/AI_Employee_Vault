# Accounting

This folder contains markdown-formatted financial summaries used by the `generate_ceo_briefing` skill to populate the **Revenue & Financial Activity** section of the weekly briefing.

The CEO Briefing skill scans all `.md` files here and extracts:
- Invoice amounts (lines matching `invoice … <number>`)
- Payment amounts (lines matching `payment … <number>`)
- Overdue notices (lines containing "overdue")

## File Naming Convention

```
YYYY-MM-DD-<description>.md
```

Examples:
- `2026-02-24-weekly-invoices.md`
- `2026-02-24-payments-received.md`
- `2026-02-24-subscription-summary.md`

## Suggested File Format

```markdown
# Invoice Summary — 2026-02-24

| # | Customer | Invoice Amount | Status |
|---|----------|---------------|--------|
| INV-001 | Acme Corp | 1500.00 | Paid |
| INV-002 | Beta Ltd  | 750.00  | Overdue |

**Total invoiced**: 2250.00
**Total payment received**: 1500.00
```

## How Data Is Populated

**Manually**: Create `.md` files here after reviewing your accounting system.

**Automatically (Gold Tier)**: The Odoo MCP `fetch_transactions` and `fetch_invoices` tools can generate these summaries when run as part of the weekly pipeline.

> Note: Never include raw credentials, API keys, or full account numbers in these files.
> Use aggregated totals and customer names only.
