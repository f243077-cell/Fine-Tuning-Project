# Data card: RU-Guard training data v1

Status: **dataset not built yet.** Generation on Colab has not been run. Every number marked "not run" is filled in from `data/processed/build_report.json` and `data/processed/review_report.json` after the real runs.

## Purpose

Train a small classifier (Qwen2.5-0.5B/1.5B with QLoRA) to label text as `SAFE` or `INJECTION|<attack_type>`, given the text's source (`user_input`, `retrieved_chunk`, `tool_output`). The text can be English, mixed Roman Urdu (`ru_mix`), or mostly transliterated Urdu (`ru_pure`).

## Sources

| Set | Rows | How it was made | Used for |
|---|---|---|---|
| Seeds (`data/seeds/seeds.jsonl`) | 80 | Drafted by the AI coding assistant at the owner's request (D22); no native-speaker review yet | Few-shot examples in generation prompts only |
| Synthetic raw (`data/synthetic/`, gitignored) | target 6,600; actual: not run | Qwen2.5-7B-Instruct, 4-bit (`training/generate_data.py`, `training/configs/generate.yaml`) on free Colab | Input to the build |
| Train (`data/processed/train.jsonl`) | target about 4,000; actual: not run | `training/build_dataset.py` | Fine-tuning |
| Validation (`data/processed/val.jsonl`) | target about 500; actual: not run | Stratified held-out slice of the same build | Model selection only |
| Test (`data/eval/test.jsonl`) | 300 | Frozen and hash-locked (D22) | Never trained on; read by the build only to remove near-duplicates |

Generation model and library versions: not run (copied from `data/synthetic/manifest.json`).

## Generation design

- 63 cells: (5 attack types x 3 surfaces x 3 sources) for injection, plus (hard negative or plain x 3 surfaces x 3 sources) for safe.
- Planned mix: 50% injection (equal per attack type) and 50% safe. Hard negatives are half of the safe rows (25% of all rows). Surfaces are `en` 15%, `ru_mix` 45%, `ru_pure` 40%. Sources are `user_input` 50%, `retrieved_chunk` 25%, `tool_output` 25%.
- Each prompt asks for 5 examples. It includes 3 seeds of the same category, a source frame, a surface rule, a Roman Urdu spelling style (to vary `kya/kia`, `nahi/nahin`, `hai/hy`), and two random topics. Injection prompts also include benign placeholder payloads.
- Sampling: temperature 0.9, top_p 0.95, fixed per-call seeds derived from base seed 1234.

## Filters (in order) and drop counts

| Filter | Rule | Dropped |
|---|---|---|
| Schema | Pydantic `DataRow` | not run |
| Length | 15 to 1,000 normalized characters (one window) | not run |
| Safety denylist | `training/configs/denylist.yaml` (weapons, malware, drugs, self-harm terms) | not run |
| Language mix | Share of Roman Urdu and English function words must match the surface label; no non-Latin script (thresholds in `training/configs/build.yaml`) | not run |
| Exact duplicate | Same normalized text | not run |
| Leakage | Character 5-gram Jaccard 0.5 or higher with any seed or test row | not run |
| Near duplicate | Character 5-gram Jaccard 0.8 or higher with an earlier kept row | not run |
| Balance | Downsample to 50/50 injection/safe and the hard-negative share; cap at 4,500 | not run |

Maximum Jaccard of any kept row against the test set: not run. Against the seeds: not run.

## Counts per cell

Not run. The full counts are in `data/processed/build_report.json` (`train.cells`, `val.cells`).

## Human review

200 random rows reviewed by the owner (`data/review/review_sample.csv`). Bad-row rate (fix + drop): not run. Target: 10% or less.

## Token lengths

Qwen2.5 tokenizer, full chat (system + user + label) against `max_seq_len` 512 (`scripts/token_report.py`):
- Seeds: maximum 131 tokens, p95 128 (run on 2026-11-13).
- Worst-case 1,000-character window: 428 tokens for both the 0.5B and 1.5B tokenizers (run on 2026-11-13). `WINDOW_CHARS` stays at 1,000.
- Train and validation: not run.

## Dataset hash

Not run. `sha256.dataset` in `build_report.json` (or in `review_report.json` after the review is applied) is recorded here at Gate 2.

## Known limits

- All text is synthetic or AI-drafted. No row has been written by a native speaker. The 200-row review is the only human check.
- The seeds and the test set were written by the same author (D22). The leakage filter removes near-copies, but shared attack *patterns* remain by design.
- The language-mix filter is a word-list heuristic. It can drop valid rows that use rare spellings, and it can keep rows whose label is borderline. One of the 80 seeds (an all-English booking confirmation labeled `ru_mix`) fails it.
- Payloads are placeholders (secret words, `example.com`, fictional tools). The model learns the structure of an instruction aimed at an AI, not harmful topics.
