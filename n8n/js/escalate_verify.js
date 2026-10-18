// escalate_to_human: check the customer's email against the order in Shopify, so the support team
// can see whether the hand-off is verified, and build a Slack-safe message body.
const p = $('Parse input').first().json;
const res = $input.first().json;
const o = ((res.data && res.data.orders && res.data.orders.nodes) || []).find(n => n.name === '#' + p.order_number);
const verified = Boolean(o && p.email && String(o.email || '').toLowerCase() === p.email);

const REASONS = {
  refund: 'Refund request', damaged_or_wrong_item: 'Damaged, defective or wrong item', warranty: 'Warranty claim',
  order_change: 'Order change', complaint: 'Complaint', chargeback_or_legal: 'Chargeback or legal threat',
  customer_request: 'Customer asked for a person', other: 'Other',
};
const reason = Object.prototype.hasOwnProperty.call(REASONS, p.reason) ? p.reason : 'other';
const summary = String(p.summary == null ? '' : p.summary).trim().slice(0, 1000);
// Slack mrkdwn: escape &, <, > so customer text can't create mentions or links.
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const slack_body =
  `*${REASONS[reason]}*\n` +
  `*Customer:* ${p.email ? esc(p.email) : 'not given'} | *Order:* ${p.order_number ? '#' + p.order_number : 'not given'} | ` +
  (verified ? ':white_check_mark: email matches order' : ':warning: not verified against an order') +
  `\n*Summary:* ${esc(summary || '(none)')}`;

return [{
  json: {
    row: {
      session_id: p.session_id ? String(p.session_id).slice(0, 200) : null,
      reason, summary: summary || '(none)',
      customer_email: p.email || null,
      order_number: p.order_number || null,
      verified,
    },
    slack_body,
  },
}];
