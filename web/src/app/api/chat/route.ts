import { createHmac } from "node:crypto";
import type { ModelKey } from "@/lib/types";

// Proxies the chat widget to the n8n webhook. The webhook URL and its key stay on the server,
// and the page needs no CORS setup.
const ENDPOINTS: Record<ModelKey, string | undefined> = {
  claude: process.env.N8N_CLAUDE_WEBHOOK_URL,
  openai: process.env.N8N_OPENAI_WEBHOOK_URL,
};
const WEBHOOK_SECRET = process.env.N8N_WEBHOOK_SECRET;
const MAX_MESSAGE = 4000;

export const maxDuration = 120;

// In-memory rate limit (single-process demo server; use a shared store such as Redis in production).
// X-Forwarded-For is client-controlled unless a proxy you run sets it, so it is only used when
// TRUSTED_PROXY_HOPS says how many proxies sit in front of the app; then the client is the address
// those proxies appended. Without it (local demo) every request shares one bucket.
const RATE = { max: 30, windowMs: 5 * 60 * 1000, maxClients: 10_000 };
const TRUSTED_PROXY_HOPS = Number(process.env.TRUSTED_PROXY_HOPS ?? 0);
const hits = new Map<string, number[]>();

function clientKey(request: Request): string {
  if (TRUSTED_PROXY_HOPS > 0) {
    const chain = (request.headers.get("x-forwarded-for") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    const client = chain[chain.length - TRUSTED_PROXY_HOPS];
    if (client) return client;
  }
  return "local";
}

function rateLimited(request: Request): boolean {
  const now = Date.now();
  if (hits.size > RATE.maxClients) {
    for (const [key, times] of hits) if (!times.some((t) => now - t < RATE.windowMs)) hits.delete(key);
    if (hits.size > RATE.maxClients) hits.clear();
  }
  const key = clientKey(request);
  const recent = (hits.get(key) ?? []).filter((t) => now - t < RATE.windowMs);
  recent.push(now);
  hits.set(key, recent);
  return recent.length > RATE.max;
}

const fail = (status: number, error: string) => Response.json({ error }, { status });

/** Only same-origin JSON requests: blocks other websites from posting through the proxy. */
function crossSite(request: Request): boolean {
  if (request.headers.get("sec-fetch-site") === "cross-site") return true;
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).host !== request.headers.get("host");
  } catch {
    return true;
  }
}

/**
 * The browser's random id is mapped to a keyed hash before it reaches n8n, so a session id
 * seen in n8n or Supabase logs can't be replayed through this proxy to read that conversation.
 */
function serverSessionId(clientId: string, secret: string): string {
  return "web-" + createHmac("sha256", secret).update(clientId).digest("hex").slice(0, 32);
}

export async function POST(request: Request) {
  if (crossSite(request)) return fail(403, "Requests must come from the Brightpan support page.");
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return fail(415, "Send the message as JSON.");
  }
  if (rateLimited(request)) return fail(429, "Too many messages in a short time. Wait a few minutes, then try again.");

  let body: { message?: unknown; session_id?: unknown; model?: unknown };
  try {
    body = await request.json();
  } catch {
    return fail(400, "Request body must be JSON.");
  }

  const message = typeof body.message === "string" ? body.message.trim() : "";
  const clientId = typeof body.session_id === "string" ? body.session_id : "";
  const model: ModelKey = body.model === "openai" ? "openai" : "claude";

  if (!message || message.length > MAX_MESSAGE) {
    return fail(400, `Write a message of 1 to ${MAX_MESSAGE.toLocaleString("en-US")} characters.`);
  }
  if (!/^[\w-]{8,100}$/.test(clientId)) return fail(400, "Start a new conversation and send the message again.");

  const endpoint = ENDPOINTS[model];
  if (!endpoint || !WEBHOOK_SECRET) {
    return fail(500, "Set the N8N_* webhook URLs and N8N_WEBHOOK_SECRET in web/.env.local, then restart the app.");
  }

  let res: Response;
  try {
    res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Brightpan-Key": WEBHOOK_SECRET },
      body: JSON.stringify({ message, session_id: serverSessionId(clientId, WEBHOOK_SECRET) }),
      signal: AbortSignal.timeout(110_000),
      cache: "no-store",
    });
  } catch (err) {
    const timedOut = err instanceof Error && err.name === "TimeoutError";
    return fail(
      502,
      timedOut
        ? "The support workflow took longer than 110 seconds. Send the message again."
        : "Can't reach n8n. Check that it is running at the webhook URL in web/.env.local.",
    );
  }

  if (res.status === 401 || res.status === 403) {
    return fail(502, "n8n rejected the webhook key. Make N8N_WEBHOOK_SECRET in web/.env.local match the root .env.");
  }
  if (!res.ok) return fail(502, `The support workflow returned HTTP ${res.status}. Check that it is active in n8n.`);

  const text = await res.text();
  try {
    return Response.json(JSON.parse(text));
  } catch {
    return fail(502, "The support workflow sent a reply that isn't JSON. Check the workflow's Respond node in n8n.");
  }
}
