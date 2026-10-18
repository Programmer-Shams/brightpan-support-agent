// Turn the AI Agent output into the webhook reply and the conversation log row.
// A failed tool call throws, so the node's error output sends the turn down the error branch
// (BUILD_SPEC step 4: "on any failure, reply 'Sorry, something went wrong…' and log it").
const p = $('Prepare').first().json;
const out = $input.first().json;

let answer = out.output;
if (Array.isArray(answer)) answer = answer.map(b => (typeof b === 'string' ? b : b.text || '')).join('');
answer = String(answer || '').trim();

// Tool observations arrive as a JSON string of the sub-workflow's output items, e.g. '[{"response": "..."}]'.
const parseObservation = o => {
  if (o && typeof o === 'object') return Array.isArray(o) ? o[0] || {} : o;
  try {
    const j = JSON.parse(o);
    return (Array.isArray(j) ? j[0] : j) || {};
  } catch (e) {
    return { response: String(o || '') };
  }
};

const tools = [];
const retrieved = {}; // article id -> title, from search_help_center results
let lookup = null;
let order = null;
let handoff = null;
for (const step of out.intermediateSteps || []) {
  const tool = step.action && step.action.tool;
  if (!tool) continue;
  tools.push(tool);
  const r = parseObservation(step.observation);
  if (r.error || typeof r.response !== 'string') {
    throw new Error(`Tool ${tool} failed: ${String(r.error || 'no response').slice(0, 300)}`);
  }
  if (tool === 'search_help_center') {
    for (const a of r.articles || []) retrieved[a.id] = a.title;
  } else if (tool === 'lookup_order') {
    if (r.result === 'match') {
      lookup = 'match';
      order = r.order;
    } else if (lookup !== 'match') {
      lookup = r.result === 'no_match' ? 'no_match' : 'incomplete';
    }
  } else if (tool === 'escalate_to_human' && r.handoff_id) {
    handoff = r;
  }
}

// An article counts as used only if the answer names it in a "(Source: …)" citation.
const titles = Object.entries(retrieved).map(([id, title]) => [id, title.toLowerCase()]);
const cited = [];
for (const m of answer.matchAll(/\(Sources?:\s*((?:[^()]|\([^()]*\))*)\)/gi)) {
  for (const part of m[1].split(';')) {
    const name = part.trim().replace(/\.$/, '').toLowerCase();
    if (name.length < 4) continue;
    const hit = titles.find(([, t]) => t === name) || titles.find(([, t]) => t.startsWith(name) || name.startsWith(t));
    if (hit && !cited.includes(hit[0])) cited.push(hit[0]);
  }
}

const response = {
  answer,
  session_id: p.session_id,
  tools_called: tools,
  article_ids_used: cited,
  article_ids_retrieved: Object.keys(retrieved),
  sources: cited.map(id => ({ id, title: retrieved[id] })),
  lookup,
  order,
  handoff_id: handoff ? handoff.handoff_id : null,
  handoff_verified: handoff ? Boolean(handoff.verified) : null,
  escalated: Boolean(handoff),
  latency_ms: Date.now() - p.started_at,
  model: '__MODEL_ID__',
  error: false,
};
return [{ json: { response, log: { ...response, user_message: p.message, error: null } } }];
