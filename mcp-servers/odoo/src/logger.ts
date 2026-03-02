/**
 * Audit logger for the Odoo MCP server.
 *
 * Appends structured JSON log entries to VAULT_PATH/Logs/YYYY-MM-DD.json.
 * Implements the Gold Tier extended log schema (FR-038 + FR-G046).
 *
 * Logs are append-only (FR-039). No entry is ever modified after writing.
 */
import fs from "fs";
import path from "path";

/** Gold Tier extended audit log entry (FR-038 + FR-G046). */
export interface OdooLogEntry {
  timestamp: string;
  actor: string;
  action: string;
  item_id: string | null;
  from_state: string | null;
  to_state: string | null;
  outcome: "success" | "failure" | "retry" | "dry_run" | "approval_pending";
  duration_ms: number;
  details: string;
  approval: {
    required: boolean;
    status: "auto" | "pending" | "approved" | "rejected" | "n/a";
    approver: "human" | "system" | null;
  };
  dry_run: boolean;
  /** Gold Tier extension fields */
  integration: "odoo";
  operation: string;
  retry_context: {
    attempt: number;
    max_attempts: number;
    delay_ms: number;
  } | null;
  approval_threshold: "auto" | "approval_required";
  ralph_wiggum_tag: string | null;
  degraded: boolean;
}

/**
 * Appends a single log entry to the daily JSON log file.
 * Creates the Logs directory and file if they do not exist.
 */
export function appendLog(vaultPath: string, entry: OdooLogEntry): void {
  const date = new Date().toISOString().split("T")[0];
  const logsDir = path.join(vaultPath, "Logs");
  const logFile = path.join(logsDir, `${date}.json`);

  fs.mkdirSync(logsDir, { recursive: true });

  let entries: OdooLogEntry[] = [];
  if (fs.existsSync(logFile)) {
    try {
      entries = JSON.parse(fs.readFileSync(logFile, "utf-8")) as OdooLogEntry[];
    } catch {
      // Corrupt log — start fresh rather than losing the file entirely.
      entries = [];
    }
  }

  entries.push(entry);
  fs.writeFileSync(logFile, JSON.stringify(entries, null, 2), "utf-8");
}

/**
 * Build a baseline log entry. Caller fills operation-specific fields.
 */
export function buildEntry(
  operation: string,
  action: string,
  outcome: OdooLogEntry["outcome"],
  durationMs: number,
  details: string,
  opts: Partial<OdooLogEntry> = {}
): OdooLogEntry {
  return {
    timestamp: new Date().toISOString(),
    actor: "odoo-mcp",
    action,
    item_id: opts.item_id ?? null,
    from_state: opts.from_state ?? null,
    to_state: opts.to_state ?? null,
    outcome,
    duration_ms: durationMs,
    details,
    approval: opts.approval ?? { required: false, status: "auto", approver: "system" },
    dry_run: opts.dry_run ?? false,
    integration: "odoo",
    operation,
    retry_context: opts.retry_context ?? null,
    approval_threshold: opts.approval_threshold ?? "auto",
    ralph_wiggum_tag: opts.ralph_wiggum_tag ?? null,
    degraded: opts.degraded ?? false,
  };
}
