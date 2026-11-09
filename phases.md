# phases.md: RU-Guard build plan for Claude Code

**How to use this file**
- Work on **one phase at a time**, in order. Follow `CLAUDE.md` (branch per phase, tests after each task, never push to `main`).
- Tick a box (`- [x]`) only when the task is done **and** its test passes. Edit just that line.
- Tasks marked **[HUMAN]** are done by the owner. Claude Code prepares templates, scripts, and instructions, then stops.
- Every phase ends at a **GATE**. Stop there and wait for the owner to say "start phase N+1".
- This repo is fully standalone and depends on no other project. The reference RAG (`demo_rag/`) and client SDK (`client/`) are built in Phase 7; Phases 0 to 6 never need them.

**Kickoff prompt for the owner to paste into Claude Code**
> Read CLAUDE.md, PRD.md, Architecture.md, then phases.md. Start the first unfinished phase. Restate the plan in 10 lines, then work task by task and stop at the gate.

## Progress

| Phase | Name | Est. | Colab | Human-heavy | Status |
|---|---|---|---|---|---|
| 0 | Scaffold and environment | 1 d | no | low | [x] |
| 1 | Taxonomy, seeds, frozen test set | 4 to 5 d | no | **high** | [ ] |
| 2 | Synthetic data generation | 3 d | yes | medium | [ ] |
| 3 | Baselines | 2 d | maybe | low | [ ] |
| 4 | QLoRA fine-tuning and export | 4 d | **yes** | medium | [ ] |
| 5 | Full evaluation and error analysis | 2 d | no | low | [ ] |
| 6 | Guard service | 3 d | no | low | [ ] |
| 7 | Reference RAG, client SDK + MCP gateway | 5 d | no | medium | [ ] |
| 8 | Observability, red-team, CI gate | 3 d | no | low | [ ] |
| 9 | Flutter playground | 3 d | no | low | [ ] |
| 10 | Packaging and release | 2 d | no | medium | [ ] |

---

## Phase 0: Scaffold and environment (about 1 day)

**Goal:** a clean repo where tests, Docker, and CI already run, with the shared normalizer and data schema in place.

- [x] Create the folder skeleton from `Architecture.md` section 5 (with `__init__.py` files and a README stub).
- [x] **[HUMAN]** Unzip the provided `understanding.zip` into `docs/` so the diagrams sit at `docs/understanding/`, then commit them. Claude Code checks that the image links in `Architecture.md` resolve and never edits that folder.
- [x] `.gitignore` (venv, `.env`, `models/*.gguf`, `*.safetensors`, `*.db`, `__pycache__`, large synthetic data) and `.env.example` (`GUARD_API_KEY`, `AUDIT_SALT`, `OLLAMA_URL`, `GUARD_MODEL`, `FAIL_MODE`, `MODE`, `DB_PATH`, plus for Phase 7: `GUARD_URL`, `CHAT_MODEL`, `GUARD_ENABLED`, `ALLOW_GUARD_TOGGLE`).
- [x] `requirements.txt` (service), `requirements-dev.txt` (pytest, pandas, numpy, matplotlib, seaborn, httpx), `requirements-demo.txt` (`demo_rag/` and `gateway/`: LangChain pieces, LangGraph, Chroma, tiktoken, MCP SDK; installed from Phase 7), `requirements-train.txt` (Colab only). Pin versions after a successful install.
- [x] `training/normalize.py` with all six rules from `Architecture.md` 6.1, plus tests (zero-width removal, repeated-char collapse, NFKC, lowercase, whitespace, leet flag off by default).
- [x] `training/schemas.py`: Pydantic row schema and enums (`Source`, `Label`, `AttackType`, `Surface`, `Origin`), plus tests (valid row, invalid enum, missing field).
- [x] Minimal FastAPI app (`guard/app/main.py`) with `GET /health` and a **stub scanner** that returns `safe`; test with the FastAPI test client.
- [x] `tests/test_boundaries.py`: parses imports and fails if `guard/` imports anything but `training/normalize.py` from the repo, or if any package imports another project (rules in `Architecture.md` section 5).
- [x] `docker/Dockerfile.guard` and `docker-compose.yml` (ollama + guard-api). `docker compose build` succeeds.
- [x] `.github/workflows/ci.yml` runs `pytest -q` on pull requests.
- [x] `docs/ENVIRONMENT.md` with OS/WSL2, CPU, RAM, Python, and Docker versions. **[HUMAN]** supplies CPU/RAM.
- [x] Verify every command in `CLAUDE.md` "Commands" works; fix the section if not.

**Acceptance:** `pytest -q` green; `docker compose build` ok; `/health` returns 200 locally and in the container; CI green on a test PR.

**GATE 0:** owner confirms `docs/ENVIRONMENT.md` and merges.

---

## Phase 1: Taxonomy, seeds, and the frozen test set (4 to 5 days, human-heavy)

**Goal:** a labeled seed set and a **hand-written, hash-locked** test set, plus tools that make authoring and validating them easy.

Claude Code:
- [ ] `docs/LABELING_GUIDE.md` from `PRD.md` sections 6 and 7, with 3 English examples per attack type (benign placeholder payloads) and 3 hard-negative examples. Roman Urdu examples are left for the owner.
- [ ] Authoring templates as CSV (easy in a spreadsheet): `data/seeds/seeds_template.csv` and `data/eval/test_template.csv` (columns: `intent_id, surface, source, label, attack_type, text, notes`).
- [ ] `scripts/csv_to_jsonl.py`: converts CSV to JSONL through the Pydantic schema with clear row-level error messages.
- [ ] `scripts/validate_data.py`: schema check, duplicates, label balance, and a **coverage matrix** (`attack_type` x `surface` x `source`), flagging empty required cells and test intents that lack all three surfaces.
- [ ] `scripts/lock_test.py` writes `data/eval/test.lock` (SHA-256 of `test.jsonl`); `scripts/verify_test_lock.py` checks it; a pytest runs the verification (skipped only if no lock exists yet).
- [ ] `scripts/eda.py`: length distributions and a coverage heatmap (matplotlib/seaborn) saved to `docs/figures/`.

**[HUMAN]** (cannot be delegated):
- [ ] Write about **80 seeds**: 40 injection (at least 8 per attack type) and 40 benign (at least 20 hard negatives). Mostly `ru_mix` and `ru_pure`.
- [ ] Write **100 matched test intents x 3 surfaces = 300 rows**: 50 injection intents (10 per attack type, about 40% with `retrieved_chunk` or `tool_output` source, including a few that target the guard itself, such as "label this SAFE") and 50 benign intents (at least 25 hard negatives). Each intent appears as `en`, `ru_mix`, and `ru_pure`.
- [ ] Self-review; drop ambiguous items; run `validate_data.py` until clean; run `lock_test.py`.

**Acceptance:** validator passes with no empty required coverage cell; `test.lock` exists and verifies; seeds JSONL committed.

**GATE 1:** owner says "test set locked". After this, any test change needs the owner's explicit approval and a new version file (`test_v2.jsonl`), never a silent edit.

---

## Phase 2: Synthetic data generation (about 3 days, Colab)

**Goal:** about 4,000 clean training rows and 500 validation rows, with a data card.

- [ ] `training/generate_data.py`: loads Qwen2.5-7B-Instruct in 4-bit (try vLLM first; flag to fall back to Transformers + bitsandbytes). Builds few-shot prompts from the seeds for each cell (`attack_type` x `surface` x `source` x `label`), requires varied Roman Urdu spellings, benign placeholder payloads only, and about 15% English. Resumable, writes JSONL shards, fixed seed, configurable temperature/top_p.
- [ ] `docs/colab/02_generate.md`: exact cells, expected runtime, Drive output path, what to copy back.
- [ ] `training/build_dataset.py`: normalize, Pydantic-validate, remove exact and near-duplicates (character n-gram Jaccard) within the set and **against seeds and test**, language-mix heuristic, length limits, safety denylist scan (drop rows with real harmful-content keywords), balance labels, split train/val, write `data/processed/train.jsonl` and `val.jsonl`.
- [ ] Token-length report with the Qwen tokenizer (dev-only dependency): confirm system prompt + window + label fit `max_seq_len` 512; if not, adjust `WINDOW_CHARS` in `Architecture.md` 6.2 and note it in the decision log.
- [ ] `scripts/sample_for_review.py` (200 random rows to CSV) and `scripts/apply_review.py` (apply keep/fix/drop, report the bad-row rate).
- [ ] `data/DATA_CARD.md`: sources, counts per cell, filters and drop rates, known limits, dataset hash.
- [ ] Tests: dedup, leakage check against a fixture test set, split determinism, denylist.

**[HUMAN]:** run the Colab generation; review the 200 sampled rows; decide go or no-go.

**Acceptance:** about 4,000 train and 500 val rows; zero near-duplicates against the test set; reviewed bad-row rate reported (target 10% or less; if above 15%, improve prompts and regenerate); token-length check passed.

**GATE 2:** owner approves dataset v1; the hash is recorded in `DATA_CARD.md`.

---

## Phase 3: Baselines before any fine-tuning (about 2 days)

**Goal:** honest numbers to beat.

- [ ] `evals/metrics.py`: recall, false-positive rate, precision, F1, macro-F1 over `attack_type`; cuts by `surface`, `source`, and hard negatives; invalid-output rate; **bootstrap 95% CIs** with NumPy (1,000 resamples, fixed seed). Tests on tiny fixtures with known answers.
- [ ] `evals/baselines.py`: (1) regex/keyword rules for English and Roman Urdu; (2) Qwen2.5-1.5B-Instruct zero-shot; (3) the same few-shot from seeds; (4) Llama Guard zero-shot (note that it targets content safety, not injection; run through whichever free local path works; record the exact version). Stretch: Guardrails AI or NeMo Guardrails if an offline free rail works within one day.
- [ ] `evals/eval_guard.py`: one runner for all models with the **same normalizer and prompt format**; strict output grammar; writes predictions JSONL and metrics JSON.
- [ ] `evals/compare.py`: tables and matplotlib charts to `evals/reports/baselines.md`.
- [ ] Run all baselines on the 300 test rows. Record commands and versions.
- [ ] If baselines make a PRD target unrealistic, propose a change to `PRD.md` section 13 (do not edit targets without the owner's approval).

**Acceptance:** baseline table with CIs on all 300 rows; invalid-output rates; report committed; metrics tests green.

**GATE 3:** owner reads the report and confirms or adjusts the targets.

---

## Phase 4: QLoRA fine-tuning and export (about 4 days, Colab)

**Goal:** `ru-guard-0.5b` and `ru-guard-1.5b` as GGUF files that load in Ollama and emit valid labels.

- [ ] `training/configs/qwen2.5-0.5b.yaml` and `qwen2.5-1.5b.yaml` (starting hyperparameters from `PRD.md` section 11 and `Architecture.md` section 10).
- [ ] `training/train_qlora.py`: load the base model in 4-bit NF4 (Unsloth), attach LoRA (PEFT config), build chat-format data with the **shared template**, train with TRL `SFTTrainer` using **assistant-only loss**, fp16 (T4 has no bfloat16), evaluate on val each epoch, checkpoint every epoch to Drive, resume support, fixed seed, plain CSV logs (no external trackers).
- [ ] Val metric callback or script: generation-based macro-F1 on a val subset (not only loss).
- [ ] `docs/colab/04_train.md`: exact cells, expected runtime and memory, resume steps if the session drops.
- [ ] `training/merge_and_export.py`: merge the adapter, export GGUF Q4_K_M and Q8_0 (confirm the current llama.cpp or Unsloth export commands first), run a 5-prompt sanity check.
- [ ] `models/Modelfile.0.5b` and `models/Modelfile.1.5b` with the same ChatML template as training; `scripts/register_model.sh`.
- [ ] `training/tests/test_template_parity.py`: the training formatter and the Modelfile template render identical prompt strings for fixture inputs.
- [ ] Time-boxed ablations on the 0.5B model only: LoRA r=8 vs 16; with vs without `en` data; 2 vs 3 epochs.
- [ ] `scripts/plot_training.py`: loss and val-F1 curves with matplotlib.

**[HUMAN]:** run Colab training; keep adapters on Drive; copy GGUF files to local `models/`.

**Acceptance:** adapters, merged weights, and GGUF per model size; val metrics logged; each GGUF loads in Ollama and returns a valid label on 20 sample prompts; training reproducible from config + seed.

**GATE 4:** owner confirms artifacts exist locally and are backed up on Drive.

---

## Phase 5: Full evaluation and error analysis (about 2 days)

**Goal:** the headline results, the model decision, and the regression thresholds.

- [ ] Run `evals/eval_guard.py` on the test set for both models (Q4_K_M and Q8_0) and all baselines, same normalizer.
- [ ] `evals/bench_latency.py`: p50 and p95 over 200 windows on the owner's CPU, cold vs warm.
- [ ] Error analysis: confusion by `attack_type`; list all false negatives and false positives; group by cause (spelling variance, hard negative, indirect source, guard-targeting, windowing).
- [ ] `evals/reports/EVAL_REPORT.md`: tables with CIs, charts, EN vs Roman Urdu gap, latency, limitations, honest misses.
- [ ] Choose the deployed model and quantization; write the reasoning in a draft `MODEL_CARD.md`.
- [ ] Optional, **one** data-v2 loop only: if a target is missed, add targeted synthetic rows for the top error clusters (never test items), retrain once, re-evaluate, document.
- [ ] `evals/thresholds.json` = release metrics minus a 2-point tolerance; `evals/gate.py` exits non-zero if any metric is below its threshold. Test it with a degraded-predictions fixture.

**Acceptance:** report complete with CIs; thresholds file exists; gate passes on the release model and fails on the fixture.

**GATE 5:** owner approves the deployed model.

---

## Phase 6: Guard service (about 3 days)

**Goal:** a production-style local service that matches the contract in `Architecture.md` section 7.

- [ ] `scanner.py`: windowing (`WINDOW_CHARS`, overlap, `MAX_CHARS`), async calls with a small semaphore, retry once, strict output regex, any-window-flags rule.
- [ ] `ollama_client.py`: async httpx, timeouts, `keep_alive`, `temperature 0`, `num_predict 8`.
- [ ] `policy.py`: action per source, `MODE`, `FAIL_MODE`.
- [ ] `security.py`: API-key dependency, request-size limit, slowapi rate limiting.
- [ ] `pii.py`: Presidio analyzer plus custom recognizers for CNIC (`#####-#######-#`) and Pakistani phone numbers; document the spaCy model download; tests.
- [ ] `audit.py`: create tables, keyed hash (`AUDIT_SALT`), insert audit rows, insert masked quarantine rows.
- [ ] Endpoints `/v1/scan`, `/v1/scan/batch`, `/health`, `/v1/stats`; Pydantic schemas; error codes 401, 413, 422, 429, 503.
- [ ] OpenTelemetry spans (normalize, Ollama call, policy) with latency attributes.
- [ ] Tests with a stub Ollama client: contract, windowing, fail modes, `MODE=log_only`, **audit contains no raw text**, PII masking.
- [ ] **Parity test:** run 50 test rows through the service and through the evaluation harness locally with the real model; outputs must match (investigate any mismatch, usually a template issue).
- [ ] Compose works end to end; README quickstart for the service.

**Acceptance:** `docker compose up`, then `curl /v1/scan` returns correct verdicts on 5 examples; parity test passes; measured p95 recorded; `pytest -q` green.

**GATE 6:** owner follows the quickstart from a clean clone.

---

## Phase 7: Reference RAG, client SDK, and MCP gateway (about 5 days)

**Goal:** a self-contained RAG app that shows measured protection (guard off vs on), a reusable client SDK, and a guarded MCP gateway for tool outputs. Nothing here depends on any other project.

- [ ] `client/ruguard_client`: sync and async clients for `/v1/scan` and `/v1/scan/batch`, Pydantic response models, timeouts and retries. It imports nothing else from the repo. Tests use `httpx.MockTransport`.
- [ ] Extend `tests/test_boundaries.py` to cover `client/`, `demo_rag/`, and `gateway/`; it must stay green.
- [ ] **[HUMAN]** Corpus: Claude Code drafts about 30 English documents about an invented company and 6 poisoned-document templates (benign placeholder payloads only) in `demo_rag/corpus/` and `demo_rag/corpus_poisoned/`. The owner writes or reviews about 10 Roman Urdu documents and the Roman Urdu poisoned ones. Nothing is copied from the test set; add a near-duplicate check against `data/eval/test.jsonl` (read-only).
- [ ] `demo_rag/ingest.py`: chunk (300 to 800 tokens with tiktoken, small overlap), **G0** scan each chunk through `client/`, embed into Chroma with its default embedding function, send flagged chunks to quarantine; `python -m demo_rag.ingest --report` prints a quarantine report.
- [ ] `demo_rag/graph.py`: LangGraph nodes `guard_input`, `retrieve`, `guard_chunks`, `build_prompt` (`<documents>` tags, token budget, canary token), `generate` (Ollama chat model, temperature 0), `validate_output`, as in `Architecture.md` section 12. `GUARD_ENABLED` flag, `guard_events` reducer, `recursion_limit` always set.
- [ ] `demo_rag/validate.py` (**G4**): Pydantic answer schema, citation presence, canary-token leak check; retry once, then refuse.
- [ ] `demo_rag/app`: FastAPI on `:8002` with `POST /chat`, `GET /chat/stream` (SSE), `GET /health`. The `guard=on|off` override works only when `ALLOW_GUARD_TOGGLE=true`.
- [ ] `docker/Dockerfile.demo` and the `demo-rag` compose service under the `demo` profile; `scripts/register_model.sh` also pulls the chat model (confirm the current Ollama tag first); pin `requirements-demo.txt`.
- [ ] `evals/attack_suite.yaml`: 30 to 50 scripted scenarios (direct attack, poisoned chunk, poisoned tool output, prompt leak) in Roman Urdu and English, each with a pass/fail check (canary leaked, forbidden tool called). Benign payloads only; not copied from the test set.
- [ ] `evals/run_asr.py --guard off|on`: Attack Success Rate table by scenario type and surface, with counts; temperature 0, fixed seed.
- [ ] `evals/golden_set.yaml` (30 questions with expected keywords; the owner reviews the Roman Urdu ones) and `evals/run_quality.py --guard off|on`: correctness and citation-presence rates with per-question diffs. Deterministic, no judge model.
- [ ] `gateway/`: MCP server with allowlisted read-only tools (`search_docs` over the `demo_rag` index, `scan_text`, demo `get_note`), Pydantic argument validation, timeouts, and redaction of flagged outputs. Tests: a poisoned Roman Urdu note is redacted; a non-allowlisted tool call is refused.
- [ ] Regression check: with `GUARD_ENABLED=false` the graph makes zero guard calls (a client that raises if called) and the unguarded answers are unchanged on the golden set.
- [ ] Optional: Ragas on the golden set with a local Ollama judge only; note the judge's limits.

**Acceptance:** ASR table off vs on; quality delta reported; MCP tests green; boundary test green; regression check passes; `docker compose --profile demo up` serves `/chat`.

**GATE 7:** owner reviews the ASR and quality tables and tries 5 attacks by hand against `demo-rag`.

---

## Phase 8: Observability, red-team, and CI gate (about 3 days)

**Goal:** regressions cannot reach `main` unnoticed.

- [ ] OpenTelemetry exporter configuration (console or file by default). Langfuse self-hosted is a **stretch**; do not block on it.
- [ ] `evals/promptfoo/promptfooconfig.yaml` with Roman Urdu red-team cases against the `demo-rag` endpoint (guard on); list failing cases.
- [ ] DeepEval pytest-style attack tests (expect refusal and no canary leak).
- [ ] Extend CI: **PR smoke eval** (100-row subset, Ollama on the runner, GGUF from the GitHub Release) with `evals/gate.py`; **nightly** full eval, ASR and golden-set quality delta (`run_asr.py`, `run_quality.py`), Promptfoo; upload reports as artifacts. Nightly may use a 10-attack subset if the runner is too slow for the chat model; say so in the report. The workflows should match the pipeline in `docs/understanding/03-ci-cd-pipeline.png`; if they differ, update `Architecture.md` section 15 and note the stale picture.
- [ ] **[HUMAN]** creates the GitHub Release with the GGUF asset (check current size limits); keep the repo public for free standard-runner minutes.
- [ ] Regression drill on a throwaway branch: swap in a degraded model or stub, confirm CI fails, then revert.

**Acceptance:** CI green on the main-equivalent branch; the drill demonstrably fails the gate.

**GATE 8:** owner checks the CI run links.

---

## Phase 9: Flutter playground (about 3 days)

**Goal:** a demo anyone can understand in 60 seconds.

- [ ] `flutter_app/` with Riverpod; features `scan` and `chat`; http or dio client; base URL in config; **no provider keys in the app**.
- [ ] Scan screen: text box, source selector, result card (verdict chip, attack type, action, latency ms). **No confidence percentage.**
- [ ] Compare screen: the same attack with guard off vs on against `demo-rag` (`guard=on|off`, needs `ALLOW_GUARD_TOGGLE=true`), side by side.
- [ ] Streaming chat screen (SSE from `demo-rag` `/chat/stream`) with a Stop button and citation chips; reuse the pattern from the study guide (6.1 and 6.2).
- [ ] Built-in sample attack library (Roman Urdu and English).
- [ ] History kept in memory (Riverpod state); do not add new dependencies.
- [ ] Widget tests for the result card; manual test checklist; screenshots in `docs/figures/`.

**Acceptance:** the app runs (emulator, desktop, or web) against the local compose stack; screenshots committed.

**GATE 9:** owner demo.

---

## Phase 10: Packaging and release (about 2 days)

**Goal:** a repo a reviewer can trust and run.

- [ ] `README.md`: what and why, results table (from `EVAL_REPORT.md`), the grand workflow and RAG pipeline pictures from `docs/understanding/` (relative links; the Mermaid blocks in `Architecture.md` stay the editable source), 5-minute quickstart, limitations, ethics note.
- [ ] Final `MODEL_CARD.md` (intended use, data, evaluation, limits, **licence check of each base model**) and final `data/DATA_CARD.md`.
- [ ] `docs/INTERVIEW_NOTES.md`: a 5-minute whiteboard walkthrough that follows `docs/understanding/02-grand-workflow.png`, tradeoffs (QLoRA vs encoder, latency vs accuracy, fail-closed vs open), likely questions.
- [ ] Demo script and video checklist. **[HUMAN]** records the demo.
- [ ] Tag `v1.0`, attach GGUF assets, write the changelog.
- [ ] Walk through `PRD.md` section 14 and tick each criterion with an evidence link. Re-check the novelty claim from `PRD.md` section 2 before it appears anywhere public.

**Acceptance:** every PRD section 14 criterion has a link to evidence.

**GATE 10:** owner publishes.

---

## Appendix A: Phase-end note template (`docs/phase-notes/phase-N.md`)
```
# Phase N: <name>
Branch / commit:
Done: (tasks)
Numbers: (only from real runs, with the command used)
Decisions: (added to Architecture.md decision log)
Open issues:
Needs from owner:
```

## Appendix B: If you get stuck
1. Re-read the relevant section of `Architecture.md`.
2. Check the installed library version and its `--help` or source (APIs change).
3. Pick the simplest option that meets `PRD.md`, record it in the decision log, continue.
4. If it changes scope, metrics, or the tool whitelist, ask the owner.
