# Phase 3: Baselines before any fine-tuning

Branch / commit: `main`. Status: **in progress (paused 2026-11-13).**

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

## Remaining (next session)
1. `python evals/eval_guard.py --model qwen-zs --split test`
2. `python evals/eval_guard.py --model llama-guard --split test`
3. `python evals/eval_guard.py --model qwen-fs --split test`
4. Write `evals/reports/baselines_notes.md` (findings, caveats, D43 fail-closed scoring), then `python evals/compare.py`.
5. Tick "Run all baselines"; propose PRD target changes only if needed; stop at Gate 3.
