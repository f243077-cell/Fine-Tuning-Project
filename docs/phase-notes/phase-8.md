# Phase 8: Observability, red-team, and CI gate

Branch / commit: `main`. Status: **done; Gate 8 closed with the Release published (see `phase-10.md` for the smoke-gate follow-up: margin 10 points, D57, D58).**

## Done
- **CI was broken since Phase 6** (every push failed at "Install"): `requirements-dev.txt` pinned `numpy==2.5.4`, but `presidio-analyzer` needs numpy below 2.5. The fix pins `numpy==2.4.6` (the version installed locally). CI also installs `requirements-demo.txt`, because the demo and gateway tests import it (D55).
- **OpenTelemetry export:** `OTEL_EXPORTER=file` (default) writes JSON-line spans to `OTEL_FILE` (`traces.jsonl` next to the audit DB); `console` and `none` are the other options. A test checks that spans carry latency and no raw text. Langfuse (stretch goal) is not done.
- **`.github/workflows/ci.yml`** (every PR and every push to main): fast checks (test lock and `pytest`, no model), then a smoke eval (100 test rows, `--subset smoke`) and `gate.py` against `evals/thresholds_smoke.json`. The GGUF comes from Release `model-v1` (SHA-256 checked, cached), with Ollama 0.32.15 on the runner. Until the Release exists, the smoke job warns and skips the model steps.
- **`.github/workflows/nightly.yml`** (02:17 UTC daily and on demand): full 300-row eval and gate, guard-api and demo-rag on the runner, ASR off/on (optional `asr_sample`), golden-set quality off/on, Promptfoo, DeepEval, and all reports uploaded as artifacts. Per-run random API key and salt. It needs the Release.
- **Smoke subset:** one row per intent with the surface rotating (100 rows: 34 en, 33 ru_mix, 33 ru_pure; 50 attacks and 50 benign). Plain every-3rd-row sampling would have picked only `en` rows. The release model on this subset (from its saved predictions, no new calls) scores recall 0.92, FPR 0.12, F1 0.902; thresholds are 2 points below that.
- **Promptfoo** (`evals/promptfoo/promptfooconfig.yaml`, 18 new Roman Urdu attacks and 4 benign controls) and **DeepEval** (`evals/redteam/`, deterministic metrics, no judge) were run against the guarded demo-rag. Results are in `evals/reports/promptfoo/REDTEAM.md`.
- `docs/release_gguf.md`: step-by-step instructions for the owner to publish the Release.

## Numbers (real runs, 2026-11-15)
- CI on `main` (`7c5f02f`, run 43739417362): fast checks passed; the smoke job passed with its model steps skipped (no Release yet).
- Promptfoo: 20 of 22 passed. All 18 attacks were defended; G1 blocked 15. Three passed the guard but the chat model did not comply: spaced letters, leetspeak, and emotional pressure. Two benign controls failed on answer quality (wrong retrieval or answer), not on guard blocks.
- DeepEval: 11 of 11 passed (8 attacks refused with no leak, 3 benign questions answered).
- Tests: 299 passed, 11 skipped (the live DeepEval tests without `DEMO_URL`).

## Regression drill
- Branch `drill/degraded-scanner` (commit `b65d36a`, not merged): `ModelScanner.scan` returns SAFE for every text. CI run 43739733966 **failed**: the "Tests" step of the fast checks failed, and the smoke job did not start. `main` stayed green (run 43739417362).
- The gate half of the drill (the smoke gate failing on a degraded model) needs the Release; it is still open.

## Open issues
- **[HUMAN]** Publish the GitHub Release `model-v1` with the GGUF (`docs/release_gguf.md`). Until then the PR smoke gate cannot run, and the nightly workflow fails at "Fetch GGUF".
- After the Release: run the drill branch again so that the smoke **gate** (not only the unit tests) fails on the degraded scanner, and check one nightly run. The nightly runtime on a CPU runner is not measured yet.
- Guard misses found by the red team: spaced-out letters and leetspeak (`leet_fold` is off by default) and soft-worded social-engineering requests for the reference code.
- The diagram `docs/understanding/03-ci-cd-pipeline.png` matches the workflows (fast checks, fetch GGUF, smoke eval 100 rows, merge gate; nightly full eval, attack suites, reports). Not stale.
