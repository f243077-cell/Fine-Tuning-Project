# Data card: RU-Guard training data v1

Status: **two builds failed the 200-row review; nothing is approved for training.** v1 build `75482df3` (6,600 raw rows): 24% bad rows (D30). v2 build `f9fdcb8a` (stricter prompts, 8,000 raw rows; now in `data/processed/`): 30.5% bad rows (D34). In v2, English rows are 3% bad; Roman Urdu rows are 32% (`ru_mix`) and 40% (`ru_pure`) bad, mostly incoherent text. The sections below describe v1 unless marked v2.

## Purpose

Train a small classifier (Qwen2.5-0.5B/1.5B with QLoRA) to label text as `SAFE` or `INJECTION|<attack_type>`, given the text's source (`user_input`, `retrieved_chunk`, `tool_output`). The text can be English, mixed Roman Urdu (`ru_mix`), or mostly transliterated Urdu (`ru_pure`).

## Sources

| Set | Rows | How it was made | Used for |
|---|---|---|---|
| Seeds (`data/seeds/seeds.jsonl`) | 80 | Drafted by the AI coding assistant at the owner's request (D22); no native-speaker review yet | Few-shot examples in generation prompts only |
| Synthetic raw (`data/synthetic/`, gitignored) | 6,600 | Qwen2.5-14B-Instruct-AWQ, 4-bit, vLLM 0.33.0 on a free Colab T4 (D29; `training/generate_data.py`, `training/configs/generate.yaml`, repo commit `c5e15f7`); 1,518 generation calls, 2,612 s including model load | Input to the build |
| Train (`data/processed/train.jsonl`) | 4,004 | `training/build_dataset.py` | Fine-tuning |
| Validation (`data/processed/val.jsonl`) | 496 | Stratified held-out slice of the same build | Model selection only |
| Test (`data/eval/test.jsonl`) | 300 | Frozen and hash-locked (D22) | Never trained on; read by the build only to remove near-duplicates |

Generation library versions (from the manifest): vllm 0.33.0, torch 2.14.0, transformers 5.20.2, accelerate 1.15.0, pydantic 2.14.2, PyYAML 6.0.3; Python 3.13 on Colab.

A first attempt with Qwen2.5-7B-Instruct-AWQ was stopped after about 200 calls. It produced about 1.1 usable rows per call and often incoherent Roman Urdu. Those rows are not used; the partial output is kept on Drive at `ru-guard/synthetic_7b_partial` (D29).

## Generation design

- 63 cells: (5 attack types x 3 surfaces x 3 sources) for injection, plus (hard negative or plain x 3 surfaces x 3 sources) for safe.
- Planned mix: 50% injection (equal per attack type) and 50% safe. Hard negatives are half of the safe rows (25% of all rows). Surfaces are `en` 15%, `ru_mix` 45%, `ru_pure` 40%. Sources are `user_input` 50%, `retrieved_chunk` 25%, `tool_output` 25%.
- Each prompt asks for 5 examples. It includes:
  - 3 seeds of the same category (same language family first);
  - a source frame and a surface rule;
  - a Roman Urdu spelling style (to vary `kya/kia`, `nahi/nahin`, `hai/hy`);
  - two random topics;
  - for injection prompts only, benign placeholder payloads.
- Sampling: temperature 0.9, top_p 0.95, fixed per-call seeds derived from base seed 1234.

## Filters (in order) and drop counts

| Filter | Rule | Dropped |
|---|---|---|
| Schema | Pydantic `DataRow` | 0 |
| Length | 15 to 1,000 normalized characters (one window) | 1 |
| Safety denylist | `training/configs/denylist.yaml` (weapons, malware, drugs, self-harm terms) | 0 |
| Language mix | Share of Roman Urdu and English function words must match the surface label; no non-Latin script (thresholds in `training/configs/build.yaml`) | 382 |
| Exact duplicate | Same normalized text | 1 |
| Leakage | Character 5-gram Jaccard 0.5 or higher with any seed or test row | 33 |
| Near duplicate | Character 5-gram Jaccard 0.8 or higher with an earlier kept row | 4 |
| Balance | Downsample to 50/50 injection/safe and the hard-negative share; cap at 4,500 | 1,679 |

Clean rows before balancing: 6,179. Maximum Jaccard of any kept row: 0.446 against the test set, 0.496 against the seeds.

## Counts

| | Train | Val |
|---|---|---|
| Rows | 4,004 | 496 |
| INJECTION / SAFE | 2,003 / 2,001 | 247 / 249 |
| Hard negatives | 1,001 | 124 |
| override / persona / prompt_leak / exfiltration / tool_abuse | 402 / 414 / 388 / 405 / 394 | 50 / 53 / 47 / 50 / 47 |
| en / ru_mix / ru_pure | 629 / 1,776 / 1,599 | 79 / 218 / 199 |
| user_input / retrieved_chunk / tool_output | 2,042 / 1,067 / 895 | 254 / 131 / 111 |

Counts per cell: `train.cells` and `val.cells` in `data/processed/build_report.json`.

## Human review

200 random rows (`data/review/review_sample.csv`, seed 1234). The review was done by the AI coding assistant at the owner's request, not by a native speaker (D30).

`python scripts/apply_review.py data/review/review_sample.csv --dry-run` (2026-11-13): 152 keep, 3 fix, 45 drop. Bad-row rate 24% (target 10% or less; above 15% means regenerate). The review was **not applied**.
- Injection rows: 33 of 101 bad. Safe rows: 15 of 99 bad.
- Causes (see the `notes` column): incoherent text (25 rows); requests that are not clearly injections, or harmless role-play (15); other (8: label leak, wrong language, non-benign payload, wrong attack type, benign requests labeled as injection).
- Not counted: many rows flagged `hard_negative` contain no attack-like word. The flag is metadata and does not change the training target.

## Token lengths

Qwen2.5 tokenizer, full chat (system + user + label) against `max_seq_len` 512 (`scripts/token_report.py`, 2026-11-13):
- Train: maximum 244 tokens, p95 143. Validation: maximum 176, p95 142.
- Worst-case 1,000-character window: 291 tokens built from train/val text, and 428 tokens built from the seeds. `WINDOW_CHARS` stays at 1,000.

## Dataset hash

Build (before review): `75482df3c6491016a14908affcafa73d3df12b075377d2abb2226b09321a361c`. That hash covers:
- train `b239cc814494438efee3a2f56e7a7c033c7bf2a5ffb7420e13029e7f5e2963b3`;
- val `b73cb58a0f84b65142e8e071b111848572d1b5ce07133612224c361b5739b8b7`.

The dataset v1 hash (after the review is applied) is recorded here at Gate 2.

## Known limits

- All text is synthetic or AI-drafted, and no row has been written by a native speaker. The 200-row review is the only human check.
- A spot check before the review found:
  - frequent grammar errors and some odd phrasing in Roman Urdu;
  - many hard negatives that do not contain the attack-like trigger words they were meant to have;
  - a narrow payload vocabulary (many override rows use "Theek hai").
- The seeds and the test set were written by the same author (D22). The leakage filter removes near-copies, but shared attack *patterns* remain by design.
- The language-mix filter is a word-list heuristic. It can drop valid rows that use rare spellings, and it can keep rows whose label is borderline. One of the 80 seeds (an all-English booking confirmation labeled `ru_mix`) fails it.
- Payloads are placeholders (secret words, `example.com`, fictional tools). The model learns the structure of an instruction aimed at an AI, not harmful topics.

## v2 build (2026-11-13)

- Generation: 8,000 rows, Qwen2.5-14B-Instruct-AWQ, stricter prompts (D31), commit `76653c9`, 3,781 s on a Colab T4. The judge pass was disabled as unreliable (D32, D33).
- `python -m training.build_dataset --config training/configs/build.yaml`:
  - Dropped: language mix 461, denylist 2, leakage 32, near duplicate 5, balance cap 3,000.
  - Relabeled: 586 hard negatives without a trigger word became plain SAFE.
  - Result: 4,000 train and 500 val rows. Maximum Jaccard 0.464 against the test set, 0.492 against the seeds.
  - Hashes: train `8377a074...`, val `7f625cea...`, dataset `f9fdcb8aeb095bd5beba98d6fa98aa750c5fe7f495b3562f6fb310fbc074352c`.
- Token check: largest 291 tokens (fits 512).
- AI review of 200 rows (`data/review/review_sample.csv`): 139 keep, 61 drop, 30.5%. Not applied.
