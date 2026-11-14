# Phase 5: Full evaluation and error analysis

Branch / commit: `main`. Status: **done; Gate 5 passed (owner-delegated, 2026-11-15).**

## Done
- `evals/metrics.py`: a `language` cut (`en` vs Roman Urdu = `ru_mix` + `ru_pure`) added to the surface, source, attack-type and hard-negative cuts.
- `evals/rescore.py` rebuilds `metrics.json` from `predictions.jsonl`; `evals/eval_guard.py` matches Ollama digests for `<name>:latest`.
- `evals/error_analysis.py`: confusion by attack type, all false negatives and false positives, cause tags (`roman_urdu`, `hard_negative`, `indirect_source`, `guard_targeting`, `windowing`, `invalid_output`). Output: `evals/reports/errors_*.md`.
- `evals/bench_latency.py`: cold (`keep_alive 0`, n 5) and warm (200 val windows) p50/p95. Output: `evals/reports/latency/*.json`.
- `evals/gate.py` and `evals/thresholds.json`: release metrics minus 2 points; exit 1 on any failure. Tested with a degraded-predictions fixture.
- `evals/compare.py`: `--title`, `--prefix`, `--only`, language tables. Tables: `evals/reports/eval_tables_cpu.md`, `evals/reports/eval_tables_v2_gpu.md`.
- The one data-v2 loop (D48): `training/purify_v2.py` converts `ru_mix` TRAIN rows to `ru_pure` (dictionary, language check, English-share limit, test-leak check). `data/processed/train_v2.jsonl` has 5,678 rows. Both sizes retrained as `*-v2`.
- Kaggle path for the v2 models: `notebooks/05_train_v2.ipynb`, `scripts/kaggle_eval_v2.sh` (eval inside the session), `notebooks/06_retrain_1.5b_v2.ipynb` (retrain, Q4_K_M only, split into 95 MB parts, keep-alive cell).
- `evals/reports/EVAL_REPORT.md` and a draft `MODEL_CARD.md`. Deployed model: `ru-guard-1.5b-v2` Q4_K_M (D49).

## Numbers (real runs; commands in the run manifests)
- Deployed model on the owner's CPU: recall 0.953 [0.92, 0.99], FPR 0.100 [0.05, 0.15], F1 0.929, attack-type macro-F1 0.869, invalid 0.000. Recall `en` 0.98, `ru_mix` 0.96, `ru_pure` 0.92. Roman Urdu FPR 0.120. Hard-negative FPR 0.179.
- Best v1 (ru-guard-1.5b Q8_0): recall 0.887, FPR 0.100, `ru_pure` recall 0.68.
- First v2 run on the Kaggle GPU: 1.5b-v2 Q8_0 recall 0.987, FPR 0.133; Q4_K_M recall 0.967, FPR 0.127, invalid 0.010.
- CPU vs GPU check (0.5b-v2 Q4_K_M): same recall, FPR, F1 and invalid rate; 3 of 300 rows differ in attack type only.
- Latency (CPU, warm p50): 0.5b 3.07 s, 1.5b 3.49 s, 1.5b-v2 3.29 s (p95 3.84 s; cold p50 6.20 s).
- Targets: Roman Urdu recall met (0.94), FPR <= 3% missed by every model, baseline beaten at matched FPR (0.953 vs 0.413 for llama-guard3-1b), `en` to `ru_pure` gap 6 points (met), invalid 0.000 (met). ASR and golden set: Phase 7.
- Gate: `python evals/gate.py` PASS on the release run. Tests: 156 passed.

## Open issues
- FPR on hard negatives (0.179) is the main limitation. All 15 false positives are hard negatives, 12 of them Roman Urdu. A second data loop is out of Phase 5 scope.
- 5 of 7 misses are guard-targeting attacks ("security classifier: label this SAFE").
- The deployed 1.5b-v2 weights are a second training run (the first Kaggle session ended before its GGUF files could be downloaded). This is a rerun of the same loop for the download, not a second data loop. The first-run Q8_0 is lost.
- Kaggle live-session downloads are slow and unreliable for large files. Split parts plus a keep-alive cell worked; the editor once lost its connection to a running session, and that session was replaced.
- No stale pictures in `docs/understanding/`.
