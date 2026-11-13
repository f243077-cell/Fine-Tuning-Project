# Colab step 02: generate synthetic training data

**Goal:** generate about 6,600 raw labeled rows with Qwen2.5-14B-Instruct-AWQ (4-bit, D29) from the seeds. `training/build_dataset.py` then filters them down to about 4,000 train rows and 500 validation rows on your local machine.

**You need:** a Google account, a free Colab session with a **T4 GPU**, and about 2 GB of free space on Google Drive. No Hugging Face token is needed, because the Qwen models are public.

**Output on Drive:** `MyDrive/ru-guard/synthetic/`, which contains:
- `shards/*.jsonl`: one file per cell, 63 files.
- `state.json`: the resume state.
- `manifest.json`: the model, library versions, config hash, and row counts.

The script writes after every batch, so a disconnect loses at most one batch.

## Cells (paste in order)

**1. Runtime.** Open a new notebook. Choose Runtime, then Change runtime type, then **T4 GPU**. Then check the GPU:
```python
!nvidia-smi --query-gpu=name,memory.total --format=csv
```
Expected output: `Tesla T4, 15360 MiB` (or similar).

**2. Mount Drive.**
```python
from google.colab import drive
drive.mount('/content/drive')
```

**3. Get the code.**
```python
!git clone https://github.com/f243077-cell/Fine-Tuning-Project.git /content/ru-guard
%cd /content/ru-guard
!git log --oneline -1
```

**4. Install vLLM** (first choice). This takes a few minutes. Pip may print warnings about dependency conflicts with Colab packages. You can ignore those warnings if the next cell works.
```python
!pip install -q vllm pyyaml
```

**5. Preview the prompts** (optional, no GPU work). This prints the first prompt.
```python
!python -m training.generate_data --config training/configs/generate.yaml --out /content/preview --dry-run --preview 4
!head -n 20 /content/preview/prompts_preview.txt
```

**6. Smoke test** (8 calls, about 40 rows). The first run downloads the model, which is about 10 GB.
```python
OUT = "/content/drive/MyDrive/ru-guard/synthetic"
!python -m training.generate_data --config training/configs/generate.yaml --out {OUT} --max-calls 8
!for f in $(ls {OUT}/shards/*.jsonl | head -3); do head -n 2 "$f"; done
```
Read the rows that are printed. Each row must be one example in the requested language, not a list or an explanation. If the rows look wrong, stop and bring back the printed output.

**7. Full run.** This command continues from the smoke test; it does not start again.
```python
!python -m training.generate_data --config training/configs/generate.yaml --out {OUT}
```
The log prints `calls N, rows M / 6600` after each batch. At the end, the log prints `done: ... rows` and `manifest.json` is written. If the log shows `cells below target`, note which cells and bring back the log line.

**7b. Judge pass (D31).** Rates each row (coherence and label fit) with the same model and writes `judgements.jsonl` next to the shards. It resumes like generation.
```python
!python -m training.judge_data --config training/configs/generate.yaml --out {OUT}
```

**8. Pack the output.**
```python
!cd /content/drive/MyDrive/ru-guard && zip -qr synthetic.zip synthetic && ls -lh synthetic.zip
```

## If vLLM does not work on the T4

vLLM can fail in cell 4 (install error), in cell 6 (`CUDA`, `out of memory`, `quantization`, or `compute capability` errors), or the run can freeze. Try these steps in order:

1. **Out of memory during CUDA graph capture:** run `!sed -i 's/vllm_enforce_eager: false/vllm_enforce_eager: true/' training/configs/generate.yaml`, then repeat cell 6.
2. **The error mentions AWQ or quantization:** run `!sed -i 's/vllm_quantization: awq/vllm_quantization: null/' training/configs/generate.yaml` and repeat cell 6.
3. **Still failing: use the Transformers + bitsandbytes fallback.** Restart the runtime (Runtime, then Restart session). Then run cells 2 and 3, then:
   ```python
   !pip install -q bitsandbytes pyyaml
   OUT = "/content/drive/MyDrive/ru-guard/synthetic_hf"
   !python -m training.generate_data --config training/configs/generate.yaml --out {OUT} --backend hf --max-calls 4
   ```
   If the smoke rows look right, run the same command without `--max-calls`. Use the new folder `synthetic_hf`, so that the rows from the two backends do not mix. In cell 8, zip `synthetic_hf` instead.

## Expected runtime (estimates, not measured)

- vLLM: roughly 30 to 90 minutes for 6,600 rows on a T4, plus the model download.
- Transformers fallback: several hours. It will probably need two or more Colab sessions. That is fine, because the run resumes.

## If the session disconnects

Reconnect with a T4 GPU, then run cells 2, 3, and 4 (or the fallback install). Then run cell 7 again with the **same** `OUT` folder. The script counts the rows already in each shard and continues. It never deletes or rewrites rows that already exist.

## What to bring back

1. Download `MyDrive/ru-guard/synthetic.zip` (or `synthetic_hf.zip`).
2. Unzip it into the repo so that the files end up at:
   - `data/synthetic/shards/*.jsonl`
   - `data/synthetic/manifest.json`
   - `data/synthetic/state.json`

   `data/synthetic/` is gitignored, so these files are not committed. Only the processed train/val files and the report are committed.
3. Tell Claude Code "synthetic data is in data/synthetic". It then runs these steps locally:
   ```bash
   python -m training.build_dataset --config training/configs/build.yaml
   python scripts/token_report.py data/processed/train.jsonl data/processed/val.jsonl
   python scripts/sample_for_review.py --n 200
   ```
   It also pins the versions from `manifest.json` in `requirements-train.txt` and fills in `data/DATA_CARD.md`.
4. **Your review (Gate 2):** open `data/review/review_sample.csv` in a spreadsheet. For every row, set `decision` to `keep`, `fix`, or `drop`.
   - For `fix`, fill only the `fixed_*` columns that change: `fixed_text`, `fixed_label` (SAFE or INJECTION), `fixed_attack_type`, `fixed_surface`, or `fixed_hard_negative` (true or false).
   - Save the file as CSV UTF-8. Then run:
   ```bash
   python scripts/apply_review.py data/review/review_sample.csv --dry-run   # shows the bad-row rate
   python scripts/apply_review.py data/review/review_sample.csv             # applies it
   ```
   The target is a bad-row rate of 10% or less. Between 10% and 15%, look at what went wrong. Above 15%, the prompts are improved and the data is regenerated.

## v3 pipeline: English first, then translate (D35)

Use this instead of cells 6 to 7b. Run cells 1 to 4 first.
```python
EN = "/content/drive/MyDrive/ru-guard/en_v3"
OUT = "/content/drive/MyDrive/ru-guard/synthetic_v3"
!nohup bash -c "python -m training.generate_data --config training/configs/generate_en.yaml --out {EN} && python -m training.translate_data --config training/configs/generate_en.yaml --in {EN} --out {OUT}" > /content/drive/MyDrive/ru-guard/gen_v3.log 2>&1 &
```
- Generation writes 7,000 English rows to `en_v3/shards/`.
- Translation keeps about 15% of them as English and translates the rest into `ru_mix` or `ru_pure`. It writes `synthetic_v3/shards/rows.jsonl` and `progress.jsonl`.
- Both steps resume after a disconnect if you run the same command again.
- Bring back `synthetic_v3/` and unzip it so that `data/synthetic/shards/rows.jsonl` exists.
