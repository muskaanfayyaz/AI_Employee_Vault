/**
 * Odoo JSON-RPC client.
 *
 * Communicates with Odoo's external JSON-RPC API:
 *   POST {url}/jsonrpc
 *   service: "common" | "object"
 *   method:  "authenticate" | "execute_kw"
 *
 * All credentials are sourced from constructor arguments which MUST come
 * from environment variables — never hard-coded (FR-G040).
 *
 * The client is stateful: it caches the authenticated uid and reuses it
 * across calls. Call authenticate() explicitly or let the first searchRead/
 * create call authenticate lazily.
 */
import type { OdooClientInterface } from "./types";

interface JsonRpcResponse {
  jsonrpc: string;
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: { message?: string } };
}

export class OdooClient implements OdooClientInterface {
  private readonly url: string;
  private readonly db: string;
  private readonly username: string;
  private readonly apiKey: string;
  private uid: number | null = null;
  private requestId = 0;

  constructor(url: string, db: string, username: string, apiKey: string) {
    // Normalise URL — strip trailing slash
    this.url = url.replace(/\/$/, "");
    this.db = db;
    this.username = username;
    this.apiKey = apiKey;
  }

  // ── Private JSON-RPC transport ────────────────────────────────────────────

  private async jsonRpc(
    service: "common" | "object",
    method: string,
    args: unknown[]
  ): Promise<unknown> {
    const id = ++this.requestId;
    const body = JSON.stringify({
      jsonrpc: "2.0",
      method: "call",
      id,
      params: { service, method, args },
    });

    const response = await fetch(`${this.url}/jsonrpc`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = (await response.json()) as JsonRpcResponse;

    if (data.error) {
      const msg =
        data.error.data?.message ?? data.error.message ?? "Unknown Odoo error";
      throw new Error(`Odoo JSON-RPC error: ${msg}`);
    }

    return data.result;
  }

  // ── Public API ───────────────────────────────────────────────────────────

  /**
   * Authenticate with Odoo and cache the uid.
   * Returns the user id (uid). Throws on failure.
   */
  async authenticate(): Promise<number> {
    const uid = await this.jsonRpc("common", "authenticate", [
      this.db,
      this.username,
      this.apiKey,
      {},
    ]);

    if (typeof uid !== "number" || uid === 0) {
      throw new Error(
        "Odoo authentication failed — check ODOO_DB, ODOO_USERNAME, ODOO_API_KEY."
      );
    }

    this.uid = uid;
    return uid;
  }

  /**
   * Ensure authenticated. Called before every object service request.
   */
  private async ensureAuth(): Promise<void> {
    if (!this.uid) {
      await this.authenticate();
    }
  }

  /**
   * search_read — read records matching domain.
   */
  async searchRead(
    model: string,
    domain: unknown[],
    fields: string[],
    opts: { limit?: number; offset?: number; order?: string } = {}
  ): Promise<Record<string, unknown>[]> {
    await this.ensureAuth();
    const result = await this.jsonRpc("object", "execute_kw", [
      this.db,
      this.uid,
      this.apiKey,
      model,
      "search_read",
      [domain],
      {
        fields,
        limit: opts.limit ?? 50,
        offset: opts.offset ?? 0,
        ...(opts.order ? { order: opts.order } : {}),
      },
    ]);
    return result as Record<string, unknown>[];
  }

  /**
   * create — create a single record. Returns the new record id.
   */
  async create(
    model: string,
    vals: Record<string, unknown>
  ): Promise<number> {
    await this.ensureAuth();
    const result = await this.jsonRpc("object", "execute_kw", [
      this.db,
      this.uid,
      this.apiKey,
      model,
      "create",
      [vals],
    ]);
    return result as number;
  }

  /**
   * write — update records. Returns true on success.
   */
  async write(
    model: string,
    ids: number[],
    vals: Record<string, unknown>
  ): Promise<boolean> {
    await this.ensureAuth();
    const result = await this.jsonRpc("object", "execute_kw", [
      this.db,
      this.uid,
      this.apiKey,
      model,
      "write",
      [ids, vals],
    ]);
    return result as boolean;
  }
}
