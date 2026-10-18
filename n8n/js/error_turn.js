// Error branch: the agent or one of its tools failed. Reply with the spec's apology,
// log the error and open a system_error hand-off. Same reply shape as a normal turn.
const p = $('Prepare').first().json;
const err = $input.first().json.error;
const message = typeof err === 'string' ? err : (err && err.message) || JSON.stringify(err || 'unknown error');
const response = {
  answer: "Sorry, something went wrong — I've passed this to our team.",
  session_id: p.session_id,
  tools_called: [],
  article_ids_used: [],
  article_ids_retrieved: [],
  sources: [],
  lookup: null,
  order: null,
  handoff_id: null,
  handoff_verified: null,
  escalated: false,
  latency_ms: Date.now() - p.started_at,
  model: '__MODEL_ID__',
  error: true,
};
return [{
  json: {
    response,
    log: { ...response, user_message: p.message, error: message.slice(0, 2000) },
    handoff: {
      session_id: p.session_id,
      reason: 'system_error',
      summary: ('Agent workflow failed: ' + message).slice(0, 1000),
      verified: false,
    },
  },
}];
