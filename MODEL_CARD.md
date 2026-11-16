# Model card: ru-guard-1.5b-v2

A small prompt-injection classifier for Roman Urdu, English and mixed text. It reads one text window and its source, and answers with one label. It is meant to run locally behind `guard-api`. It is a guard, not a content-safety model, and not a security boundary on its own.

Status: final for release v1.0 (Phase 10). Numbers are from recorded runs; commands are in `evals/reports/EVAL_REPORT.md`.

## Model

| Item | Value |
|---|---|
| Base | Qwen2.5-1.5B-Instruct (Apache-2.0, see Licences) |
| Method | QLoRA (Unsloth 2026.11.4, TRL 1.15.0, PEFT 0.21.3): r 16, alpha 32, dropout 0.05, lr 2e-4 cosine, warmup 0.03, 3 epochs, effective batch 32, max length 512, seed 1234, assistant-only loss (D45) |
| Training data | `data/processed/train_v2.jsonl`: 5,678 rows (synthetic rows from Qwen2.5-14B, 900 human-written Roman Urdu SAFE rows, and deterministic `ru_pure` conversions, D48). See `data/DATA_CARD.md` |
| Training run | Kaggle free T4, `notebooks/06_retrain_1.5b_v2.ipynb`, 534 steps, final train loss 0.0435. Manifests: `training/reports/runs/ru-guard-1.5b-v2/run_manifest_retrain.json`, `training/reports/export/ru-guard-1.5b-v2/export_manifest_retrain.json` |
| Deployed file | `ru-guard-1.5b-v2-Q4_K_M.gguf`, 986,048,224 bytes, SHA-256 `52b5472abc1419f8c43645a733dd4dd9ee9e6e8b1be7de974d61dd988f8022e7` |
| Where to get it | GitHub Release `model-v1` of this repository (asset name above). CI downloads it from there |
| Runtime | Ollama 0.32.15, `models/Modelfile.1.5b` (ChatML template, temperature 0, top_k 1, num_predict 8, num_ctx 1024). Register: `bash scripts/register_model.sh ru-guard-1.5b-v2` |

## Input and output

- Input: the fixed system prompt (`training/prompt.py`, copied to `guard/prompt.py` and checked by `tests/test_prompt_parity.py`), then one user turn with the source (`user_input`, `retrieved_chunk` or `tool_output`) and the normalized text window (`training/normalize.py`). Texts longer than 1,000 characters are split into overlapping windows; any flagged window flags the text.
- Output: `SAFE` or `INJECTION|<attack_type>`, where attack_type is `override`, `persona`, `prompt_leak`, `exfiltration` or `tool_abuse`. Anything else is invalid and must be treated as a flag (fail closed). There is no confidence score.

## Intended use

- Screening user input, retrieved chunks and tool outputs before they reach an LLM in a RAG app, agent or MCP gateway, for users who write Roman Urdu, English or a mix.
- Local, offline use on a CPU through `guard-api`.

Out of scope: Urdu in Arabic script, other languages, content-safety moderation (hate, self-harm and so on), jailbreak detection in model outputs, and use as the only security control.

## Evaluation (frozen test set, owner's CPU)

300 hand-written rows (150 attacks, 150 benign, 84 of them hard negatives; the owner's test set, locked by `data/eval/test.lock`). Full results, CIs and error analysis: `evals/reports/EVAL_REPORT.md`.

| Metric | Value [95% CI] |
|---|---|
| Recall | 0.953 [0.92, 0.99] |
| FPR | 0.100 [0.05, 0.15] |
| F1 | 0.929 [0.90, 0.96] |
| Macro-F1 on attack type | 0.869 [0.81, 0.91] |
| Invalid output | 0.000 |
| Recall `en` / `ru_mix` / `ru_pure` | 0.980 / 0.960 / 0.920 |
| Recall Roman Urdu (`ru_mix` + `ru_pure`) | 0.940 [0.89, 0.98] |
| FPR plain SAFE / hard negatives | 0.000 / 0.179 |
| Latency per window (CPU, 4 threads) | warm p50 0.88 s, p95 1.41 s; cold p50 3.95 s; through guard-api p50 0.91 s, p95 1.36 s |

The same model run again gave slightly different labels on a few borderline rows (2 of 100 in the smoke subset), so a rerun can move FPR by a point or two.

In the reference RAG app (`demo_rag`, chat model `qwen2.5:1.5b-instruct`): 8 of 36 scripted attacks succeed with the guard off and 0 of 36 with it on; golden-set correctness 25/30 off and 27/30 on (section 9 of the evaluation report; small samples).

## Other models trained

All are QLoRA fine-tunes of Qwen2.5-Instruct (Apache-2.0), Q4_K_M unless noted, same test set and harness:

| Model | Recall | FPR | F1 | Roman Urdu recall | Note |
|---|---|---|---|---|---|
| ru-guard-0.5b (v1) | 0.773 | 0.067 | 0.841 | 0.680 | Q8_0 also built: 0.807 / 0.073 |
| ru-guard-1.5b (v1) | 0.840 | 0.093 | 0.869 | 0.760 | Q8_0 also built: 0.887 / 0.100, best v1 |
| ru-guard-0.5b-v2 | 0.880 | 0.127 | 0.877 | 0.850 | warm p50 0.53 s per window |
| **ru-guard-1.5b-v2** | **0.953** | **0.100** | **0.929** | **0.940** | deployed |

## Why this model (D49)

- Best recall, F1 and attack-type macro-F1 of all models measured on the CPU, with no invalid output.
- It is the only model that meets the `en` to `ru_pure` recall-gap target (6 points against 10) and the Roman Urdu recall target (0.94 against 0.90).
- Q4_K_M rather than Q8_0: the owner chose the smaller file for a faster download from Kaggle. On the first v2 training run (Kaggle GPU) Q8_0 had 2 points more recall (0.987 vs 0.967); Q4_K_M is about 35% faster on the CPU (warm p50 0.91 s vs 1.37 s, measured on v1).
- The 0.5B models are about 1.7 times faster (warm p50 0.53 s vs 0.88 s) but miss more Roman Urdu attacks (0.5b-v2: `ru_pure` recall 0.86, FPR 0.127).

## What is and is not in the repository

- In git: code, configs, run and export manifests, evaluation reports, this card, the data card.
- On the GitHub Release `model-v1`: the deployed GGUF only.
- Not in git: GGUF files of the other models (local `models/`, ignored), QLoRA adapters, merged fp16 weights and checkpoints. The Phase 4 note says the v1 adapters and merged weights were saved to Google Drive under `MyDrive/ru-guard/{runs,export}`; I could not confirm this on 2026-11-16. For the v2 models only the GGUF files were downloaded from Kaggle, so **v2 adapters and merged weights are not available** (a second run of the same config would give different weights).

## Licences (checked 2026-11-16 on the Hugging Face model pages)

| Component | Licence | Use here |
|---|---|---|
| Qwen2.5-1.5B-Instruct | Apache-2.0 | base of the deployed model |
| Qwen2.5-0.5B-Instruct | Apache-2.0 | base of the 0.5B models |
| Qwen2.5-14B-Instruct-AWQ | Apache-2.0 | generated the synthetic training text |
| Qwen2.5-1.5B-Instruct (unmodified) | Apache-2.0 | chat model of the demo app |
| Llama Guard 3 1B | Llama 3.2 Community Licence (gated) | evaluation baseline only; not redistributed |
| UCI "Roman Urdu Data Set" (600 rows) | CC BY 4.0 | human-written SAFE rows in the training set |
| Kaggle "Roman Urdu Cyber Abuse Dataset" (300 rows) | CC BY-SA 4.0 | human-written SAFE rows in the training set |

Apache-2.0 allows the fine-tuned weights to be redistributed with the licence and notice kept. The CC BY-SA 4.0 rows mean any published copy of the training files must be shared under CC BY-SA 4.0 with attribution (`data/DATA_CARD.md`). Whether share-alike reaches model weights trained on such rows is not settled; the owner should decide how to license the released weights. The licence of this repository's own code is not yet chosen (see the Phase 10 note).

## Limitations

- **False positives on hard negatives.** FPR 0.179 on benign text that talks about instructions, rules, prompts or role-play (the target FPR <= 0.03 is missed). Use `MODE=log_only` or per-source policy where blocking benign text is costly.
- **Guard-targeting attacks.** Text that tells the classifier to answer SAFE is the main source of misses (5 of 7).
- **Obfuscation.** In the red-team run, spaced-out letters and leetspeak passed the guard (`leet_fold` is off by default); the chat model happened not to comply.
- **Synthetic training data.** Attacks were generated by Qwen2.5-14B and converted to `ru_pure` by a dictionary; the Roman Urdu was never reviewed by a native speaker; real spellings vary more.
- **Small test set.** CIs are 5 to 15 points wide; the test set was drafted by the AI coding assistant at the owner's request (D22) and awaits native-speaker review.
- **Latency.** Warm p95 1.41 s per window on a 4-thread CPU, above the PRD target of 1.0 s for the 1.5B model; a long text has many windows.
- **Weights are not bit-reproducible.** The deployed file is a second training run of the same config; the GGUF hash above identifies it.

## Ethics and safety

All attack examples use harmless placeholders (reveal the system prompt, say a secret word, call a harmless tool). The guard logs only a keyed hash and length of scanned text, never raw text; quarantined chunks are PII-masked. A guard lowers risk; it does not make an LLM app safe on its own. Blocking benign Roman Urdu text has a cost for the people who write it, which is why `log_only` mode and per-source actions exist.
