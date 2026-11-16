# RU-Guard evaluation report (Phases 5 to 8)

Frozen test set `data/eval/test.jsonl` (lock `1f8710e6fbae`, verified before every run): 300 rows, 150 INJECTION and 150 SAFE, 100 per surface (`en`, `ru_mix`, `ru_pure`), 84 SAFE rows are hard negatives. Every number below comes from a recorded run in `evals/reports/runs/` (owner's CPU, Ollama 0.32.15) or `evals/reports/runs_kaggle_gpu/` (Kaggle T4, Ollama). 95% CIs come from 1,000 bootstrap resamples (seed 1234). Invalid output counts as a flag (fail closed, D43). Targets are judged on the point estimate; the CI is shown next to it (D44).

Full tables: [eval_tables_cpu.md](eval_tables_cpu.md) (all models on the CPU, the headline), [eval_tables_v2_gpu.md](eval_tables_v2_gpu.md) (the four data-v2 models on the Kaggle GPU), [baselines.md](baselines.md).

## 1. Deployed model

**`ru-guard-1.5b-v2`, Q4_K_M** (Qwen2.5-1.5B-Instruct + QLoRA, dataset v2; D48, D49). GGUF SHA-256 `52b5472abc1419f8c43645a733dd4dd9ee9e6e8b1be7de974d61dd988f8022e7`, 986,048,224 bytes, Ollama digest `0199eaf6b9c3`.

Reproduce: `python evals/eval_guard.py --model ollama:ru-guard-1.5b-v2 --split test`.

| Metric | Value [95% CI] |
|---|---|
| Recall | 0.953 [0.92, 0.99] |
| FPR | 0.100 [0.05, 0.15] |
| Precision | 0.905 [0.86, 0.95] |
| F1 | 0.929 [0.90, 0.96] |
| Macro-F1 on attack type | 0.869 [0.81, 0.91] |
| Invalid output | 0.000 |
| Recall `en` / `ru_mix` / `ru_pure` | 0.980 / 0.960 / 0.920 |
| Recall Roman Urdu (`ru_mix` + `ru_pure`) | 0.940 [0.89, 0.98] |
| FPR `en` / Roman Urdu | 0.060 / 0.120 |
| FPR plain SAFE / hard negatives | 0.000 / 0.179 [0.11, 0.26] |

## 2. All models on the owner's CPU

| Model | Recall | FPR | F1 | Macro-F1 (type) | Invalid | Roman Urdu recall | `ru_pure` recall |
|---|---|---|---|---|---|---|---|
| rules | 0.280 [0.21, 0.35] | 0.020 [0.00, 0.04] | 0.431 | 0.370 | 0.000 | 0.250 | 0.160 |
| qwen2.5-1.5b zero-shot | 0.453 [0.37, 0.53] | 0.347 [0.27, 0.43] | 0.504 | 0.000 | 0.400 | 0.390 | 0.320 |
| qwen2.5-1.5b few-shot | 0.927 [0.88, 0.96] | 0.647 [0.58, 0.72] | 0.720 | 0.266 | 0.010 | 0.940 | 0.960 |
| llama-guard3-1b | 0.413 [0.33, 0.50] | 0.127 [0.08, 0.18] | 0.537 | 0.000 | 0.000 | 0.390 | 0.380 |
| ru-guard-0.5b (v1, Q4_K_M) | 0.773 [0.71, 0.84] | 0.067 [0.03, 0.11] | 0.841 | 0.735 | 0.007 | 0.680 | 0.520 |
| ru-guard-0.5b (v1, Q8_0) | 0.807 [0.74, 0.86] | 0.073 [0.03, 0.12] | 0.858 | 0.763 | 0.007 | 0.730 | 0.580 |
| ru-guard-1.5b (v1, Q4_K_M) | 0.840 [0.77, 0.89] | 0.093 [0.05, 0.14] | 0.869 | 0.750 | 0.000 | 0.760 | 0.560 |
| ru-guard-1.5b (v1, Q8_0) | 0.887 [0.83, 0.93] | 0.100 [0.05, 0.15] | 0.893 | 0.768 | 0.000 | 0.830 | 0.680 |
| ru-guard-0.5b-v2 (Q4_K_M) | 0.880 [0.83, 0.93] | 0.127 [0.08, 0.18] | 0.877 | 0.780 | 0.003 | 0.850 | 0.860 |
| **ru-guard-1.5b-v2 (Q4_K_M)** | **0.953 [0.92, 0.99]** | **0.100 [0.05, 0.15]** | **0.929** | **0.869** | **0.000** | **0.940** | **0.920** |

![recall by surface](figures/eval_cpu_recall_by_surface.png)
![recall by attack type](figures/eval_cpu_recall_by_attack_type.png)
![FPR on hard negatives](figures/eval_cpu_fpr_hard_negative.png)

### Data-v2 models on the Kaggle GPU (first v2 training run)

The v2 GGUF files of the first training run could not be downloaded from the Kaggle session (D49), so all four were evaluated there with the same harness (`scripts/kaggle_eval_v2.sh`).

| Model | Recall | FPR | F1 | Macro-F1 (type) | Invalid | `ru_pure` recall |
|---|---|---|---|---|---|---|
| ru-guard-0.5b-v2 Q4_K_M | 0.880 [0.83, 0.93] | 0.127 [0.08, 0.18] | 0.877 | 0.779 | 0.003 | 0.860 |
| ru-guard-0.5b-v2 Q8_0 | 0.900 [0.85, 0.95] | 0.147 [0.09, 0.20] | 0.879 | 0.797 | 0.003 | 0.880 |
| ru-guard-1.5b-v2 Q4_K_M | 0.967 [0.93, 0.99] | 0.127 [0.08, 0.18] | 0.924 | 0.812 | 0.010 | 0.920 |
| ru-guard-1.5b-v2 Q8_0 | 0.987 [0.97, 1.00] | 0.133 [0.09, 0.19] | 0.931 | 0.852 | 0.003 | 0.980 |

**CPU vs GPU check.** `ru-guard-0.5b-v2` Q4_K_M was downloaded and re-run on the CPU: recall, FPR, F1 and invalid rate are identical to the GPU run; 3 of 300 rows differ, only in the attack type.

**Retrain note.** The deployed 1.5b-v2 file is a second training run (same data, config and seed, notebook `notebooks/06_retrain_1.5b_v2.ipynb`), because the first Kaggle session ended before its GGUF could be downloaded. GPU training is not bit-for-bit deterministic, so the weights differ. Against the first run's Q4_K_M on the GPU, the retrain on the CPU has slightly lower recall (0.953 vs 0.967), lower FPR (0.100 vs 0.127), higher attack-type macro-F1 (0.869 vs 0.812) and no invalid output (0.000 vs 0.010). All differences are inside the CIs.

## 3. Targets (PRD section 13)

| Target | Value | Result (deployed model, CPU) | Status |
|---|---|---|---|
| Injection recall on `ru_mix` + `ru_pure` at FPR <= 3% | >= 0.90 | Roman Urdu recall 0.940 [0.89, 0.98], but at FPR 0.100 overall (0.120 on Roman Urdu) | **Missed** (recall met, FPR not) |
| Beat the best baseline on recall at matched FPR | yes, gap with CI | At FPR ~0.10 to 0.13: 0.953 [0.92, 0.99] vs llama-guard3-1b 0.413 [0.33, 0.50], gap 0.54, CIs do not overlap. The few-shot baseline reaches 0.927 recall only at FPR 0.647 | **Met** |
| Recall drop from `en` to `ru_pure` | <= 10 points | 0.980 to 0.920, 6 points (v1 1.5b Q8_0: 32 points) | **Met** |
| Invalid-output rate | <= 1% | 0.000 | **Met** |
| ASR reduction in `demo_rag` | >= 80% relative | 8 of 36 attacks succeed with the guard off, 0 of 36 with it on: 100% relative reduction (section 9; small n, and the poisoned-document scenarios never succeeded even without the guard) | **Met** (with caveats) |
| Golden-set correctness change | >= -3 points | 25/30 (0.83) guard off, 27/30 (0.90) guard on: +6.7 points (section 9) | **Met** |

No model reaches FPR <= 3% at useful recall. The only one under 3% is the rule baseline (FPR 0.020) at recall 0.280.

## 4. English vs Roman Urdu gap

| Model | Recall en | Recall Roman Urdu | Gap (points) | FPR en | FPR Roman Urdu |
|---|---|---|---|---|---|
| ru-guard-1.5b (v1, Q8_0) | 1.000 | 0.830 | 17 | 0.060 | 0.120 |
| ru-guard-0.5b-v2 (Q4_K_M) | 0.940 | 0.850 | 9 | 0.020 | 0.180 |
| ru-guard-1.5b-v2 (Q4_K_M) | 0.980 | 0.940 | 4 | 0.060 | 0.120 |

Data v2 (D48) closed most of the recall gap: `ru_pure` recall for the 1.5B model went from 0.680 (v1 Q8_0) to 0.920. The cost moved to FPR: Roman Urdu benign text is flagged at twice the English rate (0.120 vs 0.060), mostly `ru_pure` hard negatives (FPR 0.180 on `ru_pure`).

## 5. Latency (owner's CPU, Ollama 0.32.15)

`python evals/bench_latency.py --model <name>`: cold = model unloaded before each call (`keep_alive 0`, n = 5); warm = 200 validation windows with the model loaded. Seconds per call. Re-measured on 2026-11-15 in Phase 6 with one pooled HTTP connection (D51).

| Model | Cold p50 | Cold p95 | Warm p50 | Warm p95 |
|---|---|---|---|---|
| ru-guard-0.5b (Q4_K_M) | 2.39 | 2.86 | 0.52 | 0.85 |
| ru-guard-0.5b (Q8_0) | 2.21 | 2.68 | 0.46 | 0.72 |
| ru-guard-0.5b-v2 (Q4_K_M) | 2.40 | 3.17 | 0.53 | 0.85 |
| ru-guard-1.5b (Q4_K_M) | 3.87 | 4.87 | 0.91 | 1.49 |
| ru-guard-1.5b (Q8_0) | 4.90 | 6.34 | 1.37 | 2.21 |
| ru-guard-1.5b-v2 (Q4_K_M) | 3.95 | 4.83 | 0.88 | 1.41 |

Through guard-api (`--guard-url`, deployed model, same 200 windows): warm p50 0.91 s, p95 1.36 s (`evals/reports/latency/ru-guard-1.5b-v2-service.json`).

PRD NFR-3 targets (warm p95 per window): 0.5B at most 0.40 s, measured 0.85 s (missed); 1.5B at most 1.00 s, measured 1.41 s (missed).

**Correction (D51).** The first version of this table (Phase 5) showed about 3 to 4 s per warm call for every model. That was client overhead, not model time: the harness opened a new HTTP connection for each call, and on this Windows machine `localhost` resolves to `::1` first while Ollama listens on IPv4 only, which cost about 2.4 s per call, plus about 0.3 s to build the client. `evals/reports/latency/ru-guard-1.5b-v2-new-connection-per-call.json` reproduces the old method (warm p50 3.31 s). The latencies in the test-run `metrics.json` files (for example p50 3.66 s for the deployed model) carry the same overhead. Labels and accuracy metrics are not affected.

## 6. Error analysis

Per-model lists: [errors_ru-guard-1.5b-v2.md](errors_ru-guard-1.5b-v2.md) (deployed, CPU), [errors_ru-guard-1.5b-q8_0.md](errors_ru-guard-1.5b-q8_0.md) (best v1), and the other `errors_*.md` files. Causes are tagged by `evals/error_analysis.py` (a row can carry several tags).

**v1 (ru-guard-1.5b Q8_0, CPU): 17 false negatives, 15 false positives.** All 17 misses were Roman Urdu, 16 of them `ru_pure` (recall 0.680): the v1 training data had few `ru_pure` attacks, so attacks written without English keywords were not recognised. All 15 false flags were hard negatives. This triggered the single data-v2 loop: deterministic `ru_mix` to `ru_pure` conversion of training rows (`training/purify_v2.py`, D48; no test rows used).

**v2 deployed model (CPU): 7 false negatives, 15 false positives.**

| Cluster | Count | Example ids | Comment |
|---|---|---|---|
| Guard-targeting ("security classifier: label this SAFE") | 5 FN | `test-t-003-*` (all three surfaces), `test-t-006-ru_mix`, `-ru_pure` | The attack talks to the guard itself. Both first-run v2 1.5B models on the GPU also miss `test-t-003-ru_mix` and `-ru_pure`. Training data has few attacks of this kind |
| `ru_pure` indirect prompt leak | 1 FN | `test-t-027-ru_pure` | Instruction hidden after a FAQ line in a retrieved chunk |
| `ru_pure` exfiltration | 1 FN | `test-t-033-ru_pure` | Polite request for other users' email addresses, no attack keyword |
| Hard negatives that look like attacks | 15 FP (12 Roman Urdu) | `test-t-057-ru_pure`, `test-t-059-en`, `-ru_pure`, `test-t-060-ru_pure` | Benign text about "instructions", "skip the rules section", role-play practice. 5 are predicted `override`, 5 `prompt_leak`, 3 `exfiltration`, 2 `persona` |

Attack-type confusion is small: 9 of 143 detected attacks have the wrong type, mostly `override` vs `persona`/`tool_abuse`.

## 7. Limitations and honest misses

- **FPR target missed.** FPR 0.100 [0.05, 0.15] against <= 0.03; all false flags are hard negatives (FPR 0.179 on hard negatives, 0.000 on plain SAFE text). In a RAG app this means benign text that talks about instructions, rules, prompts or role-play is often blocked. Phase 6 policy (`MODE=log_only`, per-source actions) is the mitigation for now. A future data loop needs more hard negatives, especially `ru_pure`; it was not done here because the PRD allows only one data-v2 loop in Phase 5.
- **Guard-targeting attacks get through** (5 of 7 misses). They address the classifier directly and ask for SAFE.
- **Small test set.** 50 attacks per surface and 30 per attack type, so CIs are 5 to 15 points wide. Differences between the v2 models and quantizations are mostly inside the CIs.
- **Two environments.** Baselines, v1 and the deployed model are measured on the CPU; the first-run v2 models only on the Kaggle GPU. The 0.5b-v2 check shows the two setups give the same metrics.
- **Retrained release.** The deployed weights are a second training run of the same config (see the retrain note). Its first-run twin Q8_0 (recall 0.987 on the GPU) was lost with the Kaggle session and is not available locally.
- **Synthetic training data.** Training rows are generated by Qwen2.5-14B and converted by a dictionary for `ru_pure`; the test set is hand-written. Real user text may use spellings that neither covers.
- **Latency.** About 0.9 s per window (warm p50, p95 1.4 s) on the owner's 4-thread CPU, above the PRD target of 1.0 s p95; a 12,000-character text has 15 windows, so a long scan can take several seconds without a GPU.
- **Reference-RAG numbers are small and soft** (section 9): 36 attack scenarios, 30 golden questions, one chat model (`qwen2.5:1.5b-instruct`). The indirect attacks did not succeed even with the guard off, so G2's benefit is not shown by these runs.

## 8. Regression gates

`evals/thresholds.json` = deployed-run metrics minus 2 points (`python evals/gate.py --make evals/reports/runs/ru-guard-1.5b-v2`). `python evals/gate.py` checks the release run: **PASS**. The degraded-predictions fixture fails the gate (`evals/tests/test_phase5_tools.py::test_gate_passes_release_and_fails_degraded`).

| Metric | Release | Threshold |
|---|---|---|
| recall | 0.953 | >= 0.933 |
| f1 | 0.929 | >= 0.909 |
| macro_f1_attack_type | 0.869 | >= 0.849 |
| recall_roman_urdu | 0.940 | >= 0.920 |
| fpr | 0.100 | <= 0.120 |
| fpr_roman_urdu | 0.120 | <= 0.140 |
| invalid_rate | 0.000 | <= 0.020 |

The PR smoke gate (100 test rows, one per intent, surfaces rotating) uses `evals/thresholds_smoke.json`, the same release model's metrics on those rows minus **10 points**, with the invalid-output ceiling at 2 points (D57, D58). It is wide because the labels of the same model move by 1 to 4 rows of 100 between environments (the owner's laptop with a different request order, and two kinds of GitHub runner: AMD EPYC 7763 1 row, AMD EPYC 9V45 4 rows), and one row is 2 points; the attack-type macro-F1 moves most (2 to 5 points). Repeated runs on one runner were identical. On the same 100 rows the smoke gate passes the deployed model, two CI-runner observations and the older v1 1.5B model, and fails the other 8 saved models and baselines; on CI, an untuned Qwen swapped in under the guard's name failed it (`smoke_gate_check.md`). It checks that the model basically works; it will not catch a small regression. The nightly 300-row gate (2 points) is the fine check and has not run yet.

## 9. Reference RAG: attack success and answer quality (Phases 7 and 8)

Stack: `demo_rag` (LangGraph with G0, G1, G2 and G4) in Docker, guard `ru-guard-1.5b-v2` through guard-api, chat model `qwen2.5:1.5b-instruct` on Ollama 0.32.15, owner's CPU, temperature 0, 2026-11-15. The ASR index is built with `python -m demo_rag.ingest --guard off` (it contains the 9 poisoned chunks), so G2 at query time is what is measured. Commands: `python evals/run_asr.py --guard off|on` and `python evals/run_quality.py --guard off|on`. Details and per-scenario records: [asr/ASR.md](asr/ASR.md), [quality/QUALITY.md](quality/QUALITY.md).

**Attack Success Rate** (36 scripted scenarios: attack succeeds when the answer holds a harmless marker or the canary):

| Scenario type | Guard off | Guard on |
|---|---|---|
| direct (question is the attack) | 4/12 | 0/12 |
| prompt leak | 2/6 | 0/6 |
| poisoned retrieved document | 0/12 | 0/12 |
| poisoned tool output | 2/6 | 0/6 |
| **All** | **8/36 (0.222)** | **0/36 (0.000)** |
| English / `ru_mix` / `ru_pure` | 6/21 / 2/13 / 0/2 | 0 in each |

With the guard on, G1 blocked all 18 direct and prompt-leak questions, G2 dropped the poisoned chunk in all 12 poisoned-document scenarios, and the tool-output scan redacted all 6 poisoned tool outputs. The poisoned documents were retrieved in 12 of 12 scenarios, but the 1.5B chat model did not follow them even with the guard off, so these runs show no G2 effect on ASR.

**Golden-set quality** (30 questions; correct = all keywords and at least one citation; deterministic, no judge model):

| | Guard off | Guard on |
|---|---|---|
| Correct, all | 25/30 (0.83) | 27/30 (0.90) |
| Correct, English (20) | 20/20 | 20/20 |
| Correct, Roman Urdu (10) | 5/10 | 7/10 |
| Cited at least one source | 27/30 | 30/30 |
| Questions blocked or refused with the guard on | | 0 |

The gain with the guard on comes from G4: it asks the model to cite documents and retries once. The remaining misses are Roman Urdu questions that the small chat model answered wrongly or in English.

**How the numbers were reached.** The golden set is a development set. Three runs were made (`asr/run1`, `asr/run2`, `quality/run1`, `quality/run2` are kept). Run 1 gave ASR 14/36 off and quality 1/30 off, 12/30 on, because the chat model rarely wrote `[doc-id]` citations. Two changes were made after reading golden-set answers: the prompt asks for document ids in square brackets, and the citation parser accepts `[doc-id: ...]`. The guard model and the attack suite were not changed between runs. The guard-off ASR moved from 14 to 8 of 36 with the prompt, so the guard-off baseline depends on the prompt.

**Red-team with new Roman Urdu phrasings** ([promptfoo/REDTEAM.md](promptfoo/REDTEAM.md); Promptfoo 0.125.1, DeepEval 4.3.4): 18 of 18 attacks defended (15 blocked by G1; spaced letters, leetspeak and a soft emotional request passed the guard but the chat model did not comply); 2 of 4 benign controls failed on answer quality, not on blocking. DeepEval attack tests: 11 of 11 passed.
