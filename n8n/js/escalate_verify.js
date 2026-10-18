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
const email = /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(p.email || '') ? p.email : null;

// Slack Block Kit: system-generated lines are mrkdwn; everything the customer or model supplied goes in
// plain_text (never formatted) with newlines collapsed, so it can't imitate the header or verification line.
const plain = (text, max) => ({ type: 'plain_text', text: String(text).replace(/\s+/g, ' ').trim().slice(0, max) || '-', emoji: false });
const slack_blocks = [
  { type: 'section', fields: [
    plain('Customer: ' + (email || (p.email ? 'invalid email given' : 'not given')), 150),
    plain('Order: ' + (p.order_number ? '#' + p.order_number : 'not given'), 60),
    plain(verified ? 'Email check: matches the order' : 'Email check: NOT verified against an order', 60),
  ] },
  { type: 'section', text: plain('Summary: ' + (summary || '(none)'), 1100) },
];

return [{
  json: {
    row: {
      session_id: p.session_id ? String(p.session_id).slice(0, 200) : null,
      reason, summary: summary || '(none)',
      customer_email: email,
      order_number: p.order_number || null,
      verified,
    },
    slack_title: REASONS[reason],
    slack_blocks,
  },
}];
