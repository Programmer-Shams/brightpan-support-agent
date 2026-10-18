// lookup_order result. Order details are returned ONLY when the order number AND email match;
// an unknown order and a wrong email get the identical NO_MATCH reply (no enumeration).
const { order_number, email } = $('Parse input').first().json;

// Attempt limit (see lookup_keys.js): when any key is at its cap, no order data is returned, even for a
// correct email, so repeated guessing can't succeed. Locks expire after their window.
if ($('Reserve attempt').first().json.locked) {
  return [{ json: {
    response: 'TOO_MANY_ATTEMPTS: Too many order lookups did not match. Do not look up orders again in this ' +
      'conversation and do not share any order details. Offer to connect the customer with the support team.',
    result: 'locked', order: null,
  } }];
}

if (!order_number || !email) {
  return [{ json: {
    response: 'MISSING_INPUT: Ask the customer for both the order number and the email used at checkout.',
    result: 'missing_input', order: null,
  } }];
}
const res = $input.first().json;
if (res.errors) throw new Error('Shopify error: ' + JSON.stringify(res.errors).slice(0, 300));
const o = ((res.data && res.data.orders && res.data.orders.nodes) || []).find(n => n.name === '#' + order_number);
if (!o || String(o.email || '').toLowerCase() !== email) {
  return [{ json: {
    response: 'NO_MATCH: No order matches that order number and email address. ' +
      'Do not share any order details. Ask the customer to double-check both.',
    result: 'no_match', order: null,
  } }];
}

const attr = Object.fromEntries((o.customAttributes || []).map(a => [a.key, a.value]));
const money = m => `$${Number(m.amount).toFixed(2)}`;
const order = {
  number: o.name,
  placed: o.processedAt.slice(0, 10),
  status: attr.fulfillment_status || String(o.displayFulfillmentStatus).toLowerCase(),
  cancelled: Boolean(o.cancelledAt),
  payment: o.displayFinancialStatus,
  ship_to: attr.ship_to || null,
  carrier: attr.carrier || null,
  tracking: attr.tracking_number || null,
  shipped: attr.shipped_date || null,
  delivered: attr.delivered_date || null,
  shipping: money(o.totalShippingPriceSet.shopMoney),
  total: money(o.totalPriceSet.shopMoney),
  currency: o.totalPriceSet.shopMoney.currencyCode,
  note: attr.note || null,
  items: o.lineItems.nodes.map(li => {
    const props = Object.fromEntries((li.customAttributes || []).map(a => [a.key, a.value]));
    return {
      qty: li.quantity,
      title: li.title,
      price: money(li.originalUnitPriceSet.shopMoney),
      status: props.status || null,
      final_sale: props.final_sale === 'true',
    };
  }),
};

const lines = [
  `MATCH: Order ${order.number} (email verified)`,
  `Placed: ${order.placed}`,
  `Status: ${order.status}${order.cancelled ? ' (order cancelled)' : ''}`,
  `Payment: ${order.payment}`,
  `Ship to: ${order.ship_to || 'unknown'}`,
  `Carrier: ${order.carrier || 'not assigned yet'}`,
  `Tracking number: ${order.tracking || 'none yet'}`,
  `Shipped: ${order.shipped || 'not shipped yet'}`,
  `Delivered: ${order.delivered || 'not delivered yet'}`,
  `Shipping charged: ${order.shipping} ${order.currency}`,
  `Order total: ${order.total} ${order.currency}`,
  'Items:',
  ...order.items.map(i => `- ${i.qty} x ${i.title} (${i.price} ${order.currency})` +
    (i.status ? ` — item status: ${i.status}` : '') + (i.final_sale ? ' — final sale' : '')),
];
if (order.note) lines.push(`Note: ${order.note}`);
return [{ json: { response: lines.join('\n'), result: 'match', order } }];
