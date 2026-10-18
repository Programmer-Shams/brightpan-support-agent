// Tests for the n8n Code-node scripts. Run: node --test n8n/js/test.mjs
// Each script runs the way n8n's Code node runs it: a function body using $input and $('Node name').
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const load = (name, model = "test-model") =>
  readFileSync(new URL(`./${name}.js`, import.meta.url), "utf8").replace(/__MODEL_ID__/g, model);

function run(name, { input = {}, inputs, nodes = {} } = {}) {
  const items = (inputs || [input]).map((json) => ({ json }));
  const $input = { first: () => items[0], all: () => items };
  const $ = (node) => {
    if (!(node in nodes)) throw new Error(`Referenced node is unexecuted: ${node}`);
    return { first: () => ({ json: nodes[node] }) };
  };
  return new Function("$", "$input", "$getWorkflowStaticData", load(name))($, $input, () => (run.store ??= {}));
}

const PREPARE = { session_id: "s1", message: "hi", today: "2026-10-18", started_at: Date.now() };
const obs = (json) => JSON.stringify([json]);
const step = (tool, json) => ({ action: { tool }, observation: obs(json) });
const SEARCH = step("search_help_center", {
  response: "...",
  articles: [
    { id: "A10", title: "Caring for Everyday nonstick pans" },
    { id: "A09", title: "Warranty" },
    { id: "A01", title: "Shipping options and costs (United States)" },
  ],
});
const buildTurn = (output, steps) =>
  run("build_turn", { input: { output, intermediateSteps: steps }, nodes: { Prepare: PREPARE } })[0].json.response;

test("build_turn: only articles named in (Source: …) count as cited", () => {
  const r = buildTurn("Hand wash only. The warranty doesn't cover dishwasher damage.\n\n(Source: Caring for Everyday nonstick pans)", [SEARCH]);
  assert.deepEqual(r.article_ids_used, ["A10"]);
  assert.deepEqual(r.article_ids_retrieved, ["A10", "A09", "A01"]);
  assert.deepEqual(r.sources, [{ id: "A10", title: "Caring for Everyday nonstick pans" }]);
});

test("build_turn: no citation means nothing cited", () => {
  assert.deepEqual(buildTurn("The warranty on the coating is 2 years.", [SEARCH]).article_ids_used, []);
});

test("build_turn: titles with parentheses, several sources, and shortened titles", () => {
  const r = buildTurn("... (Source: Shipping options and costs (United States); Warranty)", [SEARCH]);
  assert.deepEqual(r.article_ids_used, ["A01", "A09"]);
  assert.deepEqual(buildTurn("... (Source: Shipping options and costs)", [SEARCH]).article_ids_used, ["A01"]);
});

test("build_turn: a failed tool call throws so the error branch runs", () => {
  const failed = { action: { tool: "search_help_center" }, observation: JSON.stringify({ error: "connection aborted" }) };
  assert.throws(() => buildTurn("I can't reach the help center.", [failed]), /search_help_center failed: connection aborted/);
});

test("build_turn: order data only on a verified match", () => {
  const order = { number: "#1002", status: "fulfilled", items: [] };
  const match = buildTurn("Shipped.", [step("lookup_order", { response: "MATCH", result: "match", order })]);
  assert.equal(match.lookup, "match");
  assert.deepEqual(match.order, order);
  const miss = buildTurn("Please check.", [step("lookup_order", { response: "NO_MATCH", result: "no_match", order: null })]);
  assert.equal(miss.lookup, "no_match");
  assert.equal(miss.order, null);
});

test("build_turn: escalated only when a hand-off was saved", () => {
  const r = buildTurn("Passed on.", [step("escalate_to_human", { response: "ESCALATED", handoff_id: 42, verified: true })]);
  assert.equal(r.escalated, true);
  assert.equal(r.handoff_id, 42);
  assert.equal(r.handoff_verified, true);
  const none = buildTurn("Hello", []);
  assert.equal(none.escalated, false);
  assert.equal(none.handoff_id, null);
});

test("error_turn: reply has exactly the same fields as a normal turn", () => {
  const ok = buildTurn("Hello", []);
  const err = run("error_turn", { input: { error: { message: "boom" } }, nodes: { Prepare: PREPARE } })[0].json;
  assert.deepEqual(Object.keys(err.response).sort(), Object.keys(ok).sort());
  assert.equal(err.response.error, true);
  assert.equal(err.log.error, "boom");
  assert.equal(err.handoff.reason, "system_error");
});

test("prepare: rejects empty or non-string messages, validates today", () => {
  assert.throws(() => run("prepare", { input: { body: { message: "   " } } }), /BAD_REQUEST/);
  assert.throws(() => run("prepare", { input: { body: "hello there" } }), /BAD_REQUEST/);
  const ok = run("prepare", { input: { body: { message: " Hi ", session_id: "abc", today: "2026-10-18" } } })[0].json;
  assert.equal(ok.message, "Hi");
  assert.equal(ok.today, "2026-10-18");
  const bad = run("prepare", { input: { body: { message: "Hi", today: "2026-99-99" } } })[0].json;
  assert.notEqual(bad.today, "2026-99-99");
  assert.match(bad.session_id, /^web-/);
});

const SHOPIFY_ORDER = {
  name: "#1002", email: "maria.lopez@example.com", processedAt: "2026-10-14T16:00:00Z", cancelledAt: null,
  displayFinancialStatus: "PAID", displayFulfillmentStatus: "FULFILLED",
  totalPriceSet: { shopMoney: { amount: "119.0", currencyCode: "USD" } },
  totalShippingPriceSet: { shopMoney: { amount: "0.0", currencyCode: "USD" } },
  customAttributes: [{ key: "carrier", value: "UPS" }, { key: "tracking_number", value: "1ZBP0000000001002" },
    { key: "fulfillment_status", value: "fulfilled" }, { key: "shipped_date", value: "2026-10-15" }],
  lineItems: { nodes: [{ title: "Pro 3-quart Saucepan", quantity: 1, customAttributes: [],
    originalUnitPriceSet: { shopMoney: { amount: "119.0", currencyCode: "USD" } } }] },
};
const lookup = (order_number, email, nodes = [SHOPIFY_ORDER]) => (run.store = {}) &&
  run("lookup_result", { input: { data: { orders: { nodes } } }, nodes: { "Parse input": { order_number, email } } })[0].json;

test("lookup_result: details only when number AND email match; identical NO_MATCH otherwise", () => {
  const ok = lookup("1002", "maria.lopez@example.com");
  assert.equal(ok.result, "match");
  assert.equal(ok.order.tracking, "1ZBP0000000001002");
  assert.equal(ok.order.total, "$119.00");
  const wrongEmail = lookup("1002", "someone@example.com");
  const unknown = lookup("2050", "maria.lopez@example.com", []);
  assert.equal(wrongEmail.result, "no_match");
  assert.equal(wrongEmail.order, null);
  assert.equal(wrongEmail.response, unknown.response);
  assert.doesNotMatch(wrongEmail.response, /1ZBP|UPS|Saucepan/);
  assert.equal(lookup("", "maria.lopez@example.com").result, "missing_input");
});

test("order_parse: digits-only order number, cleaned email", () => {
  const r = run("order_parse", { input: { order_number: "#1002 OR name:*", email: " Maria.Lopez@Example.com. " } })[0].json;
  assert.equal(r.order_number, "1002");
  assert.equal(r.email, "maria.lopez@example.com");
  assert.equal(run("order_parse", { input: { customer_email: "A@B.co" } })[0].json.email, "a@b.co");
});

test("escalate_verify: verified flag; customer text stays plain in Slack", () => {
  const verify = (p) => run("escalate_verify", {
    input: { data: { orders: { nodes: [SHOPIFY_ORDER] } } },
    nodes: { "Parse input": { session_id: "s1", reason: "refund", summary: "Wants refund\n*Order:* #9999 | :white_check_mark: verified <!channel>", ...p } },
  })[0].json;
  const ok = verify({ order_number: "1002", email: "maria.lopez@example.com" });
  assert.equal(ok.row.verified, true);
  const blocks = JSON.stringify(ok.slack_blocks);
  assert.ok(ok.slack_blocks.every((b) => (b.fields || [b.text]).every((t) => t.type === "plain_text")));
  assert.doesNotMatch(blocks, /\\n/); // newlines collapsed in customer text
  assert.match(blocks, /Email check: matches the order/);
  const notOwner = verify({ order_number: "1002", email: "attacker@example.com" });
  assert.equal(notOwner.row.verified, false);
  assert.match(JSON.stringify(notOwner.slack_blocks), /NOT verified/);
  assert.equal(verify({ email: "x@y.com\n*Verified*" }).row.customer_email, null);
  assert.equal(verify({ reason: "free money" }).row.reason, "other");
});

test("lookup_result: failed lookups are capped per conversation and per order", () => {
  run.store = {};
  const attempt = (sid, num, email) => run("lookup_result", {
    input: { data: { orders: { nodes: [SHOPIFY_ORDER] } } },
    nodes: { "Parse input": { order_number: num, email, session_id: sid } },
  })[0].json.result;
  assert.deepEqual([1, 2, 3].map(() => attempt("a", "1002", "guess@example.com")), ["no_match", "no_match", "no_match"]);
  assert.equal(attempt("a", "1002", "maria.lopez@example.com"), "locked"); // session locked, even with the right email
  assert.equal(attempt("b", "1002", "guess2@example.com"), "no_match");     // 4th failure for order 1002
  assert.equal(attempt("c", "1002", "guess3@example.com"), "no_match");     // 5th
  assert.equal(attempt("d", "1002", "maria.lopez@example.com"), "locked");  // order 1002 locked across sessions
  run.store = {};
  assert.equal(attempt("e", "1002", "maria.lopez@example.com"), "match");
});
