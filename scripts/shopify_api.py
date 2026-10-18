"""Shopify Admin GraphQL client using the client credentials grant (token cached in memory)."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import load_env, require  # noqa: E402
from net import SSL_CONTEXT  # noqa: E402

API_VERSION = "2026-10"
_token = {"value": None, "expires": 0}


def _shop(env):
    return env["SHOPIFY_STORE_DOMAIN"].removesuffix(".myshopify.com")


def access_token(env=None) -> str:
    env = env or load_env()
    require(env, "SHOPIFY_STORE_DOMAIN", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET")
    if _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    req = urllib.request.Request(
        f"https://{_shop(env)}.myshopify.com/admin/oauth/access_token",
        data=urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": env["SHOPIFY_CLIENT_ID"],
                                     "client_secret": env["SHOPIFY_CLIENT_SECRET"]}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT).read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Shopify token request failed: HTTP {e.code}: {e.read().decode()[:300]}")
    if "access_token" not in d:
        raise SystemExit(f"Shopify token response had no access_token: {str(d)[:300]}")
    _token.update(value=d["access_token"], expires=time.time() + d.get("expires_in", 0))
    return _token["value"]


def gql(query: str, variables: dict = None, env=None) -> dict:
    env = env or load_env()
    req = urllib.request.Request(
        f"https://{_shop(env)}.myshopify.com/admin/api/{API_VERSION}/graphql.json",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": access_token(env)})
    for attempt in range(5):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT).read())
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < 4:
                time.sleep(float(e.headers.get("Retry-After") or 2 ** attempt))
                continue
            raise SystemExit(f"Shopify HTTP {e.code}: {e.read().decode()[:400]}")
