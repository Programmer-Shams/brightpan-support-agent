"""Stub chat endpoint with the same HTTP contract as the n8n webhook.

NOT the agent. A keyword-overlap baseline used to exercise the eval harness
before the real workflow exists: no LLM, no embeddings, never escalates.

Run: python3 eval/stub_agent.py   (listens on http://localhost:5679/chat)
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from kb import load_articles  # noqa: E402

PORT = 5679
MIN_SCORE = 3
STOP = set("a an and are as at be by can do does for from has have how i if in is it its me my of on or "
           "our the this to was what when where which will with you your".split())


def tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


ARTICLES = load_articles()
ORDERS = {o["order_number"]: o for o in json.loads((ROOT / "data" / "orders.json").read_text())}


def reply(message):
    number = re.search(r"\b(\d{4})\b", message)
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", message)
    if number and email:
        order = ORDERS.get(number.group(1))
        if not order or order["email"].lower() != email.group(0).rstrip(".").lower():
            return {"answer": "I couldn't find an order matching that number and email. "
                              "Please check the details and try again.",
                    "tools_called": ["lookup_order"], "article_ids_used": [], "escalated": False}
        items = "; ".join(f"{i['title']}: {i.get('status', order['fulfillment_status'])}" for i in order["items"])
        answer = (f"Order {order['order_number']} status: {order['fulfillment_status']}. Items: {items}. "
                  f"Carrier: {order['carrier']}, tracking {order['tracking_number']}, "
                  f"shipped {order['shipped_date']}, delivered {order['delivered_date']}. {order.get('note', '')}")
        return {"answer": answer, "tools_called": ["lookup_order"], "article_ids_used": [], "escalated": False}

    q = tokens(message)
    best = max(ARTICLES, key=lambda a: len(q & tokens(a["title"] + " " + a["content"])))
    if len(q & tokens(best["title"] + " " + best["content"])) < MIN_SCORE:
        return {"answer": "I don't have that information in our help center. "
                          "I can connect you with our support team if you'd like.",
                "tools_called": ["search_help_center"], "article_ids_used": [], "escalated": False}
    return {"answer": f"{best['content']}\n\n(Source: {best['title']})",
            "tools_called": ["search_help_center"], "article_ids_used": [best["article_id"]], "escalated": False}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        out = json.dumps(reply(body.get("message", ""))).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Stub agent on http://localhost:{PORT}/chat ({len(ARTICLES)} articles, {len(ORDERS)} orders)")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
