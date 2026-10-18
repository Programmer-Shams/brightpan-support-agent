// Keys and limits for order-lookup attempt limiting (enforced atomically by public.begin_lookup in Supabase).
// Failed guesses are capped per conversation, per order number, per email and globally.
const p = $input.first().json;
const LIMITS = { session: [3, 15 * 60], order: [5, 60 * 60], email: [5, 60 * 60], global: [200, 60 * 60] };
const keys = [];
const limits = [];
const windows_s = [];
const add = (key, [max, seconds]) => { keys.push(key); limits.push(max); windows_s.push(seconds); };
if (p.order_number && p.email) {
  if (p.session_id) add('s:' + p.session_id, LIMITS.session);
  add('o:' + p.order_number, LIMITS.order);
  add('e:' + p.email, LIMITS.email);
  add('g', LIMITS.global);
}
return [{ json: { attempt: { keys, limits, windows_s } } }];
