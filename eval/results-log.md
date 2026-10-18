# Eval results log

Every run of `eval/run_eval.py --log` against the real n8n workflow is appended here, as measured. Auto-grades are pending until the manual review (BUILD_SPEC step 6) is done.

## Run 20261018T071633Z — claude-opus-5-5 (run 1)

> **INVALID — do not use these numbers.** From Q23 on, the n8n container lost DNS/network (`getaddrinfo ENOTFOUND` to Supabase, `Connection error.` from the Anthropic API) and Q23–Q40 hit the error branch. Network recovered right after; the harness now counts error-branch replies as request errors.
> Its per-row results file was overwritten by run 2 (same --out path); only this summary remains.

- Endpoint: `http://localhost:5678/webhook/brightpan-chat` | today=2026-10-18 | questions: 40
- Results file: `results-claude.csv`
- Correct (policy + lookups): 19/25 (76.0%)
- Correct refusals (auto, pending manual review): 0/10 (0.0%)
- Correct escalations: 0/5 (0.0%)
- Request errors: 0/40
- Latency median: 6.38 s | p90 (nearest-rank): 8.31 s
- Manual review: pending

## Run 20261018T072153Z — claude-opus-5-5 (run 2)

- Endpoint: `http://localhost:5678/webhook/brightpan-chat` | today=2026-10-18 | questions: 40
- Results file: `results-claude.csv`
- Correct (policy + lookups): 21/25 (84.0%)
- Correct refusals (auto, pending manual review): 9/10 (90.0%)
- Correct escalations: 5/5 (100.0%)
- Request errors: 0/40
- Latency median: 7.57 s | p90 (nearest-rank): 11.49 s
- Manual review: pending
- Note: this run's per-row CSV was later overwritten by a newer run with the same --out path; only this summary remains.

## Run 20261018T072742Z — gpt-5.5 (run 1)

- Endpoint: `http://localhost:5678/webhook/brightpan-chat-openai` | today=2026-10-18 | questions: 40
- Results file: `results-openai.csv`
- Correct (policy + lookups): 24/25 (96.0%)
- Correct refusals (auto, pending manual review): 9/10 (90.0%)
- Correct escalations: 5/5 (100.0%)
- Request errors: 0/40
- Latency median: 7.28 s | p90 (nearest-rank): 10.33 s
- Manual review: pending
- Note: this run's per-row CSV was later overwritten by a newer run with the same --out path; only this summary remains.

## Run 20261018T084153Z — claude-opus-5-5 (run 3, after review fixes)

- Endpoint: `http://localhost:5678/webhook/brightpan-chat` | today=2026-10-18 | questions: 40
- Results file: `results-claude.csv`
- Correct (policy + lookups): 22/25 (88.0%)
- Correct refusals (auto, pending manual review): 9/10 (90.0%)
- Correct escalations: 5/5 (100.0%)
- Request errors: 0/40
- Latency median: 7.27 s | p90 (nearest-rank): 9.55 s
- Manual review: pending

## Run 20261018T084708Z — gpt-5.5 (run 2, after review fixes)

- Endpoint: `http://localhost:5678/webhook/brightpan-chat-openai` | today=2026-10-18 | questions: 40
- Results file: `results-openai.csv`
- Correct (policy + lookups): 24/25 (96.0%)
- Correct refusals (auto, pending manual review): 9/10 (90.0%)
- Correct escalations: 5/5 (100.0%)
- Request errors: 0/40
- Latency median: 7.74 s | p90 (nearest-rank): 9.34 s
- Manual review: pending
