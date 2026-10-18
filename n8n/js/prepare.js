// Validate the webhook request. Throws on a bad request; the node's error output replies 400.
const raw = $input.first().json.body;
const body = raw && typeof raw === 'object' ? raw : {};
const message = typeof body.message === 'string' ? body.message.trim().slice(0, 4000) : '';
if (!message) throw new Error('BAD_REQUEST: "message" must be a non-empty string');

const session_id = typeof body.session_id === 'string' && body.session_id.trim()
  ? body.session_id.trim().slice(0, 200)
  : 'web-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

// `today` lets the eval freeze the date (BUILD_SPEC rule 9); only real calendar dates are accepted.
const isRealDate = s => {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(s + 'T00:00:00Z');
  return !isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
};
const etToday = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date());
const today = isRealDate(body.today) ? body.today : etToday;

return [{ json: { session_id, message, today, started_at: Date.now() } }];
