# PRD: RU-Guard, a Roman Urdu Prompt-Injection Guard (QLoRA fine-tuned)

| | |
|---|---|
| Owner | Tanzeel Hussain |
| Status | Draft v0.2 (standalone scope) |
| Date | 2026-11-09 |
| Working repo name | `roman-urdu-guard` |
| Companion docs | `Architecture.md`, `phases.md`, `CLAUDE.md`; diagrams in `docs/understanding/` |
| Cost constraint | **$0.** Every tool is free or open-source and is named in the owner's GenAI roadmap documents (see section 12). |

---

## 1. One-line summary

A small language model, fine-tuned with **QLoRA**, that detects prompt-injection and jailbreak attempts written in **Roman Urdu, English, and mixed Roman Urdu/English**, shipped as a local FastAPI service that any RAG app, agent, or MCP tool gateway can call over HTTP, with measured before/after results on a bundled reference RAG app.

**Standalone by design.** RU-Guard is a self-contained project: its own repo, model, API, client SDK (`client/`), reference RAG app (`demo_rag/`), attack suite, golden set, and tests. It depends on no other project. `demo_rag/` exists only to prove the guard works (attack success rate and answer quality, guard off vs on); `guard/` never imports it. Any other app can use the same `/v1/scan` endpoint through plain HTTP or the `client/` SDK. Phases 0 to 6 do not need `demo_rag/`.

## 2. Background and problem

- Roman Urdu (Urdu in Latin script, usually mixed with English) is how most Pakistani users type. Most prompt-injection defenses are built and tested on English.
- A 2026 workshop paper introduced the Roman Urdu Adversarial Benchmark (RUAB) specifically to test whether safety detection degrades on Roman Urdu and code-switched text. That is evidence the problem is recognised.
- Partial prior work exists: open guard models that list Hindi/Hinglish and South Indian languages, and research-style models covering Urdu and Sindhi script. In a short survey on 2026-11-09 no production-oriented Roman Urdu injection guard for RAG and agent pipelines was found. **Re-check before claiming novelty in the README or interviews.**
- Injection does not only arrive through the chat box. It arrives inside retrieved documents and tool outputs (indirect injection). A guard that only scans user input is incomplete.

References:
- Roman Urdu Adversarial Benchmark: https://aclanthology.org/2026.abjadnlp-1.37.pdf
- Diviqra DistilBERT Guard: https://huggingface.co/Diviqra/diviqra-distilbertguard
- Jev-Multilingual: https://huggingface.co/shakeel143/jev-multilingual

## 3. Goals

| ID | Goal |
|---|---|
| G1 | Fine-tune Qwen2.5 small models with **QLoRA** to classify text as `SAFE` or `INJECTION|<attack_type>`. |
| G2 | Prove the gain with a fair **baseline comparison** on a frozen, hand-written test set. |
| G3 | Serve the best model locally (GGUF via llama.cpp, run by Ollama) behind a **FastAPI guard service** with PII-safe audit logging. |
| G4 | Ship a small reference RAG app (`demo_rag/`) with the guard at four checkpoints (user input, retrieved chunks, ingest time, output validation), switchable on/off so the effect can be measured. |
| G5 | Provide an **MCP gateway** that scans tool outputs and enforces read-only, allowlisted tools. |
| G6 | Gate every change with an **automated evaluation in CI** (no merge if scores regress). |
| G7 | Ship a Flutter "attack playground" demo, a model card, a data card, and an evaluation report. |

## 4. Non-goals (v1)

- Moderating harmful content in model replies (this is not a content-safety filter).
- Multi-turn / long-conversation attacks, multimodal injection, and Urdu-script text. Urdu script is a stretch goal for v2, not v1.
- Training a model from scratch, or any paid API, paid GPU, or paid hosting.
- Guaranteeing safety. A classifier is one layer of defense in depth, never the only one.

## 5. Users

| User | Need |
|---|---|
| Developer building a Roman Urdu or Pakistani-market GenAI app | A drop-in `/v1/scan` endpoint with a clear verdict and action. |
| Developer of a RAG app or agent (the bundled `demo_rag` is the worked example) | Guarded retrieval with measurable attack-success-rate reduction and no answer-quality loss. |
| Reviewer or interviewer | A reproducible repo: data card, model card, eval report, CI gate, and a demo they can run in minutes. |

## 6. Scope: threat model

**Attack types** (the `attack_type` label):

| attack_type | Meaning |
|---|---|
| `override` | Tries to cancel or replace earlier instructions ("pichli hidayat bhool jao ..."). |
| `persona` | Role-play or "no rules" framing to change behaviour. |
| `prompt_leak` | Tries to make the model reveal its system prompt or hidden context. |
| `exfiltration` | Tries to send or reveal private data, keys, or other users' data. |
| `tool_abuse` | Tries to make an agent call a tool it should not, or call it with harmful arguments. |

**Sources** (where the text came from, given to the model as input):

| source | Meaning |
|---|---|
| `user_input` | Chat message from the user. |
| `retrieved_chunk` | Text retrieved from the vector store (indirect injection surface). |
| `tool_output` | Text returned by a tool or MCP server (indirect injection surface). |

**Surface forms** (matched-intent evaluation):

| surface | Meaning |
|---|---|
| `en` | English. |
| `ru_mix` | Roman Urdu with English words mixed in. |
| `ru_pure` | Mostly transliterated Urdu. |

**Safety rule for data:** attack payloads in the dataset must be *benign placeholders* (reveal the system prompt, say a secret word, call a harmless tool). The dataset must never contain real instructions for weapons, malware, self-harm, or other harmful content. We teach the model to recognise the *instruction-to-the-AI structure*, not harmful topics.

## 7. Labeling guideline

1. Label `INJECTION` if the text **addresses or instructs an AI system** to deviate from its task or rules, or to reveal or exfiltrate something, regardless of language.
2. Label `SAFE` if the text merely *discusses or mentions* such attacks (for example a security article or a student asking "prompt injection kya hoti hai?").
3. A normal Roman Urdu request that happens to contain words like "ignore", "bhool jao", or "pichli baat" in a harmless sense is `SAFE` (a **hard negative**).
4. When the same text would be an injection in a retrieved chunk but a normal question from a user, `source` is part of the input and the label follows rule 1 for that source.
5. Ambiguous items are removed from the test set rather than guessed.

## 8. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | `POST /v1/scan` accepts `{text, source, request_id?}` and returns `{request_id, verdict, attack_type, action, model, latency_ms, windows}`. |
| FR-2 | `verdict` is `safe`, `injection`, or `error`. There is **no confidence percentage** in v1 (see Phase 6.3 guidance: avoid fake precision). |
| FR-3 | Long text is split into overlapping windows; if any window is flagged, the whole text is flagged. |
| FR-4 | The same `normalize_text()` runs in training, evaluation, and serving. |
| FR-5 | Model output is validated with Pydantic. Malformed output is retried once, then handled by `FAIL_MODE` (default `closed`). |
| FR-6 | `POST /v1/scan/batch` scans a list; `GET /health`; `GET /v1/stats`. |
| FR-7 | API-key auth (`X-API-Key`), request-size limits, and rate limiting (slowapi). |
| FR-8 | Audit log in SQLite stores a hash and length of the text, never the raw text. Quarantined chunks are stored **PII-masked** (Presidio). |
| FR-9 | Actions: `block` (user input), `drop_chunk` (retrieved chunk), `redact_tool_output` (tool output), `log_only` (monitor mode). |
| FR-10 | Reference RAG (`demo_rag/`, LangGraph + Chroma + a local Ollama chat model): guard at user input, after retrieval, at ingest time, and on output validation, switchable by `GUARD_ENABLED`. It calls the guard only over HTTP through `client/`. |
| FR-11 | MCP gateway exposes read-only tools, scans every tool output, and uses an allowlist. |
| FR-12 | Flutter playground: paste text, pick source, see verdict, attack type, and latency; toggle the guard on/off against `demo-rag`. |
| FR-13 | Client SDK (`client/ruguard_client`): sync and async Python wrapper over `/v1/scan` and `/v1/scan/batch` with timeouts and retries; the only way `demo_rag/`, `gateway/`, and `evals/` reach the guard. |

## 9. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | **Cost $0**, no credit card, no paid API. |
| NFR-2 | Runs on CPU in Docker on the owner's machine (WSL2 Ubuntu + Docker Desktop). Hardware specs to be recorded in Phase 0. |
| NFR-3 | Latency target: p95 per window of 400 ms or less for the 0.5B model, 1,000 ms or less for the 1.5B model, on the owner's CPU. **Targets; report measured values.** |
| NFR-4 | Reproducible: fixed seeds, pinned versions, scripts (not only notebooks), versioned datasets with hashes. |
| NFR-5 | Privacy: no raw user text in logs; PII masked before storage; no provider keys in the client app. |
| NFR-6 | Honest reporting: all numbers come from the frozen test set and are reported with confidence intervals. Failures are published. |

## 10. Data requirements

| Set | Size (target) | How it is made | Rules |
|---|---|---|---|
| Seeds | ~80 rows (40 injection, 40 benign) | Hand-written by the owner, covering every attack_type and the `ru_mix`/`ru_pure` forms | Used only as few-shot examples for generation. |
| **Test (frozen)** | **300 rows = 100 matched intents x 3 surface forms** | **Hand-written/rewritten by the owner** (50 injection intents, 10 per attack_type, about 40% indirect sources; 50 benign intents, at least 25 hard negatives) | Never used for training or prompt tuning. Locked with a SHA-256 hash in `data/eval/test.lock`. |
| Train (synthetic) | ~4,000 | Generated with Qwen2.5-14B-Instruct-AWQ (4-bit; 7B was tried first, see D29) on free Colab from the seeds, then filtered | 50% injection, 50% benign (at least 25% hard negatives); about 15% `en`, the rest `ru_mix`/`ru_pure`; all three sources represented. |
| Validation | ~500 | Held-out slice of the synthetic data, plus a human-checked 10% sample | Used for model selection only. |

**v1 provenance note (D22):** at the owner's request, the 80 seeds and the 300-row test set v1 were drafted by the AI coding assistant, not hand-written by the owner. Native-speaker review is pending. Reports must state this.

Data quality gates: Pydantic schema validation, exact and near-duplicate removal (character n-gram Jaccard, no overlap with the test set), length limits, a language-mix heuristic, and a **human review of at least 200 random synthetic rows** before training. Document everything in `data/DATA_CARD.md`.

Public English injection datasets may be adapted only after checking their licences; otherwise generate English with Qwen.

## 11. Model requirements (QLoRA)

- **Base models:** Qwen2.5-0.5B-Instruct and Qwen2.5-1.5B-Instruct (both trained; compared on the test set). Check each model's licence on its model card before publishing weights.
- **Data generator:** Qwen2.5-14B-Instruct-AWQ, 4-bit, with vLLM on the Colab T4 (Transformers + bitsandbytes as fallback). 7B was tried first and produced too much incoherent Roman Urdu (D29).
- **Method:** QLoRA with Unsloth, Hugging Face Transformers, PEFT, TRL (`SFTTrainer`, loss on the assistant answer only), and bitsandbytes (4-bit NF4).
- **Starting hyperparameters (tune on validation only):** LoRA r=16, alpha=32, dropout 0.05, all linear projection modules; learning rate 2e-4 with cosine schedule and 3% warmup; 3 epochs; effective batch size 32; max sequence length 512; **fp16** (the free Colab T4 does not support bfloat16); fixed seed.
- **Output format:** one line, `SAFE` or `INJECTION|<attack_type>`; temperature 0; at most 8 new tokens.
- **Export:** merge the adapter, convert to GGUF (Q4_K_M, plus Q8_0 for comparison) with llama.cpp or Unsloth's export, and register in Ollama with a `Modelfile`.
- **Deliverables per model:** adapter, merged weights, GGUF, `MODEL_CARD.md` (data, limits, intended use, evaluation).

## 12. Tool whitelist (all free, all from the owner's roadmap documents)

| Area | Tools | Doc section |
|---|---|---|
| Language, API, data | Python 3.12, FastAPI, Pydantic, Pandas, NumPy, matplotlib/seaborn, pytest | Roadmap 0.1, 0.6; Study Guide 3.4 |
| Storage | SQLite | Matrix Phase 6; Roadmap 0.2 |
| Dev environment | Git, GitHub, Docker, venv + pip | Roadmap 0.4, 0.5 |
| Context and RAG (`demo_rag/`) | Chroma (with its built-in default embedding function), LangChain pieces, LangGraph, tiktoken | Roadmap 2.1 to 2.5; Study Guide 2.2 (`DefaultEmbeddingFunction`) |
| Chat model for `demo_rag/` | Qwen2.5-Instruct (general model, not fine-tuned) served by Ollama | Roadmap 1.2, 4.3 |
| Structured output | Pydantic (Outlines optional for local inference) | Roadmap 2.4 |
| Agents and protocols | MCP (official Python SDK), LangGraph | Roadmap 3.2, 2.5+ |
| Models and fine-tuning | Qwen2.5, Hugging Face Transformers, PEFT, TRL, bitsandbytes, Unsloth | Roadmap 1.2, 4.1, 4.2 |
| Free compute | Google Colab free GPU | Study Guide Day 8 |
| Serving | llama.cpp (GGUF), Ollama, vLLM (generation only, optional) | Roadmap 4.3 |
| Deployment | FastAPI + Docker, slowapi for rate limiting | Roadmap 5.1; Study Guide 5.1 |
| Observability | OpenTelemetry; Langfuse (self-hosted, optional) | Roadmap 5.2 |
| Safety | Microsoft Presidio; Llama Guard, Guardrails AI, NeMo Guardrails (baselines) | Roadmap 5.3 |
| Evaluation | Ragas, DeepEval, TruLens (optional), Promptfoo | Roadmap 5.6 |
| CI/CD | GitHub Actions | Roadmap 5.7 |
| Client | Flutter, Riverpod, http/dio, SSE | Roadmap 6 |

**Libraries needed by listed tools but not named in the roadmap documents (approved by the owner on 2026-11-09, open question 2, decision D15):** `httpx` (required by FastAPI's test client; also used for async calls to Ollama and `guard-api`) and `PyYAML` (attack suite, golden set, and training configs). `uvicorn` is also needed to serve FastAPI and appears in Study Guide 5.1.

**Operational notes (not project dependencies):** Colab's built-in Google Drive mount is used only to move adapters and GGUF files between Colab and the local machine. GitHub Releases hold the GGUF file for CI (check current size limits).

**Not allowed:** paid LLM APIs, Pinecone, Colab Pro, paid hosting, and any tool not listed above without the owner's approval. Depending on, importing from, or modifying any other project is also out of scope.

## 13. Evaluation plan and success metrics

All evaluation runs on the frozen test set; compare **fine-tuned vs baselines** under identical normalization and prompt format.

**Baselines (before any fine-tuning):**
1. Rule baseline: keyword/regex heuristics (English and Roman Urdu patterns).
2. Qwen2.5-1.5B-Instruct, zero-shot with the same system prompt.
3. Qwen2.5-1.5B-Instruct, few-shot (from the seeds).
4. Llama Guard, zero-shot (it targets content-safety categories, not injection; report it with that caveat).
5. Stretch: Guardrails AI or NeMo Guardrails if an offline free rail works within one day of effort.

**Metrics:**

| Metric | Cut by |
|---|---|
| Injection recall; benign false-positive rate (FPR); precision; F1 | surface form, source, attack_type, hard negatives |
| Macro-F1 on `attack_type` | overall |
| Invalid-output rate | model |
| Latency p50/p95 (CPU) | model, quantization |
| Attack Success Rate (ASR) in `demo_rag` | guard off vs on, scripted suite of 30 to 50 attacks |
| Golden-set answer correctness (deterministic keyword containment) and citation-presence rate | guard off vs on, 30-question golden set; Ragas is optional and uses a local Ollama judge only |
| Bootstrap 95% confidence intervals (NumPy) | all headline numbers |

**Targets (confirm or adjust after Phase 3 baselines; report honestly if missed):**

| Target | Value |
|---|---|
| Injection recall on `ru_mix` + `ru_pure` at FPR <= 3% | >= 0.90 |
| Beat the best baseline on recall at matched FPR | yes, gap reported with CI |
| Recall drop from `en` to `ru_pure` | <= 10 points |
| ASR reduction in `demo_rag` with guard on | >= 80% relative |
| Golden-set correctness change with guard on | no worse than -3 points (at most 1 of 30 questions) |
| Invalid-output rate | <= 1% |

## 14. Acceptance criteria (release v1.0)

1. Frozen test set intact (hash matches) and all headline numbers reproducible from one documented command.
2. QLoRA adapters, merged weights, GGUF files, and model/data cards exist for both sizes; the deployed model is chosen by the evaluation, with reasoning written down.
3. `docker compose up` starts Ollama + guard-api (`--profile demo` adds `demo-rag`); `/v1/scan` works from a clean checkout following the README.
4. `demo_rag` demonstrates guard off vs on with the scripted attack suite and the golden set; ASR and quality tables are in the evaluation report.
5. MCP gateway blocks a poisoned tool output in a test.
6. CI runs unit tests on every PR and the evaluation gate (smoke on PR, full nightly); thresholds stored in `evals/thresholds.json`.
7. Flutter playground runs against the local service; README has an architecture diagram, demo video, limitations, and a "how to run in 5 minutes" section.

## 15. Milestones (about 4 to 6 weeks, part-time)

| Phase | Name | Estimate |
|---|---|---|
| 0 | Scaffold and environment | 1 day |
| 1 | Taxonomy, seeds, frozen test set (human-heavy) | 4 to 5 days |
| 2 | Synthetic data generation and quality gates | 3 days |
| 3 | Baselines | 2 days |
| 4 | QLoRA fine-tuning and export | 4 days |
| 5 | Full evaluation and error analysis | 2 days |
| 6 | Guard service (FastAPI + Ollama + Docker) | 3 days |
| 7 | Reference RAG, client SDK + MCP gateway | 5 days |
| 8 | Observability, red-team, CI gate | 3 days |
| 9 | Flutter playground | 3 days |
| 10 | Packaging and release | 2 days |

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Synthetic Roman Urdu from a 7B model is unnatural or inconsistent | Seeds written by a native speaker; filters; 200-row human review; test set fully human-written; report the limitation. |
| Train/test leakage inflates results | Hand-written test set; near-duplicate check against train; lock hash; never tune on test. |
| Over-blocking (false positives) hurts usability | Hard negatives in train and test; FPR is a headline metric; `log_only` mode. |
| Free Colab GPU limits (session cap, idle timeout, no guaranteed T4, no bf16) | Scripts with checkpoints saved to Drive every epoch; fp16; small models; resumable training. |
| Generative classifier is slower than an encoder | Measure p95; Q4 quantization; 0.5B option; short outputs; report latency honestly. |
| Evasion (padding, homoglyphs, spelling variants) | Normalizer; sliding windows; adversarial test items; Promptfoo red-team. |
| Guard becomes a single point of failure | `FAIL_MODE` setting; health checks; defense in depth (instruction/data separation, least privilege, output validation). |
| Model licence restrictions | Check each licence before publishing; document in the model card. |
| Hardware too weak for 1.5B on CPU | Fall back to 0.5B; record specs in Phase 0. |
| ASR results on one small reference RAG may not generalise to other apps | Present them as a reference-app result; the frozen test set is the primary evidence; the `/v1/scan` contract is app-agnostic; list `demo_rag` limits in the report. |
| The chat model in `demo_rag` is small, so quality numbers are noisy | Deterministic golden-set metric, temperature 0, fixed seed; report the question count and per-question diffs. |

## 17. Open questions for the owner

1. Laptop RAM/CPU for the latency target? (Record in Phase 0.)
2. ~~Two Python libraries are not named in your documents but are required by listed tools: `httpx` (FastAPI's test client and async HTTP calls) and `PyYAML` (config and test-suite files). Approve both, or name the replacements you prefer?~~ Resolved 2026-11-09: both approved (D15).
3. Will you write the 100 matched test intents yourself (about 2 to 3 days)? This cannot be delegated to Claude Code.
4. Should v2 add Urdu script after v1.0 is released?
5. Will you write or review about 10 Roman Urdu documents and the poisoned documents for the `demo_rag` corpus (Phase 7, about half a day)? They must not reuse test-set rows.

## 18. Roadmap alignment

| Roadmap item | Where it appears |
|---|---|
| 2.1 Context engineering | `<documents>` tag separation, token budget |
| 2.4 Structured output | Pydantic-validated scan responses |
| 3.2 MCP and tool safety | MCP gateway, allowlist, read-only tools |
| 4.2 QLoRA and baseline comparison | Phases 3 to 5 |
| 4.3 Optimization | GGUF quantization, Ollama |
| 5.1 to 5.3 | Docker service, tracing, Presidio, guardrail baselines |
| 5.6 to 5.7 | Evaluation, GitHub Actions gate |
| 6 | Flutter playground |
| 7 | README, diagrams, whiteboard walkthrough |
