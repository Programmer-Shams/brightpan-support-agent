"""Deploy the Brightpan workflows to local n8n through its public API.

1. Creates (or recreates with --refresh-credentials) the n8n credentials from .env.
   Secrets go straight from .env into n8n; they are never printed or written to the repo.
   N8N_WEBHOOK_SECRET is generated on first run and copied to web/.env.local for the chat proxy.
2. Builds the workflow JSON (build_workflows.py), fills deploy-time placeholders,
   creates or updates each workflow by name, and activates all of them
   (n8n 2.x refuses to run inactive sub-workflows).

Ids are kept in n8n/.deploy-state.json (git-ignored).
Usage: python3 n8n/deploy.py [--refresh-credentials] [--no-slack] [--purge-token-executions]
  --no-slack                 deploy escalations without the Slack step (used during eval runs)
  --purge-token-executions   delete stored executions of the workflows that handle the Shopify token
"""
import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))
from envfile import load_env, require, set_env  # noqa: E402
from net import SSL_CONTEXT  # noqa: E402
from build_workflows import WEBHOOK_AUTH_HEADER, build  # noqa: E402

STATE = HERE / ".deploy-state.json"
WEB_ENV = ROOT / "web" / ".env.local"
TOKEN_WORKFLOWS = ("tool-lookup-order", "tool-escalate-to-human")


class N8n:
    def __init__(self, env):
        self.base = env["N8N_BASE_URL"].rstrip("/") + "/api/v1"
        self.key = env["N8N_API_KEY"]

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-N8N-API-KEY": self.key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise SystemExit(f"n8n API {method} {path} -> HTTP {e.code}: {e.read().decode()[:600]}")


def wait_for_api(api, timeout_s=90):
    """Right after a container start, n8n answers /healthz before its public API is mounted."""
    deadline = time.time() + timeout_s
    while True:
        try:
            req = urllib.request.Request(api.base + "/workflows?limit=1", headers={"X-N8N-API-KEY": api.key})
            urllib.request.urlopen(req, timeout=5, context=SSL_CONTEXT)
            return
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise SystemExit("n8n rejected N8N_API_KEY. Create a new key in n8n Settings > n8n API.")
        except (urllib.error.URLError, OSError):
            pass
        if time.time() > deadline:
            raise SystemExit(f"n8n API not reachable at {api.base} after {timeout_s}s. Is it running (n8n/start.sh)?")
        time.sleep(2)


def ensure_webhook_secret(env):
    """Shared secret the chat proxy and eval send in the X-Brightpan-Key header."""
    if not env.get("N8N_WEBHOOK_SECRET"):
        env["N8N_WEBHOOK_SECRET"] = secrets.token_urlsafe(32)
        set_env("N8N_WEBHOOK_SECRET", env["N8N_WEBHOOK_SECRET"])
        print("generated N8N_WEBHOOK_SECRET in .env")
    if WEB_ENV.exists() and dict(line.split("=", 1) for line in WEB_ENV.read_text().splitlines() if "=" in line
                                 ).get("N8N_WEBHOOK_SECRET") != env["N8N_WEBHOOK_SECRET"]:
        set_env("N8N_WEBHOOK_SECRET", env["N8N_WEBHOOK_SECRET"], WEB_ENV)
        print("copied N8N_WEBHOOK_SECRET to web/.env.local")


def credential_specs(env):
    shop_auth = {"body": {"client_id": env["SHOPIFY_CLIENT_ID"], "client_secret": env["SHOPIFY_CLIENT_SECRET"]}}
    return {
        "ANTHROPIC": ("Brightpan Anthropic", "anthropicApi", {"apiKey": env["ANTHROPIC_API_KEY"]}),
        "OPENAI": ("Brightpan OpenAI", "openAiApi", {"apiKey": env["OPENAI_API_KEY"]}),
        "SUPABASE": ("Brightpan Supabase", "supabaseApi",
                     {"host": env["SUPABASE_URL"], "serviceRole": env["SUPABASE_SERVICE_ROLE_KEY"]}),
        "SHOPIFY": ("Brightpan Shopify client", "httpCustomAuth", {"json": json.dumps(shop_auth)}),
        "WEBHOOK": ("Brightpan webhook key", "httpHeaderAuth",
                    {"name": WEBHOOK_AUTH_HEADER, "value": env["N8N_WEBHOOK_SECRET"]}),
    }


def ensure_credentials(api, env, state, refresh):
    creds = state.setdefault("credentials", {})
    for key, (name, ctype, data) in credential_specs(env).items():
        if creds.get(key) and refresh:
            api.call("DELETE", f"/credentials/{creds[key]}")
            creds.pop(key)
        if not creds.get(key):
            creds[key] = api.call("POST", "/credentials", {"name": name, "type": ctype, "data": data})["id"]
            print(f"credential created: {name} ({ctype})")
        else:
            print(f"credential kept:    {name}")
    STATE.write_text(json.dumps(state, indent=2))
    return creds


def fill(wf: dict, values: dict) -> dict:
    # Escape each value as a JSON string body so quotes or backslashes can't break the document.
    text = json.dumps(wf)
    for k, v in values.items():
        text = text.replace(k, json.dumps(v)[1:-1])
    leftover = [p for p in ("__CRED_", "__WF_", "__SUPABASE_URL__", "__SHOPIFY_SHOP__", "__SLACK_WEBHOOK_URL__")
                if p in text]
    if leftover:
        raise SystemExit(f"Unfilled placeholders in {wf['name']}: {leftover}")
    return json.loads(text)


def upsert_workflow(api, state, key, wf):
    wfs = state.setdefault("workflows", {})
    body = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
    if wfs.get(key):
        api.call("PUT", f"/workflows/{wfs[key]}", body)
        print(f"workflow updated: {wf['name']} ({wfs[key]})")
    else:
        wfs[key] = api.call("POST", "/workflows", body)["id"]
        print(f"workflow created: {wf['name']} ({wfs[key]})")
    STATE.write_text(json.dumps(state, indent=2))
    api.call("POST", f"/workflows/{wfs[key]}/activate")
    return wfs[key]


def purge_executions(api, workflow_id):
    deleted = 0
    while True:
        page = api.call("GET", f"/executions?workflowId={workflow_id}&limit=250")["data"]
        if not page:
            return deleted
        for x in page:
            api.call("DELETE", f"/executions/{x['id']}")
            deleted += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-credentials", action="store_true")
    ap.add_argument("--no-slack", action="store_true")
    ap.add_argument("--purge-token-executions", action="store_true")
    args = ap.parse_args()
    env = load_env()
    require(env, "N8N_BASE_URL", "N8N_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY", "SHOPIFY_STORE_DOMAIN", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET")
    ensure_webhook_secret(env)
    api = N8n(env)
    wait_for_api(api)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    creds = ensure_credentials(api, env, state, args.refresh_credentials)

    slack_url = env.get("SLACK_WEBHOOK_URL", "")
    slack = slack_url.startswith("https://hooks.slack.com/") and not args.no_slack
    if slack_url and not slack_url.startswith("https://hooks.slack.com/"):
        print("WARNING: SLACK_WEBHOOK_URL is set but is not a https://hooks.slack.com/ URL; Slack step skipped.")
    workflows = build(slack=slack)
    values = {f"__CRED_{k}__": v for k, v in creds.items()}
    values.update({"__SUPABASE_URL__": env["SUPABASE_URL"].rstrip("/"),
                   "__SHOPIFY_SHOP__": env["SHOPIFY_STORE_DOMAIN"].removesuffix(".myshopify.com"),
                   "__SLACK_WEBHOOK_URL__": slack_url if slack else ""})

    for key, ph in [("tool-search-help-center", "__WF_SEARCH__"), ("tool-lookup-order", "__WF_LOOKUP__"),
                    ("tool-escalate-to-human", "__WF_ESCALATE__")]:
        values[ph] = upsert_workflow(api, state, key, fill(workflows[key], values))
    for key in ("agent-claude", "agent-openai"):
        upsert_workflow(api, state, key, fill(workflows[key], values))

    if args.purge_token_executions:
        for key in TOKEN_WORKFLOWS:
            print(f"purged {purge_executions(api, state['workflows'][key])} stored executions of {key}")

    base = env["N8N_BASE_URL"].rstrip("/")
    print(f"\nAll 5 workflows active. Slack notifications: {'on' if slack else 'off'}")
    print(f"Claude endpoint: {base}/webhook/brightpan-chat  (header {WEBHOOK_AUTH_HEADER} required)")
    print(f"OpenAI endpoint: {base}/webhook/brightpan-chat-openai")


if __name__ == "__main__":
    main()
