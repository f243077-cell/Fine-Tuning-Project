# Smoke gate check (Phase 8 follow-up, 2026-11-16)

The PR smoke eval runs 100 test rows (`eval_guard.py --subset smoke`) and `gate.py --thresholds evals/thresholds_smoke.json`.

## Why the margin is 10 points, not 2

The first real CI smoke runs failed the gate on commits with no change to the model or the code (run 52 failed; runs 51 and 55 passed). Evidence gathered on 2026-11-16, all with the same GGUF (SHA-256 `52b5472a...`) and Ollama 0.32.15:

| Environment | Rows that differ from the saved release run (100 rows) | Recall | FPR | F1 | Attack-type macro-F1 | Roman Urdu FPR |
|---|---|---|---|---|---|---|
| Saved release run (slice of the 300-row run, owner's laptop) | 0 | 0.920 | 0.120 | 0.902 | 0.845 | 0.182 |
| Owner's laptop, fresh smoke run (different request order) | 2 | 0.920 | 0.140 | 0.893 | 0.819 | 0.212 |
| GitHub runner, CI run 55 | not measured | 0.920 | 0.140 | 0.893 | 0.798 | 0.212 |
| GitHub runner, AMD EPYC 9V45 (4 cores), 3 runs with an Ollama restart before each (jitter diagnostic, branch `diag/jitter`) | 4 (all 3 runs identical to each other) | 0.940 | 0.160 | 0.895 | 0.822 | 0.242 |
| GitHub runner, CI run 52 | not measured (the gate failed at step 11) | not recorded | | | | |

Reading: repeated runs on one machine with the same request order give the same labels (0 rows differ between the three runner runs). The labels move by 2 to 4 rows of 100 between environments (a different CPU, or a different request order). With 50 rows per class one row is 2 points, and one row of the 33 Roman Urdu benign rows is 3 points. The attack-type macro-F1 is the noisiest metric (about 10 attacks per type): it fell by 2 to 5 points in every environment. At a 6-point margin the diagnostic run failed the gate by 0.0006 on Roman Urdu FPR (0.2424 against 0.2418, two flipped rows). The cause (CPU model, order, or both) is not isolated.

`thresholds_smoke.json` is now the release model's 100-row metrics minus **10 points**; the invalid-output ceiling stays at 2 points. The full 300-row gate (`thresholds.json`) is unchanged at 2 points.

Command: `python evals/gate.py --make evals/reports/runs/ru-guard-1.5b-v2-smoke --tolerance 0.10 --thresholds evals/thresholds_smoke.json`

## What the 10-point gate still catches

Each saved 300-row run reduced to the same 100 smoke rows and checked against `thresholds_smoke.json` (real predictions, no new model calls), plus the two CI-runner observations above:

| Run | Recall | FPR | Smoke gate |
|---|---|---|---|
| ru-guard-1.5b-v2 (deployed) | 0.92 | 0.12 | PASS |
| GitHub runner, CI run 55 | 0.92 | 0.14 | PASS |
| GitHub runner, EPYC 9V45 | 0.94 | 0.16 | PASS |
| ru-guard-1.5b (v1) | 0.86 | 0.10 | PASS |
| ru-guard-1.5b-q8_0 (v1) | 0.84 | 0.10 | FAIL (1 check) |
| ru-guard-0.5b-v2 | 0.88 | 0.10 | FAIL (1 check) |
| ru-guard-0.5b (v1) | 0.78 | 0.06 | FAIL (3 checks) |
| ru-guard-0.5b-q8_0 (v1) | 0.80 | 0.06 | FAIL (3 checks) |
| Qwen2.5-1.5B zero-shot (untuned) | 0.52 | 0.36 | FAIL (7 checks) |
| Qwen2.5-1.5B few-shot (untuned) | 0.92 | 0.68 | FAIL (4 checks) |
| Llama Guard 3 1B | 0.40 | 0.16 | FAIL (4 checks) |
| rules | 0.26 | 0.02 | FAIL (4 checks) |

The regression drill on CI: branch `drill/untuned-model` swaps the untuned Qwen2.5-1.5B-Instruct in under the guard's name; CI run 53 failed at the Merge gate (step 12). An earlier drill with a scanner that calls everything safe failed the unit tests (run 47).

**Limit.** A 10-point margin on 100 rows is a "does it still basically work" check: it catches a broken, untuned or wrongly templated model, but it passes the older v1 1.5B model. The nightly 300-row gate (2 points) is the fine check, and it has not run yet; if it flakes across runner hardware the same way, its margin would need widening (an owner decision, because it changes a threshold set by the PRD).
