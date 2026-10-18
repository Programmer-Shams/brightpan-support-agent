// Keys and limits for order-lookup attempt limiting (enforced atomically by public.begin_lookup in Supabase).
// Hard keys lock further lookups: per conversation, per order number (stops guessing an order's email) and
// per email (stops cycling order numbers for a known email). The global failure counter never locks anyone
// out; when it passes its threshold, the hard keys switch to their `strict` limits, which cuts an attacker's
// budget while customers who get their details right on the first try are unaffected.
const p = $input.first().json;
const LIMITS = {
  session: { max: 3, strict: 1, seconds: 15 * 60, hard: true },
  order: { max: 5, strict: 2, seconds: 60 * 60, hard: true },
  email: { max: 5, strict: 2, seconds: 60 * 60, hard: true },
  global: { max: 200, strict: 200, seconds: 60 * 60, hard: false },
};
// A unique ticket per lookup: if the reservation call is retried after a network error,
// begin_lookup recognises the ticket and doesn't count the attempt twice.
const token = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
const attempt = { keys: [], limits: [], windows_s: [], hard: [], strict_limits: [], token };
const add = (key, lim) => {
  attempt.keys.push(key);
  attempt.limits.push(lim.max);
  attempt.windows_s.push(lim.seconds);
  attempt.hard.push(lim.hard);
  attempt.strict_limits.push(lim.strict);
};
if (p.order_number && p.email) {
  if (p.session_id) add('s:' + p.session_id, LIMITS.session);
  add('o:' + p.order_number, LIMITS.order);
  add('e:' + p.email, LIMITS.email);
  add('g', LIMITS.global);
}
return [{ json: { attempt } }];
