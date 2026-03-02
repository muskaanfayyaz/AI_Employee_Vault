/**
 * Approval file writer for the Odoo MCP server.
 *
 * When an operation requires human approval (FR-G006, FR-G009, FR-G011),
 * this module writes a vault item to VAULT_PATH/Pending_Approval/ using
 * the standard YAML front-matter format (FR-002).
 *
 * The orchestrator / AI employee monitors this folder and surfaces the
 * approval request to the human operator. NO Odoo write is made until
 * the human approves the item.
 */
import fs from "fs";
import path from "path";
import crypto from "crypto";

export interface ApprovalRequest {
  /** Human-readable description of the proposed action */
  proposed_action: string;
  /** AI reasoning for why this action is needed */
  reasoning: string;
  /** The raw arguments that would be passed to Odoo on approval */
  odoo_payload: Record<string, unknown>;
  /** Odoo model that would be written (e.g. account.payment) */
  odoo_model: string;
  /** Odoo method that would be called (e.g. create) */
  odoo_method: string;
  /** Original context from the caller (item_id, source, etc.) */
  source_context?: Record<string, unknown>;
}

/**
 * Writes an approval request file to VAULT_PATH/Pending_Approval/.
 *
 * Returns the absolute path of the created file.
 * Throws if the directory cannot be created or the file cannot be written.
 */
export function writeApprovalRequest(
  vaultPath: string,
  req: ApprovalRequest
): string {
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  const filename = `odoo-approval-${id}.md`;
  const approvalDir = path.join(vaultPath, "Pending_Approval");
  const filePath = path.join(approvalDir, filename);

  fs.mkdirSync(approvalDir, { recursive: true });

  const frontMatter = [
    "---",
    `id: ${id}`,
    `type: odoo_approval`,
    `source: odoo-mcp`,
    `priority: high`,
    `status: pending_approval`,
    `created_at: "${now}"`,
    `updated_at: "${now}"`,
    `requires_approval: true`,
    `classification: local_only`,
    `approval:`,
    `  proposed_action: "${req.proposed_action.replace(/"/g, '\\"')}"`,
    `  reasoning: "FR-G006/FR-G009 — Odoo write requires human approval"`,
    `  odoo_model: "${req.odoo_model}"`,
    `  odoo_method: "${req.odoo_method}"`,
    `  requested_at: "${now}"`,
    `  decision: null`,
    `  decided_at: null`,
    `  feedback: null`,
    "---",
  ].join("\n");

  const body = [
    "",
    `# Odoo Action Requires Approval`,
    "",
    `**Action**: ${req.proposed_action}`,
    "",
    `**Odoo Model**: \`${req.odoo_model}\``,
    `**Odoo Method**: \`${req.odoo_method}\``,
    "",
    `## Reasoning`,
    "",
    req.reasoning,
    "",
    `## Proposed Payload`,
    "",
    "```json",
    JSON.stringify(req.odoo_payload, null, 2),
    "```",
    "",
    req.source_context
      ? [
          `## Source Context`,
          "",
          "```json",
          JSON.stringify(req.source_context, null, 2),
          "```",
          "",
        ].join("\n")
      : "",
    `## Instructions`,
    "",
    `To **approve**: rename this file or set \`approval.decision: approved\` in the front-matter.`,
    `To **reject**: set \`approval.decision: rejected\` and add \`approval.feedback\` with the reason.`,
    "",
    `> ⚠️ No Odoo write will occur until this approval is granted.`,
    `> ⚠️ This approval expires after 24 hours without auto-approving (FR-G009).`,
  ].join("\n");

  fs.writeFileSync(filePath, frontMatter + body, "utf-8");
  return filePath;
}
