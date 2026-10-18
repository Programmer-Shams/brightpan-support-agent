"""Ingest kb/help-center.md into Supabase `kb_chunks` (BUILD_SPEC step 2).

One chunk per `## [Axx]` article, embedded with OpenAI text-embedding-3-small.
Re-run after editing the help center: rows are upserted by article_id and
articles removed from the file are deleted.

Then checks retrieval: for every test question with an article source, is the
expected article in the top 4 from match_kb_chunks? (Retrieval only, not the agent.)

Usage: python3 ingest/ingest_kb.py [--skip-check]
"""
import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from envfile import load_env, require  # noqa: E402
from kb import load_articles  # noqa: E402
from net import SSL_CONTEXT  # noqa: E402
from supabase_setup import run_sql  # noqa: E402

MODEL = "text-embedding-3-small"
DIMS = 1536
TOP_K = 4


def embed(texts: list, api_key: str) -> list:
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps({"model": MODEL, "input": texts}).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"OpenAI embeddings failed: HTTP {e.code}: {e.read().decode()[:300]}")
    vectors = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    assert all(len(v) == DIMS for v in vectors), "unexpected embedding size"
    return vectors


def lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def vec(v: list) -> str:
    return "'[" + ",".join(f"{x:.8f}" for x in v) + "]'::extensions.vector"


def ingest(env: dict) -> list:
    articles = load_articles()
    vectors = embed([f"{a['title']}\n\n{a['content']}" for a in articles], env["OPENAI_API_KEY"])
    values = ",\n".join(
        f"({lit(a['article_id'])}, {lit(a['title'])}, {lit(a['content'])}, "
        f"{lit(json.dumps({'article_id': a['article_id'], 'title': a['title']}))}::jsonb, {vec(v)}, now())"
        for a, v in zip(articles, vectors)
    )
    ids = ", ".join(lit(a["article_id"]) for a in articles)
    run_sql(f"""
        insert into public.kb_chunks (article_id, title, content, metadata, embedding, updated_at)
        values {values}
        on conflict (article_id) do update set
          title = excluded.title, content = excluded.content, metadata = excluded.metadata,
          embedding = excluded.embedding, updated_at = now();
        delete from public.kb_chunks where article_id not in ({ids});
    """, env)
    count = run_sql("select count(*)::int as n from public.kb_chunks;", env)[0]["n"]
    print(f"Embedded {len(articles)} articles with {MODEL}; kb_chunks now has {count} rows.")
    return articles


def check_retrieval(env: dict):
    rows = [r for r in csv.DictReader((ROOT / "eval" / "testset.csv").open())
            if any(p.startswith("A") for p in r["source"].split("+"))]
    vectors = embed([r["question"] for r in rows], env["OPENAI_API_KEY"])
    hits = 0
    print(f"\nRetrieval check (expected article in top {TOP_K}):")
    for r, v in zip(rows, vectors):
        expected = {p for p in r["source"].split("+") if p.startswith("A")}
        got = [x["article_id"] for x in run_sql(
            f"select article_id from public.match_kb_chunks({vec(v)}, {TOP_K});", env)]
        ok = expected <= set(got)
        hits += ok
        print(f"  {r['id']} {'HIT ' if ok else 'MISS'} expected {'+'.join(sorted(expected))} got {got}")
    print(f"Retrieval hit rate @ {TOP_K}: {hits}/{len(rows)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-check", action="store_true")
    args = ap.parse_args()
    env = load_env()
    require(env, "OPENAI_API_KEY", "SUPABASE_ACCESS_TOKEN", "SUPABASE_PROJECT_REF")
    ingest(env)
    if not args.skip_check:
        check_retrieval(env)


if __name__ == "__main__":
    main()
