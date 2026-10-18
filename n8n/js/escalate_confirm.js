// escalate_to_human result. Reaching this node means the hand-off row was saved;
// a failed Slack alert is reported but doesn't undo the hand-off.
const h = $('Save handoff').first().json;
const verified = $('Verify customer').first().json.row.verified;
let slack = 'off';
try {
  const s = $('Notify Slack').first().json;
  slack = s && s.error ? 'failed' : 'sent';
} catch (e) {
  // No Slack node in this deployment (SLACK_WEBHOOK_URL not set).
}
return [{
  json: {
    response: `ESCALATED: Handoff #${h.id} saved for the support team` +
      (slack === 'failed' ? ' (the Slack alert failed, but the ticket is saved)' : '') + '. ' +
      'Tell the customer a person will reply within 1 business day (Mon–Fri, 9:00 am–6:00 pm ET).',
    handoff_id: h.id,
    verified,
    slack,
  },
}];
