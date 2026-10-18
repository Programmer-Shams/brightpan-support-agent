"""Create the `brightpan-demo` Supabase project and apply supabase/schema.sql.

Touches only the project it creates. It never lists, reads or changes other
projects: the project ref is stored in .env on creation, and every later call
targets that ref only.

Needs SUPABASE_ACCESS_TOKEN in .env (supabase.com/dashboard/account/tokens).
Usage: python3 scripts/supabase_setup.py [--org <slug>]
Idempotent: if SUPABASE_PROJECT_REF is already set it skips creation.
"""
import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import ROOT, load_env, require, set_env  # noqa: E402
from net import SSL_CONTEXT  # noqa: E402

API = "https://api.supabase.com"
PROJECT_NAME = "brightpan-demo"
REGION = "us-east-1"


class ApiError(Exception):
    pass


def api(method: str, path: str, token: str, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "brightpan-demo-setup/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise ApiError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:500]}") from None


def run_sql(query: str, env: dict = None):
    """Run SQL on the brightpan-demo database via the Management API."""
    env = env or load_env()
    require(env, "SUPABASE_ACCESS_TOKEN", "SUPABASE_PROJECT_REF")
    return api("POST", f"/v1/projects/{env['SUPABASE_PROJECT_REF']}/database/query",
               env["SUPABASE_ACCESS_TOKEN"], {"query": query}, timeout=120)


def create_project(token: str, org_slug: str = None) -> str:
    orgs = api("GET", "/v1/organizations", token)
    if org_slug:
        if not any(o["slug"] == org_slug for o in orgs):
            raise SystemExit(f"Organization slug '{org_slug}' not found for this token.")
    elif len(orgs) == 1:
        org_slug = orgs[0]["slug"]
    else:
        print("This token can see several organizations. Re-run with --org <slug>:")
        for o in orgs:
            print(f"  {o['slug']}  ({o['name']})")
        raise SystemExit(1)

    db_pass = secrets.token_urlsafe(24)
    set_env("SUPABASE_DB_PASSWORD", db_pass)
    print(f"Creating project '{PROJECT_NAME}' in org '{org_slug}', region {REGION} ...")
    try:
        project = api("POST", "/v1/projects", token, {
            "name": PROJECT_NAME,
            "organization_slug": org_slug,
            "db_pass": db_pass,
            "region_selection": {"type": "specific", "code": REGION},
        })
    except ApiError as e:
        raise SystemExit(f"Project creation failed (nothing was created):\n{e}")
    ref = project.get("ref") or project["id"]
    set_env("SUPABASE_PROJECT_REF", ref)
    print(f"Created project ref {ref}")
    return ref


def wait_healthy(token: str, ref: str, timeout_s: int = 900):
    start, last = time.time(), None
    while time.time() - start < timeout_s:
        status = api("GET", f"/v1/projects/{ref}", token).get("status")
        if status != last:
            print(f"  status: {status}")
            last = status
        if status == "ACTIVE_HEALTHY":
            return
        if status in ("INIT_FAILED", "REMOVED"):
            raise SystemExit(f"Project entered {status}")
        time.sleep(10)
    raise SystemExit(f"Project not healthy after {timeout_s}s (last status {last})")


def store_keys(token: str, ref: str):
    keys = api("GET", f"/v1/projects/{ref}/api-keys?reveal=true", token)
    service = next((k for k in keys if k.get("name") == "service_role" and k.get("api_key")), None) \
        or next((k for k in keys if k.get("type") == "secret" and k.get("api_key")), None)
    if not service:
        raise SystemExit("No service_role/secret key returned by the API.")
    set_env("SUPABASE_URL", f"https://{ref}.supabase.co")
    set_env("SUPABASE_SERVICE_ROLE_KEY", service["api_key"])
    print(f"Stored SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY ({service.get('name')}, type {service.get('type')}) in .env")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", help="organization slug, if the token sees more than one")
    args = ap.parse_args()

    env = load_env()
    require(env, "SUPABASE_ACCESS_TOKEN")
    token = env["SUPABASE_ACCESS_TOKEN"]
    ref = env.get("SUPABASE_PROJECT_REF") or create_project(token, args.org)

    wait_healthy(token, ref)
    store_keys(token, ref)
    for attempt in range(1, 7):
        try:
            run_sql((ROOT / "supabase" / "schema.sql").read_text())
            break
        except ApiError as e:  # database can lag behind ACTIVE_HEALTHY right after creation
            if attempt == 6:
                raise SystemExit(f"Schema failed: {e}")
            print(f"  schema attempt {attempt} failed, retrying in 15s: {str(e)[:160]}")
            time.sleep(15)
    tables = run_sql("select table_name from information_schema.tables "
                     "where table_schema='public' order by 1;")
    print("Schema applied. Public tables:", ", ".join(t["table_name"] for t in tables))


if __name__ == "__main__":
    main()
