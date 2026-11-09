# CLAUDE.md: RU-Guard (Roman Urdu Prompt-Injection Guard)

Read in this order: `PRD.md` (what and why), `Architecture.md` (how), `phases.md` (what to do now). Do not skim `phases.md`: it is your work queue. For pictures of the system, see `docs/understanding/README.md`.

## What this project is
A small Qwen2.5 model fine-tuned with **QLoRA** to detect prompt injection in Roman Urdu, English, and mixed text. It runs as a local FastAPI service (`guard-api`) backed by Ollama, and can protect any RAG app, agent, or MCP gateway. This repo is **fully standalone**: it ships its own reference RAG app (`demo_rag/`), client SDK (`client/`), attack suite, and golden set, and depends on no other project. Everything must be **free**.

## How to work: phase by phase
1. Open `phases.md`. Find the **first phase that has unchecked tasks**. Work **only** on that phase.
2. Create or switch to a branch named `phase-<N>-<slug>`. Commit there. **Never push to `main`.** The owner merges.
3. Start by restating the phase goal and your plan in 10 lines or fewer. Ask a question only if you are truly blocked; otherwise choose the simplest option and record the decision in the decision log of `Architecture.md`.
4. Do tasks in order. After each task: run `pytest -q`, then tick the checkbox in `phases.md` with a **targeted edit**.
5. At the end of the phase: run the acceptance checks, write a short note to `docs/phase-notes/phase-<N>.md` (what was done, numbers, open issues), then **STOP at the gate**. Do not begin the next phase until the owner says "start phase N+1".
6. **Human gates:** you cannot run Colab, write the test set, or review data. When a step needs the owner, write exact copy-paste instructions to `docs/colab/<step>.md` (or the relevant doc), list the files to bring back, and stop.

## Hard rules
- **Free and whitelisted only.** Use only tools listed in `PRD.md` section 12. Do not add any dependency, service, or API that is not listed without asking first. No paid APIs, ever, in code, tests, or CI.
- **No attribution.** Never add Claude as co-author, collaborator, or "generated with" attribution anywhere: commits, PR descriptions, docs, README, model card, code comments. This is a standing rule for all work.
- **Targeted edits.** Prefer small edits to existing files over rewriting whole files. Do not reformat code you were not asked to change.
- **The test set is sacred.** `data/eval/test.jsonl` is hand-written by the owner and frozen by `data/eval/test.lock`. Never edit, regenerate, augment, train on, or tune prompts against it. Never write anything into `data/eval/`. If `scripts/verify_test_lock.py` fails, stop and tell the owner.
- **Never draft test-set content.** Test items are written or rewritten by the owner.
- **Benign payloads only.** Attack examples in datasets use harmless placeholders (reveal the system prompt, say a secret word, call a harmless tool). Never write real instructions for weapons, malware, self-harm, or other harmful content.
- **Privacy.** No raw user text in logs or `audit_log`. Store only a keyed hash and length. Quarantined text is Presidio-masked.
- **Secrets.** Config from environment variables. Never commit `.env`, keys, model files (`.gguf`, `.safetensors`), or large data. Keep `.gitignore` correct.
- **No invented numbers.** Every metric must come from a real run with a recorded command and commit. If it was not run, write "not run".
- **Ask before destructive actions** (`rm -rf`, `git reset --hard`, force-push, deleting data or branches).
- **Standalone boundary.** Do not depend on, import from, or modify any other project or repo. `guard/` never imports `demo_rag/` or `gateway/`; `demo_rag/`, `gateway/`, and `evals/` reach the guard only over HTTP through `client/`. `tests/test_boundaries.py` enforces this.
- **Diagrams.** `docs/understanding/` is provided by the owner. Do not edit, regenerate, or delete it. If an architecture change makes a picture stale, update the Mermaid blocks in `Architecture.md` and list the stale pictures in the phase note.
- **Library APIs change** (Unsloth, TRL, llama.cpp, Ollama, Presidio, MCP SDK). Before using one, check the installed version, `--help`, or the package source. Do not guess from memory. Pin versions you tested.

## Quick reference
| Item | Value |
|---|---|
| Labels | `SAFE` or `INJECTION|<attack_type>` |
| attack_type | `override`, `persona`, `prompt_leak`, `exfiltration`, `tool_abuse` |
| source | `user_input`, `retrieved_chunk`, `tool_output` |
| surface | `en`, `ru_mix`, `ru_pure` |
| Models | `ru-guard-0.5b`, `ru-guard-1.5b` (QLoRA on Qwen2.5-0.5B/1.5B-Instruct) |
| Data generator | Qwen2.5-7B-Instruct, 4-bit, on free Colab |
| guard-api | `:8001`, header `X-API-Key` (env `GUARD_API_KEY`) |
| Ollama | `:11434` (serves `ru-guard-*` and the demo chat model) |
| Reference RAG | `demo_rag/`, FastAPI `demo-rag` on `:8002`, chat model `qwen2.5:1.5b-instruct` via Ollama, flag `GUARD_ENABLED` |
| Client SDK | `client/ruguard_client` (sync + async HTTP wrapper over `/v1/scan`) |
| Policy | `FAIL_MODE=closed` default; `MODE=enforce|log_only` |
| Normalizer | `training/normalize.py` (single source of truth, imported by `guard/`) |
| Test lock | `data/eval/test.lock` |
| Thresholds | `evals/thresholds.json` |

## Commands (keep this section accurate; update it when you change tooling)
```bash
# Setup (WSL2 Ubuntu, Python 3.12)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
# Setup (Windows host, Git Bash; see docs/ENVIRONMENT.md)
py -3.12 -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt -r requirements-dev.txt

# Tests (run after every task)
pytest -q

# Run the service locally
uvicorn guard.app.main:app --port 8001 --reload

# Docker (Ollama + guard-api)
docker compose up --build
bash scripts/register_model.sh ru-guard-0.5b   # Phase 4 onward

# Reference RAG (Phase 7 onward; adds the demo-rag service)
docker compose --profile demo up --build
python evals/run_asr.py --guard off && python evals/run_asr.py --guard on
python evals/run_quality.py --guard off && python evals/run_quality.py --guard on

# Data and evaluation
python scripts/validate_data.py data/seeds/seeds.jsonl   # Phase 1 onward
python scripts/verify_test_lock.py                       # Phase 1 onward
python evals/eval_guard.py --model ru-guard-0.5b --split test   # Phase 3 onward
python evals/gate.py                                     # Phase 5 onward
```
Training and generation scripts run on Colab, not here. Local runs are limited to tiny smoke tests.

## Code conventions
- Python 3.12, type hints on all function signatures, small functions, one-line docstrings.
- Pydantic models for every external input and output (API bodies, JSONL rows, model output).
- Config via environment variables and yaml files. No hard-coded paths, keys, or URLs.
- `logging` module only in services (no `print`). Do not swallow exceptions silently.
- Tests live next to the code (`guard/tests`, `training/tests`, `evals/tests`, `client/tests`, `demo_rag/tests`, `gateway/tests`). Use fixtures with tiny data and a **stub scanner** so unit tests never need a model.
- Deterministic by default: fixed seeds, versions pinned, outputs reproducible from a config file.
- Scripts over notebooks: notebooks only install, clone, mount Drive, and call a script.

## Definition of done (per task)
Code written, test added or updated and passing, docs updated if behaviour or contracts changed, checkbox ticked in `phases.md`, and nothing outside the phase scope touched.

## Colab hand-off format
When a step needs Colab, create `docs/colab/<step>.md` containing: the goal, the exact cells to paste in order, expected runtime and output, where files are saved on Drive, what to copy back and to which local path, and what to do if the session disconnects (resume instructions). Then stop and wait.

## When something is unclear
Prefer the simplest design that satisfies `PRD.md`. Write the choice in the decision log (`Architecture.md` section 18) and continue. If it changes scope, metrics, or the whitelist, ask the owner first.
