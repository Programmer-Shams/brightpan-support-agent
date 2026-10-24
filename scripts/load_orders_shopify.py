"""Create the 15 test orders from data/orders.json in the Shopify dev store (BUILD_SPEC step 3).

Scopes: read_orders, write_orders only. Native order fields carry what those scopes
allow (name #10xx, email, date, line items, shipping, financial/fulfillment status,
cancellation). A native fulfillment needs a location id (read_locations), so carrier,
tracking number, shipped/delivered dates and per-item status are stored as order
custom attributes instead.

Idempotent: orders already tagged bp-<order_number> are skipped, except that an order which
should be cancelled but isn't (e.g. a run that died between create and cancel) is cancelled.
Usage: python3 scripts/load_orders_shopify.py [--only 1001,1002]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import ROOT  # noqa: E402
from shopify_api import gql  # noqa: E402

CURRENCY = "USD"

CREATE = """
mutation($order: OrderCreateOrderInput!, $options: OrderCreateOptionsInput) {
  orderCreate(order: $order, options: $options) {
    userErrors { field message }
    order { id name displayFinancialStatus displayFulfillmentStatus currencyCode
            totalPriceSet { shopMoney { amount currencyCode } } }
  }
}"""

CANCEL = """
mutation($id: ID!) {
  orderCancel(orderId: $id, reason: CUSTOMER, refundMethod: { originalPaymentMethodsRefund: false }, restock: false, notifyCustomer: false) {
    orderCancelUserErrors { field message }
    job { id }
  }
}"""

FINANCIAL = {"paid": "PAID", "refunded": "REFUNDED"}
FULFILLMENT = {"fulfilled": "FULFILLED", "partially_fulfilled": "PARTIAL"}  # unfulfilled/cancelled: omit


def money(amount):
    return {"shopMoney": {"amount": f"{amount:.2f}", "currencyCode": CURRENCY}}


def order_input(o: dict) -> dict:
    first, _, last = o["name"].partition(" ")
    address = {"firstName": first, "lastName": last, "countryCode": o["country"]}
    if o.get("state"):
        address["provinceCode"] = o["state"]
    attrs = {
        "order_number": o["order_number"],
        "ship_to": ", ".join(x for x in (o.get("state"), o["country"]) if x),
        "carrier": o.get("carrier"),
        "tracking_number": o.get("tracking_number"),
        "shipped_date": o.get("shipped_date"),
        "delivered_date": o.get("delivered_date"),
        "fulfillment_status": o["fulfillment_status"],
        "note": o.get("note"),
    }
    line_items = []
    for item in o["items"]:
        props = [{"name": "status", "value": item["status"]}] if item.get("status") else []
        if item.get("final_sale"):
            props.append({"name": "final_sale", "value": "true"})
        line_items.append({
            "title": item["title"], "sku": item["sku"], "quantity": item["qty"],
            "priceSet": money(item["price"]), "requiresShipping": not item["sku"].startswith("GC-"),
            "giftCard": item["sku"].startswith("GC-"), **({"properties": props} if props else {}),
        })
    order = {
        "name": f"#{o['order_number']}",
        "email": o["email"],
        "currency": CURRENCY,
        "processedAt": f"{o['created']}T12:00:00-04:00",
        "lineItems": line_items,
        "shippingAddress": address,
        "billingAddress": address,
        "financialStatus": FINANCIAL[o["financial_status"]],
        "tags": [f"bp-{o['order_number']}", "brightpan-demo"],
        "customAttributes": [{"key": k, "value": str(v)} for k, v in attrs.items() if v is not None],
    }
    if o.get("note"):
        order["note"] = o["note"]
    if o["shipping"]:
        order["shippingLines"] = [{"title": "Shipping", "priceSet": money(o["shipping"])}]
    if o["fulfillment_status"] in FULFILLMENT:
        order["fulfillmentStatus"] = FULFILLMENT[o["fulfillment_status"]]
    return order


def existing(order_number: str):
    r = gql('query($q:String!){ orders(first:1, query:$q){ nodes { id name cancelledAt } } }',
            {"q": f"tag:bp-{order_number}"})
    nodes = r["data"]["orders"]["nodes"]
    return nodes[0] if nodes else None


def cancel(order_id: str):
    c = gql(CANCEL, {"id": order_id})
    errs = c.get("errors") or ((c.get("data") or {}).get("orderCancel") or {}).get("orderCancelUserErrors")
    print(f"   cancel: {'FAILED ' + str(errs) if errs else 'requested'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated order numbers")
    args = ap.parse_args()
    orders = json.loads((ROOT / "data" / "orders.json").read_text())
    if args.only:
        orders = [o for o in orders if o["order_number"] in args.only.split(",")]

    created = skipped = failed = 0
    for o in orders:
        if found := existing(o["order_number"]):
            if o["fulfillment_status"] == "cancelled" and not found["cancelledAt"]:
                print(f"{o['order_number']}: exists as {found['name']} but isn't cancelled — cancelling")
                cancel(found["id"])
            else:
                print(f"{o['order_number']}: exists as {found['name']} — skipped")
            skipped += 1
            continue
        for attempt in range(6):  # dev stores throttle orderCreate ("Too many attempts")
            r = gql(CREATE, {"order": order_input(o),
                             "options": {"sendReceipt": False, "sendFulfillmentReceipt": False,
                                         "inventoryBehaviour": "BYPASS"}})
            res = (r.get("data") or {}).get("orderCreate") or {}
            if "Too many attempts" not in json.dumps(res.get("userErrors") or []):
                break
            print(f"{o['order_number']}: throttled, waiting 30s")
            time.sleep(30)
        if r.get("errors") or res.get("userErrors") or not res.get("order"):
            print(f"{o['order_number']}: FAILED {r.get('errors') or res.get('userErrors')}")
            failed += 1
            continue
        so = res["order"]
        total = so["totalPriceSet"]["shopMoney"]
        print(f"{o['order_number']}: created {so['name']} | {so['displayFinancialStatus']} / "
              f"{so['displayFulfillmentStatus']} | {total['amount']} {total['currencyCode']}")
        if o["fulfillment_status"] == "cancelled":
            cancel(so["id"])
        created += 1
    print(f"\nCreated {created}, skipped {skipped}, failed {failed}")


if __name__ == "__main__":
    main()
