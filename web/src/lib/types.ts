export type ModelKey = "claude" | "openai";

export const MODELS: Record<ModelKey, { label: string; short: string }> = {
  claude: { label: "Claude Opus 5.5", short: "Claude" },
  openai: { label: "GPT-5.5", short: "GPT-5.5" },
};

export const MAX_MESSAGE = 4000;

/** Mirrors the `order` object built in n8n/js/lookup_result.js. */
export type OrderItem = {
  qty: number;
  title: string;
  price: string;
  status: string | null;
  final_sale: boolean;
};

export type Order = {
  number: string;
  placed: string;
  status: string;
  cancelled: boolean;
  payment: string;
  ship_to: string | null;
  carrier: string | null;
  tracking: string | null;
  shipped: string | null;
  delivered: string | null;
  shipping: string;
  total: string;
  currency: string;
  note: string | null;
  items: OrderItem[];
};

/**
 * Reply from the n8n agent workflow: n8n/js/build_turn.js (normal turn) and
 * n8n/js/error_turn.js (error branch, `error: true`) return exactly these fields.
 */
export type AgentReply = {
  answer: string;
  session_id: string;
  tools_called: string[];
  article_ids_used: string[];
  article_ids_retrieved: string[];
  sources: { id: string; title: string }[];
  lookup: "match" | "no_match" | "incomplete" | null;
  order: Order | null;
  handoff_id: number | null;
  handoff_verified: boolean | null;
  escalated: boolean;
  latency_ms: number;
  model: string;
  error: boolean;
};

/** Accepts any JSON reply and fills missing fields, so an unexpected shape can't crash the page. */
export function toAgentReply(data: Partial<AgentReply>): AgentReply {
  return {
    answer: typeof data.answer === "string" ? data.answer : "",
    session_id: data.session_id ?? "",
    tools_called: Array.isArray(data.tools_called) ? data.tools_called : [],
    article_ids_used: Array.isArray(data.article_ids_used) ? data.article_ids_used : [],
    article_ids_retrieved: Array.isArray(data.article_ids_retrieved) ? data.article_ids_retrieved : [],
    sources: Array.isArray(data.sources) ? data.sources : [],
    lookup: data.lookup ?? null,
    order: data.order && Array.isArray(data.order.items) ? data.order : null,
    handoff_id: data.handoff_id ?? null,
    handoff_verified: data.handoff_verified ?? null,
    escalated: Boolean(data.escalated),
    latency_ms: Number(data.latency_ms) || 0,
    model: data.model ?? "",
    error: Boolean(data.error),
  };
}

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; reply: AgentReply; question: string }
  | { id: string; role: "error"; text: string; detail?: string; question: string };
