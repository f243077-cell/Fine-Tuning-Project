# Phase 6: Guard service

Branch / commit: `main`. Status: **done; Gate 6 passed (owner-delegated, 2026-11-15: "start phase 7"). The clean-clone quickstart was not run; the full `ollama` container path is still untested on this machine.**

## Done
- `guard/scanner.py`: normalize, overlapping windows (`WINDOW_CHARS` 1000, `OVERLAP_CHARS` 200), parallel window calls bounded by a semaphore (`SCAN_CONCURRENCY` 2), one retry per window on any error, strict output regex, any-window-flags rule (D50).
- `guard/ollama_client.py`: async httpx, timeouts, `keep_alive`, the evaluation harness's decoding options (`temperature 0`, `top_k 1`, `num_predict 8`, `num_ctx 1024`, `seed 0`).
- `guard/policy.py`: action per source, `MODE=enforce|log_only`, `FAIL_MODE=closed|open`.
- `guard/security.py`: `X-API-Key` dependency (constant-time compare), body-size limit, slowapi rate limit per key.
- `guard/pii.py`: Presidio with spaCy `en_core_web_sm` (pinned as a wheel URL in `requirements.txt`), plus recognizers for CNIC and Pakistani mobile and landline numbers.
- `guard/audit.py`: `audit_log` (HMAC-SHA256 with `AUDIT_SALT`, length, verdict, action, model, latency) and `quarantine` (PII-masked flagged chunks).
- Endpoints `/v1/scan`, `/v1/scan/batch`, `/health`, `/v1/stats`; error codes 401, 413, 422, 429, 503. A 503 still carries the fail-mode action in the body (D50).
- OpenTelemetry spans `scan`, `normalize`, `ollama.call`, `policy` with latency attributes and no text (`OTEL_CONSOLE=true` prints them).
- Tests with a fake Ollama client: contract, windowing, retry, concurrency, fail modes, `log_only`, audit has no raw text, PII masking, spans. `tests/test_prompt_parity.py` checks that the served prompt, grammar, options and windowing match training and the harness.
- `evals/parity.py`, `evals/bench_latency.py --guard-url`, `docker-compose.host-ollama.yml`, `REGISTER_TARGET=docker` in `scripts/register_model.sh`, README quickstart.

## Numbers (real runs, owner's CPU, Ollama 0.32.15, model ru-guard-1.5b-v2 Q4_K_M)
- Parity: 50 of 50 test rows give the same label through guard-api and through the harness (`python evals/parity.py --model ru-guard-1.5b-v2`, report `evals/reports/parity/ru-guard-1.5b-v2.json`). Labels: 24 SAFE, 26 INJECTION (all five attack types).
- Latency through guard-api, 200 val windows: warm p50 0.91 s, p95 1.36 s (`evals/reports/latency/ru-guard-1.5b-v2-service.json`). Direct Ollama: warm p50 0.88 s, p95 1.41 s; cold p50 3.95 s. PRD NFR-3 (1.5B p95 at most 1.0 s) is missed.
- Docker: guard-api image builds (732 MB) and turns healthy against host Ollama. `curl /v1/scan` gives correct verdicts on 5 examples (2 Roman Urdu or English user-input attacks blocked, 1 retrieved-chunk exfiltration dropped, 2 benign texts allowed). 401, 413 and 422 confirmed with curl. Batch, stats, audit rows (hash and length only) and masked quarantine rows were checked in the container DB.
- Tests: 230 passed.

## Latency correction (D51)
The Phase 5 latencies (about 3.3 s warm) were mostly HTTP client overhead. The harness opened a new connection per call, and on this Windows machine `localhost` tries `::1` first while Ollama listens on IPv4 only (about 2.4 s), plus about 0.3 s to build the client. The harness now keeps one pooled client. All six fine-tuned models were re-measured, and EVAL_REPORT section 5, MODEL_CARD and the phase-5 note were corrected; D51 records the correction to D49. The 0.5B is about 1.7 times faster than the 1.5B (warm p50 0.52 s against 0.88 s). The deployed model is unchanged (Roman Urdu recall).

## Open issues
- **Ollama container not run here.** `docker compose up` stalled for about 50 minutes pulling `ollama/ollama:0.32.15` (about 1.5 GB; the link here measured about 320 KB/s). guard-api was verified in Docker against host Ollama instead. Gate 6 (clean-clone quickstart) covers the full path, including `REGISTER_TARGET=docker`.
- **PII over-masking.** spaCy's English NER tags some Roman Urdu words as PERSON (for example "bhool jao"), so quarantined text can lose words. This errs on the side of privacy. A Roman Urdu name model is out of scope.
- The parity file's `service_latency_ms_after_harness` numbers benefit from Ollama's prompt cache (same prompt just sent by the harness), so they are not a latency measurement.
- `evals/parity.py` uses httpx directly until `client/` exists (Phase 7).
- Diagrams: the API contract adds `allow` and `scanner_error`. No picture in `docs/understanding/` shows these fields, so none is stale.
