# Phase 4: QLoRA fine-tuning and export

Branch / commit: `main`. Status: **code done; waiting on the owner's GPU run ([HUMAN], `docs/colab/04_train.md`).**

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
- Training metrics: **not run** (GPU step pending).

## Open issues
- The training stack was checked from package source, not from a run: Unsloth 2026.11.4, TRL 1.15.0, transformers 5.17.0, PEFT 0.21.3. Pin the versions in `requirements-train.txt` after the Colab run.
- Ablations (r 8 vs 16, with and without `en`, 2 vs 3 epochs) are prepared as commands in the runbook but not yet run.
- No diagrams in `docs/understanding/` became stale.

## Next ([HUMAN])
1. The owner runs `docs/colab/04_train.md` cells 1 to 10 and brings back the GGUF files and `train_logs.zip`.
2. Claude then:
   - registers the models;
   - runs `scripts/smoke_ollama_model.py` on all 4 models;
   - plots the curves;
   - pins the versions;
   - writes the ablation results.
3. Claude stops at Gate 4.
