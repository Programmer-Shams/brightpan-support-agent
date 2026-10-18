// Normalize the order number and email the model passed in (shared by lookup_order and escalate_to_human).
// Digits only for the order number, so nothing else can reach the Shopify search query.
const raw = $input.first().json;
const clean = v => String(v == null ? '' : v).trim();
const order_number = clean(raw.order_number).replace(/\D/g, '').slice(0, 12);
const emailField = raw.email !== undefined ? raw.email : raw.customer_email;
const email = clean(emailField).replace(/[.,;:!?)\]]+$/, '').toLowerCase().slice(0, 254);
return [{ json: { ...raw, order_number, email } }];
