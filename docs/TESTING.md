# Testing: unit, integration, performance

Run on 2026-11-16 on the owner's laptop (Intel i7-7500U, 4 threads, no GPU), Windows 10, Docker Desktop. Stack: guard-api and demo-rag in Docker, Ollama 0.32.15 on the host (`docker-compose.host-ollama.yml`), deployed model `ru-guard-1.5b-v2` (Q4_K_M), chat model `qwen2.5:1.5b-instruct`. Code at commit `04c212c` plus the files added with this report.

| Suite | Where | Tests | Result | Needs |
|---|---|---|---|---|
| Unit | next to the code (`guard/tests`, `training/tests`, `client/tests`, `demo_rag/tests`, `gateway/tests`, `evals/tests`, `scripts`, `tests/`) | 301 (+13 skipped live tests) | **301 passed** | nothing (stub scanner, no model) |
| Integration | `tests/integration/test_integration.py` | 40 | **40 passed** (120 s) | running stack |
| Performance | `tests/performance/test_performance.py` | 37 | **37 passed** (276 s) | running stack |

The live suites skip themselves when guard-api is not reachable, so `pytest -q` and CI stay as before.

## All-Docker run from a fresh clone (README quickstart)

2026-11-16, `git clone` of `main` at `04c212c` into an empty folder, model downloaded from Release `model-v1` (SHA-256 matched), `.env` from `.env.example` with two new secrets, `docker compose up --build -d` (Ollama in the `ollama/ollama:0.32.15` container), `REGISTER_TARGET=docker SKIP_CHAT_MODEL=1 bash scripts/register_model.sh ru-guard-1.5b-v2`, then the two README scans:

- The first register call failed on a Windows path bug in `scripts/register_model.sh` (fixed, see CHANGELOG). Before the model was registered, both scans returned `verdict: error`, `action: block`, `scanner_error: unavailable`: fail-closed worked.
- After the fix: `/health` ok; the Roman Urdu attack `injection`, `prompt_leak`, `block` (6.9 s, the cold first call); `Mera order kab deliver hoga?` `safe`, `allow` (0.68 s).
- Integration suite against this stack (demo-rag not started): 36 passed, 3 skipped (demo-rag), **1 failed**: the safe Roman Urdu probe (`RU_SAFE`) was labelled injection once. Sent again three times by itself it was `safe` each time; this is the run-to-run label jitter of [smoke_gate_check.md](../evals/reports/smoke_gate_check.md), most likely from requests running in parallel. The test was not changed.

## How to run

```bash
pytest -q                                              # unit (about 35 s)

# live stack: Ollama with the model registered, then
RATE_LIMIT=1000/minute ALLOW_GUARD_TOGGLE=true \
  docker compose -f docker-compose.yml -f docker-compose.host-ollama.yml --profile demo up -d guard-api demo-rag
pytest -q tests/integration                            # GUARD_API_KEY from the environment or .env
PERF_OUT=evals/reports/perf/perf.json pytest -q tests/performance
```

`RATE_LIMIT=1000/minute` is needed for the performance bursts (the default is 120/minute per client). URLs default to `http://127.0.0.1:8001` and `:8002` (`GUARD_URL`, `DEMO_URL`).

## Integration (40)

guard-api contract (13): health and model name, 401 without or with a wrong key, 422 for four bad bodies, 413 for a text over 12,000 characters and for 33 batch items, request id echoed or generated, response fields with no text echoed back. Verdicts on the real model (11): injection blocked in English, Roman Urdu and mixed text; safe text allowed in all three; poisoned retrieved chunk dropped; poisoned tool output redacted; long text split into windows; an injection hidden after 3,000 characters of safe text still found; batch keeps order, ids and per-source actions. Audit log (4): `/v1/stats` needs the key, counts grow by one per scan, by source, and a flagged chunk lands in quarantine. Client SDK (6): flags and allows, health and stats, wrong key raises `GuardAuthError`, an unreachable service fails closed (`block`, `unavailable`), async client. MCP gateway with the live guard (4): clean note passes, poisoned note redacted, unknown tool refused, `scan_text` tool. demo-rag (3): health, injected question blocked with the guard on, clean question answered.

The probe texts are new ones written for this suite (`tests/live.py`), not taken from the test set.

## Performance (37), measured values

Saved in [evals/reports/perf/perf_host-ollama_2026-11-16.json](../evals/reports/perf/perf_host-ollama_2026-11-16.json). Budgets are regression budgets (about 1.8x the service baseline of EVAL_REPORT section 5), not the PRD targets.

| Measure | Value | Budget |
|---|---|---|
| `/health` p95 | 0.059 s | 0.3 s |
| 401 / 422 / 413 rejection | 0.033 / 0.013 / 0.005 s | 0.1 / 0.1 / 0.2 s |
| 2 MB body rejected | 0.026 s | 1 s |
| Warm single window, median per surface (6 cases) | 0.49 to 1.03 s (safe texts about 0.5 s, injections about 0.8 to 1.0 s: the label is longer) | 1.7 s |
| Warm, 20 mixed calls | p50 1.29 s, p95 1.67 s | p95 2.5 s |
| Server-side `latency_ms` p95 | 1,598 ms | 2,500 ms |
| 12,000-character text (13 windows) | 10.2 s | 30 s |
| Batch of 4 / 8 / 16 / 32 chunks | 1.36 / 1.21 / 1.33 / 1.28 s per item | 2.5 s per item |
| Parallel clients 2 / 4 / 8 (each sends 2) | 0.59 / 0.77 / 0.78 scans per second, worst call 7.5 s, no errors | no errors, under 30 s |
| Drift over 30 sequential scans | p95 first 10: 1.03 s, last 10: 0.70 s | last at most 1.5x first + 0.5 s |
| SDK overhead over raw HTTP | 0.041 s (median) | 0.1 s |
| Fail-closed answer with the service down | 4.5 s (connect retries) | 6 s |
| guard-api container memory | 164 MiB | 1,500 MiB |

**Read with care.** The multi-window texts repeat one paragraph and the async throughput test sends one text eight times, so Ollama's prompt cache makes those faster than real traffic (0.36 to 0.52 s per window there, against about 1 s for fresh text). The 20-call p95 of 1.67 s per window is above the PRD NFR-3 target for the 1.5B model (1.0 s), which was already reported as missed. Throughput levels off near 0.8 scans per second because Ollama runs one model on 4 CPU threads (`CONCURRENCY=2`).

## Problems found while writing the suites (fixed in the tests, not in the service)

- `localhost` on Windows tries IPv6 first and added about 2 s to new connections (the same cause as D51); the suites use `127.0.0.1`.
- `httpx.get` builds a new client and SSL context for each call, about 0.5 s on this CPU; the health test first measured that instead of the server. It now uses one client.
- Single-sample latency checks failed on CPU noise (one 4.8 s outlier); window tests use the median of 3, and the SDK-overhead test interleaves raw and SDK calls.
