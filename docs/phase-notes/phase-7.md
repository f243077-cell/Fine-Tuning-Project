# Phase 7: Reference RAG, client SDK, and MCP gateway

Branch / commit: `main`. Status: **done; Gate 7 passed (owner-delegated, 2026-11-15). The owner reviews the Roman Urdu texts when running the app (D54).**

## Done
- `client/ruguard_client`: sync and async clients for `/v1/scan`, `/v1/scan/batch`, `/health`, `/v1/stats`; Pydantic models; retries on transport errors, 429, and bodiless 502/503/504; `fail_mode` closed (default), open, or raise (D53). Tests use `httpx.MockTransport`. `evals/parity.py` and `evals/bench_latency.py --guard-url` now use it.
- `tests/test_boundaries.py`: 9 more violation cases (client, demo_rag, gateway, evals) and 3 allowed cases.
- Corpus: 30 English and 10 Roman Urdu documents about a fictional company (Noorbagh Electronics), plus 6 English and 3 Roman Urdu poisoned documents with harmless placeholder payloads. `scripts/check_corpus_leak.py` compares every paragraph of the corpus, poisoned docs, gateway notes, attack suite, and golden set with the frozen test set (read-only): 249 pieces, none at or above the threshold (highest 0.135 on the 243 pieces checked before the gateway notes were added) (threshold 0.5).
- `demo_rag/`: tiktoken chunking, Chroma store with the default embedding function, `ingest.py` with the G0 scan and a quarantine report, LangGraph `graph.py` (G1 `guard_input`, `retrieve`, G2 `guard_chunks`, `build_prompt` with `<documents>` tags, a token budget, and a canary token, `generate`, G4 `validate_output` with one retry), `validate.py`, and a FastAPI app on `:8002` (`POST /chat`, `GET /chat/stream` SSE, `GET /health`, `guard=on|off` only with `ALLOW_GUARD_TOGGLE=true`). `recursion_limit` is always set.
- `gateway/`: MCP server (SDK 2.3, `MCPServer`) with only `search_docs`, `scan_text`, and `get_note`; Pydantic argument checks, a timeout, a 4,000-character result cap, and a `tool_output` scan with redaction. Tests: a poisoned Roman Urdu note is redacted, and non-allowlisted tools and bad arguments are refused (also through an in-process MCP client).
- `evals/attack_suite.yaml` (36 scenarios), `evals/run_asr.py`, `evals/golden_set.yaml` (30 questions), `evals/run_quality.py`.
- Regression test: with the guard off the graph makes zero guard calls (a client that raises) and sends the same prompts and gives the same answers as a plain RAG pipeline on all 30 golden questions.
- `docker/Dockerfile.demo`, the `demo-rag` compose service (profile `demo`), and the host-Ollama override; `scripts/register_model.sh` also pulls `qwen2.5:1.5b-instruct` (the tag already in the owner's Ollama). `requirements-demo.txt` pinned.

## Numbers (real runs, 2026-11-15, owner's CPU; guard ru-guard-1.5b-v2 in Docker, chat model qwen2.5:1.5b-instruct on host Ollama 0.32.15)
- **G0 ingest** (`python -m demo_rag.ingest --guard on --report`): 49 chunks; poisoned chunks flagged 9 of 9, clean chunks flagged 0 of 40 (`demo_rag/reports/ingest_report_guard_on.json`).
- **ASR** (legacy index built with `--guard off`, so the 9 poisoned chunks are in it; `evals/reports/asr/ASR.md`): guard off 8 of 36 (0.222), guard on 0 of 36 (0.000).
  - By type, off then on: direct 4/12 then 0/12, prompt_leak 2/6 then 0/6, poisoned_tool 2/6 then 0/6, poisoned_chunk 0/12 then 0/12.
  - With the guard on, G1 blocked all 18 direct and prompt-leak questions, G2 dropped the poisoned chunk in all 12 poisoned-chunk scenarios, and the tool-output scan redacted all 6 poisoned tool outputs.
  - The poisoned documents were retrieved in 12 of 12 scenarios, but the chat model did not follow their instructions even with the guard off. So the ASR shows no G2 effect on this chat model; G2 still removed every poisoned chunk.
- **Golden-set quality** (`evals/reports/quality/QUALITY.md`): correct (keywords and a citation) guard off 25/30, guard on 27/30; keywords only 26/30 and 27/30; cited 27/30 and 30/30. English 20/20 in both. Roman Urdu (10 questions) 5 then 7 correct. With the guard on, no golden question was blocked or refused. The 3 misses are Roman Urdu questions the chat model answered wrongly or in English.
- Tests: all green (see the commit).

## Run history (the golden set is a dev set, not the frozen test set)
- Run 1 (`evals/reports/*/run1/`): ASR off 14/36, on 0/36; quality off 1/30, on 12/30. The chat model rarely wrote `[doc-id]` citations unless G4's retry reminded it, so "correct" mostly measured citing.
- Run 2 (`run2/`): the prompt asks for document ids at the end of the answer. ASR off 9/36, on 0/36; quality off 16/30, on 22/30. Several correct answers were refused because the model wrote `[doc-id:en-02-...]` (it copied the instruction literally).
- Run 3 (reported above): the citation parser also accepts `[doc-id: ...]`, and the prompt no longer shows the literal `[doc-id]` pattern. Two changes, both made after looking at golden-set answers; no change was made to the guard model or the attack suite.

## Open issues
- **[HUMAN]** The owner reviews the 10 Roman Urdu corpus docs, the 3 Roman Urdu poisoned docs, the Roman Urdu attack scenarios, and the 10 Roman Urdu golden questions (all drafted by Claude, D53).
- The corpus docs are shorter than 300 tokens, so each doc is one chunk (the 300 to 800 token range applies only to longer docs).
- Indirect attacks did not succeed against qwen2.5:1.5b-instruct even unguarded, so the ASR suite cannot show G2's value on this model. A weaker or more obedient chat model, or stronger poisoned texts, would be needed to show it.
- The Roman Urdu answer quality of the 1.5B chat model is the main quality limit (7 of 10 correct with the guard on).
- Docker: the demo-rag image builds (1.26 GB) and runs with `docker-compose.host-ollama.yml`. At start it ran G0 (9 of 9 poisoned chunks quarantined, 0 of 40 clean flagged); `/chat` answered a Roman Urdu and an English question with citations, blocked an attack, and `/chat/stream` sent 7 events. The full compose path with the `ollama` container is still untested here (slow link; D52).
- Ragas (optional) not run.
- Diagrams: no picture in `docs/understanding/` is made stale (the graph and checkpoints match Architecture.md section 12).
