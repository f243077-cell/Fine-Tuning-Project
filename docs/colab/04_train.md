# Colab step 04: QLoRA fine-tuning and GGUF export

**Goal:**
- Train `ru-guard-0.5b` and `ru-guard-1.5b` with QLoRA on dataset v1.1 (4,378 train and 548 val rows, committed in the repo).
- Run three short ablations on the 0.5B model.
- Export each final model to GGUF (Q4_K_M and Q8_0).

**You need:**
- A free Colab session with a **T4 GPU**. If the Colab GPU quota has run out, use Kaggle instead; see the Kaggle section below (D39).
- About 8 GB of free space on Google Drive.
- No Hugging Face token: the Qwen2.5 models are public.

**Output on Drive (`MyDrive/ru-guard/`):**
- `runs/<run_name>/`:
  - `adapter/`: the LoRA adapter and tokenizer;
  - `checkpoints/checkpoint-<step>/`: one checkpoint per epoch;
  - `train_log.csv`, `val_metrics.csv` and `run_manifest.json`.
- `export/<name>/`:
  - `merged/`: fp16 weights;
  - `gguf/<name>-Q4_K_M.gguf` and `gguf/<name>-Q8_0.gguf`;
  - `export_manifest.json`.

Checkpoints are written at the end of every epoch. If the session drops, the same command resumes from the last saved epoch.

## Fastest path: the notebook

Open `notebooks/04_train.ipynb` from GitHub. In Colab: File, then Open notebook, then GitHub. In Kaggle: File, then Import Notebook, then GitHub. Choose the T4 GPU, then Run all. The notebook runs the cells below in the same order. Every step is skipped when its output already exists, so after a disconnect, just Run all again.

## Cells (paste in order)

**1. Runtime.** Runtime, then Change runtime type, then **T4 GPU**. Then:
```python
!nvidia-smi --query-gpu=name,memory.total --format=csv
```
Expected output: `Tesla T4, 15360 MiB` (or similar).

**2. Mount Drive.**
```python
from google.colab import drive
drive.mount('/content/drive')
RUNS = "/content/drive/MyDrive/ru-guard/runs"
EXPORT = "/content/drive/MyDrive/ru-guard/export"
```

**3. Get the code.**
```python
!git clone https://github.com/f243077-cell/Fine-Tuning-Project.git /content/ru-guard
%cd /content/ru-guard
!git log --oneline -1
```

**4. Install the training stack.** This takes a few minutes. These are the versions the code was checked against: Unsloth 2026.11.4 requires `trl<=1.15.0` and `transformers<=5.17.0`. Pip may print warnings about conflicts with other Colab packages. You can ignore them if cell 5 works.
```python
!pip install -q "unsloth==2026.11.4" "unsloth_zoo==2026.11.4" "trl==1.15.0" "transformers==5.17.0" "peft==0.21.3" pyyaml
!pip list 2>/dev/null | grep -iE "^(unsloth|unsloth.zoo|trl|transformers|peft|torch|bitsandbytes|datasets) "
```
Copy the printed version list. It goes into `requirements-train.txt`.

**5. Dry run** (tokenizer only, about 1 minute).
```python
!python -m training.train_qlora --config training/configs/qwen2.5-0.5b.yaml --dry-run
```
Expected: `train_rows 4378`, `train_dropped_long 0`, `optimizer_steps 411`, `trained_part_of_example "SAFE<|im_end|>"` (or an INJECTION label).

**6. Train ru-guard-0.5b** (main run).
```python
!python -m training.train_qlora --config training/configs/qwen2.5-0.5b.yaml --out {RUNS}
```
The log prints the loss every 10 steps. At the end of each epoch it prints `val_gen epoch N: {...}`, with generation-based macro-F1, recall, FPR and invalid rate on 200 val rows. At the end it prints `adapter saved to ...`.

**7. Ablations (0.5B only, time-boxed).** Run them in this order. Each run is a separate folder, and each one resumes like cell 6. If time runs out, skip the rest and note which ones did not run.
```python
!python -m training.train_qlora --config training/configs/qwen2.5-0.5b.yaml --out {RUNS} --set run_name=ru-guard-0.5b-r8 --set lora.r=8 --set lora.alpha=16
!python -m training.train_qlora --config training/configs/qwen2.5-0.5b.yaml --out {RUNS} --set run_name=ru-guard-0.5b-no-en --set data.include_en=false
!python -m training.train_qlora --config training/configs/qwen2.5-0.5b.yaml --out {RUNS} --set run_name=ru-guard-0.5b-2ep --set train.epochs=2
```

**8. Train ru-guard-1.5b.**
```python
!python -m training.train_qlora --config training/configs/qwen2.5-1.5b.yaml --out {RUNS}
```

**9. Export both models.** The first export builds llama.cpp, which takes about 10 minutes. The script first runs 5 sanity prompts and refuses to export if any output is not a valid label.
```python
!python -m training.merge_and_export --adapter {RUNS}/ru-guard-0.5b/adapter --name ru-guard-0.5b --out {EXPORT}
!python -m training.merge_and_export --adapter {RUNS}/ru-guard-1.5b/adapter --name ru-guard-1.5b --out {EXPORT}
!ls -lh {EXPORT}/*/gguf/
```
Expected: four `.gguf` files. Q4_K_M is about 0.4 GB for 0.5B and 1.0 GB for 1.5B; Q8_0 is about twice that. These sizes are estimates.

**10. Pack the small logs** (to bring back to the repo).
```python
!cd /content/drive/MyDrive/ru-guard && zip -qr train_logs.zip runs/*/train_log.csv runs/*/val_metrics.csv runs/*/run_manifest.json export/*/export_manifest.json && ls -lh train_logs.zip
```

## What to bring back

| File on Drive | Local path |
|---|---|
| `export/ru-guard-0.5b/gguf/ru-guard-0.5b-Q4_K_M.gguf` and `-Q8_0.gguf` | `models/` |
| `export/ru-guard-1.5b/gguf/ru-guard-1.5b-Q4_K_M.gguf` and `-Q8_0.gguf` | `models/` |
| `train_logs.zip` | unzip into `training/reports/` (gives `training/reports/runs/...` and `training/reports/export/...`) |
| The pip version list from cell 4 | paste into chat |

GGUF files are gitignored and never committed. Adapters and merged weights stay on Drive, which is the backup that Gate 4 checks.

Then, locally (Claude does this):
```bash
bash scripts/register_model.sh ru-guard-0.5b && bash scripts/register_model.sh ru-guard-0.5b q8_0
bash scripts/register_model.sh ru-guard-1.5b && bash scripts/register_model.sh ru-guard-1.5b q8_0
python scripts/smoke_ollama_model.py --model ru-guard-0.5b --tokenizer Qwen/Qwen2.5-0.5B-Instruct
python scripts/plot_training.py training/reports/runs/ru-guard-0.5b* --out docs/figures/training_0.5b.png
```

## Expected runtime (estimates, not measured)

| Step | Estimate |
|---|---|
| ru-guard-0.5b, 3 epochs (411 steps) | 20 to 40 min |
| Each 0.5B ablation | 15 to 40 min |
| ru-guard-1.5b, 3 epochs | 45 to 90 min |
| Export, each model | 10 to 20 min (the first one includes the llama.cpp build) |

That is about 3 to 5 hours in total. It is fine to spread the work over several sessions.

## If the session disconnects

1. Reconnect and choose a T4 GPU again. Then run cells 2, 3 and 4.
2. Run the same training command again. It prints `resume from: .../checkpoint-<step>` and continues from the last finished epoch. Work inside a half-finished epoch is lost, so expect at most about 15 minutes of lost work on the 1.5B model.
3. `train_log.csv` can repeat a few steps after a resume. `scripts/plot_training.py` keeps the last row for each step.
4. If an export stopped halfway, run the export command again. It writes the same files again.

## Kaggle instead of Colab (free tier only, D39)

1. Create a new notebook. In Settings, choose Accelerator **GPU T4 x2** and turn Internet **on**. Use only free features.
2. Skip cell 2 and set the output folders instead. Also select one GPU, because Unsloth trains on one:
   ```python
   import os; os.environ["CUDA_VISIBLE_DEVICES"] = "0"
   RUNS = "/kaggle/working/runs"; EXPORT = "/kaggle/working/export"
   ```
3. In cell 3, clone into `/kaggle/working/ru-guard` and `%cd` there.
4. Run cells 4 to 10 as written. A long command must stay in the foreground: `!cmd &` fails on Kaggle with "Background processes not supported".
5. `/kaggle/working` is lost when the session ends. Before you stop, download the files listed in "What to bring back" from the Output panel. To keep a checkpoint between sessions, use "Save Version" (Quick Save). Then add the saved output as an input of the next session and copy `runs/` back into `/kaggle/working/` before you resume.

## If something fails

- **`CUDA out of memory` on the 1.5B model:** add `--set train.per_device_batch=2 --set train.grad_accum=16`. The effective batch is still 32.
- **Pip conflict and cell 5 fails on an import:** bring back the full error text. Do not upgrade packages by guesswork.
- **`label mask is wrong`:** the tokenizer splits the prompt differently than expected. Stop and bring back the printed line.
- **Export sanity check fails** (`BAD` lines): do not export. Bring back the printed lines and `val_metrics.csv` for that run.
