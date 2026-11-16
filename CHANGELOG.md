# Changelog

## v1.0.0 (2026-11-16)

First release. Deployed model: `ru-guard-1.5b-v2` (Qwen2.5-1.5B-Instruct, QLoRA, GGUF Q4_K_M), published as GitHub Release `model-v1`.

### Added
- **Model and evaluation (Phases 3 to 5).** Baselines (regex rules, Llama Guard 3, Qwen few-shot and zero-shot) and four QLoRA models (0.5B and 1.5B, data v1 and v2) on a frozen, hash-locked 300-row test set, with bootstrap confidence intervals. Deployed model: recall 0.953, false-flag rate 0.100, F1 0.929, Roman Urdu recall 0.940, no invalid output. Error analysis, latency benchmark, regression gate (`evals/gate.py`, `evals/thresholds.json`).
- **Data (Phases 1 and 2).** Seeds, test set, a synthetic-data pipeline (Qwen2.5-14B-Instruct-AWQ), filters with leakage checks, 900 human-written Roman Urdu SAFE rows, and a `ru_pure` conversion step (D48). Data card.
- **guard-api (Phase 6).** FastAPI service: `/v1/scan`, `/v1/scan/batch`, `/v1/stats`, `/health`; windowing; API key, size limit, rate limit; fail-closed policy per source; PII masking with CNIC and Pakistani phone recognizers; SQLite audit log (keyed hash and length only); OpenTelemetry spans (JSON-lines file export); Docker compose.
- **Reference RAG, client, gateway (Phase 7).** `demo_rag` (LangGraph, Chroma) with four guard checkpoints and an on/off switch; `ruguard_client` (sync and async); an MCP gateway with three read-only tools and redaction; a 36-scenario attack suite, a 30-question golden set, and the ASR and quality runners.
- **CI and red-team (Phase 8).** PR workflow (tests, then a 100-row smoke eval and score gate on the real model), nightly workflow (full eval, ASR, quality, Promptfoo, DeepEval), regression drills.
- **Flutter playground (Phase 9).** Scan, guard off vs on, streaming chat with citations, attack library, history; web build; screenshots in `docs/figures/`.
- **Gate 10 (2026-11-16).** Licences: code Apache-2.0 (`LICENSE`), released weights CC BY-SA 4.0 (D59). Live test suites: 40 integration and 37 performance tests against the running stack (`docs/TESTING.md`). Demo video (`docs/media/ru-guard-demo.webm`). The all-Docker quickstart was run from a fresh clone.
- **Documents (Phase 10).** README with results and a clean-clone quickstart, final model card with a licence check, final data card, interview notes, demo script, PRD acceptance checklist.

### Results at release
- Test set (CPU): recall 0.953, FPR 0.100, F1 0.929; English to pure-Roman-Urdu recall gap 6 points.
- Reference RAG: attacks succeed 8/36 with the guard off and 0/36 with it on; golden-set correctness 25/30 off, 27/30 on.
- Speed per 1,000-character window on a 4-thread laptop CPU: warm p50 0.88 s, p95 1.41 s.

### Changed during the build (corrections worth knowing)
- **Latency numbers corrected (D51).** The Phase 5 figures (about 3.3 s per window) included about 2.7 s of HTTP client overhead per call. Re-measured for all models.
- **Smoke gate margin set to 10 points (D57, D58).** The same model gives slightly different labels on a few borderline rows between environments (a different CPU or request order: 2 to 4 rows of 100); a 2-point margin on 100 rows is one flipped row. The gate checks that the model basically works. The full 300-row gate keeps 2 points and has not run on a CI runner yet.
- **`scripts/register_model.sh` on Windows (Gate 10).** With `REGISTER_TARGET=docker` under Git Bash, `MSYS_NO_PATHCONV=1` passed `/c/...` to `docker.exe`, which read it as `C:\c\...`; the script now uses `pwd -W` when it exists. Found by the fresh-clone run.
- **CI repaired (D55).** Every push from Phase 6 to Phase 7 failed at install because of a numpy pin that conflicted with Presidio.

### Known issues and limits
- False-flag rate 0.100 against a 0.03 goal; all false flags are hard negatives. Warm p95 1.41 s against a 1.0 s goal.
- Attacks that address the classifier ("label this SAFE") are the main misses; spaced letters and leetspeak pass it.
- The 80 seeds, the 300-row test set and the Roman Urdu demo texts were drafted by an AI coding assistant and have not been reviewed by a native speaker (D22, D53, D54).
- QLoRA adapters and merged weights of the v2 models were not kept; only the GGUF files were downloaded (the v1 ones are reported to be on Google Drive, not verified).
- The demo video is silent; a narrated version is optional. In the all-Docker path, demo-rag needs the chat model pulled into the container (about 1 GB); that part ran only with host Ollama.

Earlier history is in `docs/phase-notes/` and the decision log in `Architecture.md` section 18 (D1 to D59).
