"""Eval harness for the Brightpan support agent (BUILD_SPEC step 6).

Sends each test question as a fresh session to the chat endpoint, grades the
reply automatically, writes a CSV for manual review and prints the summary.

Endpoint contract (n8n webhook or stub):
  request : POST {"session_id": str, "message": str, "today": "YYYY-MM-DD"}
            header X-Brightpan-Key: N8N_WEBHOOK_SECRET from .env (the stub ignores it)
  response: {"answer": str, "tools_called": [str], "article_ids_used": [str] (articles cited in "(Source: …)"),
             "escalated": bool (a hand-off was saved), "lookup": "match"|"no_match"|..., "order": {...}|null,
             "error": bool (the workflow's error branch replied); see n8n/js/build_turn.js for the full shape}

Usage:
  python3 eval/run_eval.py                              # uses N8N_WEBHOOK_URL from .env
  python3 eval/run_eval.py --endpoint http://localhost:5679/chat --label stub --out eval/results-stub.csv
  python3 eval/run_eval.py --label claude --log         # also append summary to eval/results-log.md
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from envfile import load_env  # noqa: E402

TESTSET = ROOT / "eval" / "testset.csv"
ORDERS = ROOT / "data" / "orders.json"
KB = ROOT / "kb" / "help-center.md"
LOG = ROOT / "eval" / "results-log.md"
FROZEN_TODAY = "2026-10-18"

LOOKUP_TOOL = "lookup_order"
ESCALATE_TOOL = "escalate_to_human"

# "7–12", "7-12" and "7 to 12" all compare equal.
_RANGE = re.compile(r"(\d)\s*[‐-―\-]\s*(\d)")

_DECLINE = re.compile(
    r"don't have|do not have|doesn't (?:cover|include|mention)|does not (?:cover|include|mention)"
    r"|isn't covered|is not covered|not covered in|no information|couldn't find|could not find"
    r"|can't find|cannot find|wasn't able|was not able|unable to|not able to"
    r"|can't help|cannot help|can't share|cannot share|can't provide|cannot provide"
    r"|can't give|cannot give|can't offer|cannot offer|i can only help|only able to help"
    r"|outside (?:of )?what i can|not something i can|no record|couldn't locate|could not locate"
    r"|doesn't match|does not match|didn't match|did not match|check the (?:order number|details|email)"
    r"|double-check|not in our help center|isn't in our help center"
)


def normalize(text: str) -> str:
    text = (text or "").replace("’", "'").replace("‘", "'")
    text = _RANGE.sub(r"\1 to \2", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def missing_items(answer: str, must_include: str) -> list:
    """Return the must_include items (| separated, ~ alternatives) not found in answer."""
    norm = normalize(answer)
    missing = []
    for item in (must_include or "").split("|"):
        if not item.strip():
            continue
        alternatives = [normalize(a) for a in item.split("~") if a.strip()]
        if not any(alt in norm for alt in alternatives):
            missing.append(item.strip())
    return missing


def sensitive_order_strings() -> list:
    """Strings that only appear if order data is revealed (KB terms excluded)."""
    kb = normalize(KB.read_text())
    out = []
    for o in json.loads(ORDERS.read_text()):
        out += [o["name"], o["email"]]
        if o.get("tracking_number"):
            out.append(o["tracking_number"])
        out += [i["title"] for i in o["items"]]
        out += [d for d in (o.get("created"), o.get("shipped_date"), o.get("delivered_date")) if d]
    return sorted({s for s in out if normalize(s) not in kb})


def leaked_order_data(answer: str, question: str, sensitive: list) -> list:
    norm_a, norm_q = normalize(answer), normalize(question)
    return [s for s in sensitive if normalize(s) in norm_a and normalize(s) not in norm_q]


def grade(row: dict, resp: dict, sensitive: list) -> dict:
    """Auto-grade one reply per BUILD_SPEC step 6. Returns pass flag and reasons."""
    cat = row["category"]
    answer = resp.get("answer", "")
    tools = [t.lower() for t in resp.get("tools_called", [])]
    articles = [a.upper() for a in resp.get("article_ids_used", [])]
    escalated = ESCALATE_TOOL in tools
    # The workflow reports escalated=true only once the hand-off row is saved; the stub omits the flag.
    handoff_saved = escalated and resp.get("escalated_flag") is not False
    leaks = leaked_order_data(answer, row["question"], sensitive)
    reasons = []
    manual = False

    if resp.get("error"):
        reasons.append(f"request error: {resp['error']}")
    elif cat in ("answerable", "order_lookup"):
        for item in missing_items(answer, row["must_include"]):
            reasons.append(f"missing '{item}'")
        for part in row["source"].split("+"):
            if part == "ORDERS":
                if LOOKUP_TOOL not in tools:
                    reasons.append("lookup_order not called")
            elif part.upper() not in articles:
                reasons.append(f"source {part} not used")
    elif cat == "refuse":
        manual = True
        if escalated:
            reasons.append("escalated unnecessarily")
        if leaks:
            reasons.append(f"order data revealed: {', '.join(leaks)}")
        if resp.get("lookup") == "match" or resp.get("order"):
            reasons.append("order lookup matched and returned order data")
        if not _DECLINE.search(normalize(answer)):
            reasons.append("no decline/'don't have that' wording found")
    elif cat == "escalate":
        if not escalated:
            reasons.append("escalate_to_human not called")
        elif not handoff_saved:
            reasons.append("escalate_to_human called but no hand-off was saved")
        for item in missing_items(answer, row["must_include"]):
            reasons.append(f"missing '{item}'")
    else:
        reasons.append(f"unknown category {cat}")

    return {
        "auto_pass": not reasons,
        "fail_reasons": "; ".join(reasons),
        "needs_manual_review": manual,
        "escalated": handoff_saved,
        "order_strings_in_answer": "; ".join(leaks),
    }


def call_endpoint(url: str, session_id: str, message: str, today: str, timeout: float, key: str = "") -> tuple:
    body = json.dumps({"session_id": session_id, "message": message, "today": today}).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Brightpan-Key"] = key
    req = urllib.request.Request(url, data=body, headers=headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
        latency_ms = round((time.perf_counter() - start) * 1000)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"error": str(e)}, round((time.perf_counter() - start) * 1000)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": f"non-JSON response: {raw[:200]}"}, latency_ms
    if isinstance(data, list):
        data = data[0] if data else {}
    if data.get("error"):  # the workflow's error branch replies 200 with error: true
        return {"error": "workflow error branch (see conversations.error in Supabase)",
                "answer": data.get("answer", "")}, latency_ms
    return {
        "answer": data.get("answer", data.get("output", "")),
        "tools_called": data.get("tools_called") or [],
        "article_ids_used": data.get("article_ids_used") or [],
        "escalated_flag": data.get("escalated"),
        "lookup": data.get("lookup"),
        "order": data.get("order"),
    }, latency_ms


def percentile_nearest_rank(values: list, pct: float):
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(pct / 100 * len(s)) - 1)]


def summarize(rows: list) -> dict:
    def rate(cats):
        sel = [r for r in rows if r["category"] in cats]
        return sum(r["auto_pass"] for r in sel), len(sel)

    lat = [r["latency_ms"] for r in rows if not r["error"]]
    return {
        "policy_lookup": rate(("answerable", "order_lookup")),
        "refuse": rate(("refuse",)),
        "escalate": rate(("escalate",)),
        "errors": sum(1 for r in rows if r["error"]),
        "median_ms": statistics.median(lat) if lat else None,
        "p90_ms": percentile_nearest_rank(lat, 90),
        "n": len(rows),
    }


def fmt_pct(passed, total):
    return f"{passed}/{total} ({100 * passed / total:.1f}%)" if total else "n/a"


def fmt_s(ms):
    return "n/a" if ms is None else f"{ms / 1000:.2f} s"


def summary_lines(s: dict) -> list:
    return [
        f"Correct (policy + lookups): {fmt_pct(*s['policy_lookup'])}",
        f"Correct refusals (auto, pending manual review): {fmt_pct(*s['refuse'])}",
        f"Correct escalations: {fmt_pct(*s['escalate'])}",
        f"Request errors: {s['errors']}/{s['n']}",
        f"Latency median: {fmt_s(s['median_ms'])} | p90 (nearest-rank): {fmt_s(s['p90_ms'])}",
    ]


FIELDS = [
    "run_id", "label", "id", "category", "question", "expected_behavior", "must_include", "source",
    "answer", "tools_called", "article_ids_used", "escalated", "escalated_flag", "latency_ms",
    "auto_pass", "fail_reasons", "order_strings_in_answer", "needs_manual_review",
    "manual_verdict", "manual_notes", "error",
]


def main():
    env = load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=env.get("N8N_WEBHOOK_URL"))
    ap.add_argument("--label", default="unlabeled", help="e.g. stub, claude, openai")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results.csv"))
    ap.add_argument("--today", default=FROZEN_TODAY)
    ap.add_argument("--only", help="comma-separated ids, e.g. Q01,Q31")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--log", action="store_true", help="append summary to eval/results-log.md")
    args = ap.parse_args()
    if not args.endpoint:
        raise SystemExit("No endpoint: pass --endpoint or set N8N_WEBHOOK_URL in .env")

    tests = list(csv.DictReader(TESTSET.open()))
    if args.only:
        wanted = set(args.only.split(","))
        tests = [t for t in tests if t["id"] in wanted]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sensitive = sensitive_order_strings()
    rows = []
    for t in tests:
        session_id = f"eval-{run_id}-{t['id']}-{uuid.uuid4().hex[:6]}"
        resp, latency = call_endpoint(args.endpoint, session_id, t["question"], args.today, args.timeout,
                                      env.get("N8N_WEBHOOK_SECRET", ""))
        g = grade(t, resp, sensitive)
        row = {
            **t,
            "run_id": run_id,
            "label": args.label,
            "answer": resp.get("answer", ""),
            "tools_called": "|".join(resp.get("tools_called", [])),
            "article_ids_used": "|".join(resp.get("article_ids_used", [])),
            "escalated_flag": resp.get("escalated_flag"),
            "latency_ms": latency,
            "manual_verdict": "",
            "manual_notes": "",
            "error": resp.get("error", ""),
            **g,
        }
        rows.append(row)
        mark = "PASS" if g["auto_pass"] else "FAIL"
        print(f"{t['id']} {t['category']:<12} {mark} {latency:>6} ms  {g['fail_reasons']}")

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    s = summarize(rows)
    print(f"\nRun {run_id} | label={args.label} | endpoint={args.endpoint} | today={args.today}")
    for line in summary_lines(s):
        print(line)
    print(f"Wrote {args.out}")

    if args.log:
        with LOG.open("a") as f:
            f.write(f"\n## Run {run_id} — {args.label}\n\n")
            f.write(f"- Endpoint: `{args.endpoint}` | today={args.today} | questions: {s['n']}\n")
            f.write(f"- Results file: `{Path(args.out).name}`\n")
            for line in summary_lines(s):
                f.write(f"- {line}\n")
            f.write("- Manual review: pending\n")
        print(f"Appended summary to {LOG}")


if __name__ == "__main__":
    main()
