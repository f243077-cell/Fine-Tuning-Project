# Phase 4: QLoRA fine-tuning and export

Branch / commit: `main`. Status: **done, stopped at Gate 4 (2026-11-14).**

## Done
- `training/configs/qwen2.5-0.5b.yaml` and `qwen2.5-1.5b.yaml`: starting values from PRD section 11 (r 16, alpha 32, dropout 0.05, 7 projection modules, lr 2e-4 cosine, 3% warmup, 3 epochs, effective batch 32, max_seq_len 512, fp16, seed 1234). The 1.5B model uses batch 4 x 8 instead of 8 x 4.
- `training/train_qlora.py`:
  - Unsloth 4-bit loading, LoRA, and TRL `SFTTrainer`.
  - Data is pre-tokenized with the shared ChatML prompt, with `-100` labels on the prompt (D45), and the mask is checked again at run start.
  - Eval and a checkpoint at every epoch, resume from the latest checkpoint, and plain CSV logs.
  - `run_manifest.json` records the config, data hashes, git commit, versions and GPU. `--set` overrides drive the ablations.
  - `--dry-run` works on CPU.
- `training/val_metrics.py`: generation-based recall, FPR, invalid rate, and macro-F1 over 6 labels, run on a fixed 200-row val subset at each epoch end.
- `training/merge_and_export.py`: 5 sanity prompts (export stops on any invalid output), the merged fp16 model, GGUF Q4_K_M and Q8_0 renamed to `<name>-<QUANT>.gguf`, and a manifest with SHA-256 hashes.
- `models/Modelfile.0.5b` and `models/Modelfile.1.5b`, `scripts/register_model.sh` (Q4_K_M as `<name>`, Q8_0 as `<name>:q8_0`), and `scripts/smoke_ollama_model.py`. The smoke script runs 20 val prompts and checks grammar plus live template token counts.
- `training/tests/test_template_parity.py`: the training prompt, the Modelfile template, and the Qwen2.5 0.5B and 1.5B tokenizer chat templates all render the same strings.
- `scripts/plot_training.py`: loss, val macro-F1, and val recall/FPR curves.
- `docs/colab/04_train.md`: Colab cells, Kaggle variant, resume steps, and what to bring back.

## Numbers (local, real runs)
- Dry run on dataset v1.1: 4,378 train and 548 val rows, 0 dropped for length.
- Tokens per row: p50 117, max 217.
- 411 optimizer steps for 3 epochs. With `include_en=false`: 3,855 rows and 363 steps.
- Live template check on Ollama 0.32.15 (temporary model built from `qwen2.5:1.5b-instruct`): `prompt_eval_count` equals the tokenizer count on 3 of 3 prompts.
- Tests: 145 passed.
- Tests: 148 passed (after the notebook and export changes).

## GPU run (2026-11-14, Colab free T4, commit `4ce9326`, `notebooks/04_train.ipynb`)
Stack confirmed by the run: Unsloth 2026.11.4, TRL 1.15.0, transformers 5.17.0, PEFT 0.21.3, torch 2.14.1+cu130, bitsandbytes 0.50.2, datasets 4.8.5, Python 3.13.16. Logs and manifests are in `training/reports/`. Curves: `docs/figures/training_0.5b_vs_1.5b.png` and `docs/figures/training_0.5b_ablations.png`.

Val numbers are on the fixed 200-row val subset (92 INJECTION, 108 SAFE), final epoch. Val rows are synthetic like the train rows, so these are not test-set results.

| Run | Train time | Train loss | Val recall | Val FPR | Val macro-F1 | Invalid | Peak GPU |
|---|---|---|---|---|---|---|---|
| ru-guard-0.5b | 578 s | 0.065 | 1.000 | 0.028 | 0.985 | 0.000 | 1.02 GB |
| ru-guard-1.5b | 1,588 s | 0.040 | 0.957 | 0.009 | 0.973 | 0.000 | 2.50 GB |
| 0.5b, r 8 | 568 s | 0.077 | 0.967 | 0.028 | 0.960 | 0.000 | 0.98 GB |
| 0.5b, no `en` (3,855 rows) | 495 s | 0.071 | 0.957 | 0.019 | 0.969 | 0.000 | 1.04 GB |
| 0.5b, 2 epochs | 380 s | 0.093 | 0.957 | 0.019 | 0.968 | 0.000 | 1.02 GB |

- No ablation beats the default (D46). The 1.5B model was best at epoch 2 (macro-F1 0.984, FPR 0.009); the epoch-3 adapter is the one exported.
- Export: 5 of 5 sanity prompts were valid and correct for both models.

GGUF files (in `models/`, gitignored). The SHA-256 of each downloaded copy matches its export manifest.

| File | Size | SHA-256 (prefix) |
|---|---|---|
| ru-guard-0.5b-Q4_K_M.gguf | 398 MB | 89188129904a |
| ru-guard-0.5b-Q8_0.gguf | 531 MB | 2949c1383529 |
| ru-guard-1.5b-Q4_K_M.gguf | 986 MB | c4a1819e5258 |
| ru-guard-1.5b-Q8_0.gguf | 1,647 MB | e9c886f15891 |

Ollama smoke check (`scripts/smoke_ollama_model.py`, 20 val prompts, Ollama 0.32.15, CPU):

| Model | Valid labels | Template token mismatches | Exact match |
|---|---|---|---|
| ru-guard-0.5b (Q4_K_M) | **19 / 20** | 0 | 0.90 |
| ru-guard-0.5b:q8_0 | **19 / 20** | 0 | 0.90 |
| ru-guard-1.5b (Q4_K_M) | 20 / 20 | 0 | 0.95 |
| ru-guard-1.5b:q8_0 | 20 / 20 | 0 | 0.95 |

## Open issues
- **0.5B misses the "valid label on 20 prompts" acceptance check by one row.** For val row `syn-inj-tool_abuse-en-user_input-00237-ru_mix`, the model emits `tool_abuse` without the `INJECTION|` prefix.
  - Raw `/api/generate` with the exact training prompt gives the same 4 tokens, in both Q4_K_M and Q8_0. It is model behaviour, not the template or quantization.
  - Under D43 it counts as a flag, and the row is an injection, so it is caught.
  - Phase 5 measures the invalid rate on the test set against the 1% target.
- The Kaggle cross-check of the ablations was not kept (session stopped to save quota). Colab holds every log.
- Adapters, merged fp16 weights, checkpoints and GGUF files stay on Drive under `MyDrive/ru-guard/{runs,export}`.
- No diagrams in `docs/understanding/` became stale.

## Gate 4
The owner confirms that the artifacts exist locally (`models/*.gguf`, registered in Ollama) and are backed up on Drive. Then the owner decides whether the 0.5B one-row invalid output is acceptable for Phase 5, or whether it needs a fix first.
