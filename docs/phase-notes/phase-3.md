# Phase 3: Baselines before any fine-tuning

Branch / commit: `main`. Status: **done, stopped at Gate 3 (2026-11-14).**

## Done
- `evals/metrics.py`: recall, FPR, precision, F1, macro-F1 over attack type, invalid-output rate, cuts (surface, source, attack type, hard negatives), and bootstrap 95% CIs (NumPy, 1,000 resamples, seed 1234). Invalid outputs count as flags (fail closed). Tests: `evals/tests/test_metrics.py`.
- `evals/baselines.py`:
  - regex rules for English and Roman Urdu, written once and not tuned on the test set;
  - Qwen2.5-1.5B-Instruct zero-shot and few-shot (8 fixed seed examples) via Ollama with the shared prompt;
  - Llama Guard 3 1B via Ollama ("unsafe" maps to a plain INJECTION flag).
- `evals/eval_guard.py`: one runner with the shared normalizer and prompt, the strict output grammar, windowing, latency, and versions.
- `evals/compare.py`: tables and charts into `evals/reports/baselines.md`, with hand-written notes appended from `evals/reports/baselines_notes.md`.
- Rules baseline on the 300 test rows: recall 0.280, FPR 0.020 (`evals/reports/runs/rules/metrics.json`).
- Ollama 0.32.15 models pulled: `qwen2.5:1.5b-instruct` (digest prefix `65ec06548149`) and `llama-guard3:1b` (`494147e06bf9`).

## Observations from a 5-row smoke run
- Qwen zero-shot often outputs the literal placeholder `INJECTION|<attack_type>`, which is invalid under the strict grammar.
- Llama Guard 3 1B has content-safety categories only (S1 to S13) and answered "safe" on 5 attack rows.
- About 5 seconds per row on this CPU, so about 25 minutes per 300-row run.

## Results (300 test rows, lock `1f8710e6fbae` verified)
Full report with CIs and cuts: `evals/reports/baselines.md`.

| Model | Recall | FPR | F1 | Invalid |
|---|---|---|---|---|
| rules | 0.280 | 0.020 | 0.431 | 0.000 |
| qwen2.5-1.5b zero-shot | 0.453 | 0.347 | 0.504 | 0.400 |
| qwen2.5-1.5b few-shot | 0.927 | 0.647 | 0.720 | 0.010 |
| llama-guard3 1b | 0.413 | 0.127 | 0.537 | 0.000 |

- Zero-shot never emits a valid INJECTION label. Its recall comes only from fail-closed scoring of invalid output (D43).
- Few-shot over-flags: 83 of its 97 false flags say `tool_abuse`.
- No baseline is near the target of recall >= 0.90 at FPR <= 3%. The best baseline under 3% FPR is rules (recall 0.280).
- Decision added: D43 (fail-closed scoring).

## Open issues
- PRD target proposal (not applied): judge FPR <= 3% on the point estimate and report the CI next to it. With 150 SAFE rows the CI upper end is about 6%. See `evals/reports/baselines_notes.md`.
- Guardrails AI and NeMo Guardrails (stretch) were not run.
- The first few-shot run stopped at row 198 when Ollama shut down. It was re-run in full.
- No diagrams in `docs/understanding/` became stale.

## Gate 3
The owner reads `evals/reports/baselines.md`, then confirms the PRD section 13 targets or adjusts them. Phase 4 starts only after "start phase 4".
