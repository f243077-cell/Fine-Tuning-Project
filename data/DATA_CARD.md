# Data card: RU-Guard training data v1

Status: **Dataset v1 is approved (Gate 2, D41).** It is the v3.2 build (en and `ru_mix` only, D38) with its 200-row review applied: 3,977 train and 499 val rows in `data/processed/`, dataset hash `c09b65da87caefa87cb3c553c0630fe533702f6197157ba69b4285ab2868d300`. The reviewed bad-row rate was 12% (D40), above the 10% target and below the 15% regenerate limit. The owner delegated both the review and the go decision to the AI coding assistant. Earlier builds failed: v1 `75482df3` 24% (D30), v2 `f9fdcb8a` 30.5% (D34), v3 `297f48cb` 23% (D36; `ru_pure` 44%). The sections below describe v1 unless marked v2, v3, or v3.2.

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

**Dataset v1 (Gate 2, 2026-11-13):** v3.2 build after `python scripts/apply_review.py data/review/review_sample.csv`. The 24 dropped rows were removed; there were no fixes.
- train `794da339052aacda1d022a695afc514b6fb7aa13595ebe89a730bb076505eef9` (3,977 rows: 1,986 INJECTION, 1,991 SAFE);
- val `0efb30030d74c1b4a78ad018e2fcdc274d20728489625332ce91637a54138f77` (499 rows: 251 INJECTION, 248 SAFE);
- dataset `c09b65da87caefa87cb3c553c0630fe533702f6197157ba69b4285ab2868d300`;
- review sheet sha256 `e6c77d93...`; details in `data/processed/review_report.json`.

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
- AI review of 200 rows (`data/review/review_f9fdcb8a.csv`): 139 keep, 61 drop, 30.5%. Not applied.

## v3 build (2026-11-13)

- Generation (D35, commit `370be47`, Colab T4, Qwen2.5-14B-Instruct-AWQ, vLLM 0.33.0):
  - English only: 7,000 rows from 1,439 calls, 2,414 s including model load (`training/configs/generate_en.yaml`).
  - Translation (`training/translate_data.py`, temperature 0.3): 1,017 rows kept as `en`, 5,858 translated, 125 failed (empty or unchanged); 1,517 s. Output: 6,875 rows.
  - Raw rows, manifest (`en_manifest.json`), and log are in `data/synthetic/` (gitignored) and on Drive at `ru-guard/en_v3` and `ru-guard/synthetic_v3`.
- `python -m training.build_dataset --config training/configs/build.yaml`:
  - Dropped: language mix 221, length 1, exact duplicate 5, near duplicate 2, leakage 2, balance cap 2,144.
  - Relabeled: 507 hard negatives without a trigger word became plain SAFE.
  - Result: 3,996 train and 504 val rows. Train: 2,000 INJECTION / 1,996 SAFE, 998 hard negatives; `en` 571, `ru_mix` 1,879, `ru_pure` 1,546. Maximum Jaccard 0.430 against the test set, 0.471 against the seeds.
  - Hashes: train `30220dd3...`, val `74a8835f...`, dataset `297f48cb8adfedf3e71dadf2c506a53bc7729d766eb7ecb26d00fb7125c0ba55`.
- Token check (`scripts/token_report.py`): train maximum 192 tokens (p95 148), val maximum 170; worst-case window 356 tokens. Fits 512.
- AI review of 200 rows (`data/review/review_297f48cb.csv`, owner-delegated, not a native speaker): 154 keep, 46 drop, 23%. Not applied.
  - Per surface: `en` 2/27 (7%), `ru_mix` 7/88 (8%), `ru_pure` 37/85 (44%).
  - Causes: 38 rows of incoherent or broken Roman Urdu (invented or wrong words such as "qadim takhfif", "gaibi khayal"; 37 of them are not `en`). 8 rows where the label does not fit:
    - 3 translations changed the meaning (the speaker flipped, or the target was lost);
    - 5 come from weak English source items: 2 plain topic changes, 2 normal tool requests, and 1 persona that keeps its rules.

## v3.2 build (2026-11-13)

- `ru_pure` was dropped from training data (D38). The 2,783 English rows assigned to `ru_pure` were translated into `ru_mix` on a free Kaggle T4 (D39; commit `1b27b68`, `translate_data.py --only ru_pure --as ru_mix`): 2,696 translated, 87 failed, about 15 minutes including model load. They are in `data/synthetic/shards/rows_mix2.jsonl`, next to the 4,123 v3 `en` and `ru_mix` rows in `rows.jsonl` (both gitignored).
- `python -m training.build_dataset --config training/configs/build.yaml`:
  - Input 6,819. Dropped: language mix 161, exact duplicate 7, near duplicate 3, leakage 3, balance cap 2,145. Relabeled: 378 hard negatives without a trigger word became plain SAFE.
  - Result: 4,000 train and 500 val rows. Train: 1,998 INJECTION / 2,002 SAFE, 1,001 hard negatives; `en` 582, `ru_mix` 3,418, `ru_pure` 0. Maximum Jaccard 0.430 against the test set, 0.416 against the seeds.
  - Hashes: train `dab6dc8c...`, val `1e9884a8...`, dataset `21b2a10b27d744ffaa6361c3b148c2d1df7dd020dccac4f897f57253b190a335`.
- Token check: train maximum 209 tokens (p95 144), val maximum 185; worst-case window 349. Fits 512.
- AI review of 200 rows (`data/review/review_sample.csv`, owner-delegated, not a native speaker): 176 keep, 24 drop, 12%; verdict "review prompts". Not applied.
  - Per surface: `en` 2/32 (6%), `ru_mix` 22/168 (13%). Per label: INJECTION 13/101, SAFE 11/99.
  - Causes: 18 rows of incoherent Roman Urdu or a wrong word that changes the meaning. 6 rows where the label does not fit: 2 translations flipped the speaker, and 4 come from weak English items (a plain topic change, a benign request, a note that is not addressed to the AI, a confused payload).
- Known limit: the model never sees `ru_pure` text in training. The `ru_pure` items in the test set measure how well it generalizes from `ru_mix`.

## Dataset v1.1: human-written SAFE rows (2026-11-13, D42)

`python -m training.add_external --config training/configs/external.yaml` (run on dataset v1). This adds 900 real Roman Urdu comments as SAFE rows, with origin `external` and source `user_input`:

| Source | License | Rows | Surface |
|---|---|---|---|
| UCI "Roman Urdu Data Set", Z. Sharf (2017), https://doi.org/10.24432/C58325 | CC BY 4.0 | 600 | 450 `ru_pure`, 150 `ru_mix` |
| Kaggle "Roman Urdu Cyber Abuse Dataset", Muhammad Hassan Tariq (`hassan7838/roman-urdu-cyber-abuse-dataset`) | CC BY-SA 4.0 | 300 | `ru_mix` (150 abusive `H`, 150 ordinary `O`) |

- Raw files go in `data/external/raw/` (gitignored; download them by hand from the links above).
- Filters:
  - length 20 to 400 characters and at least 4 words;
  - denylist;
  - text with encoding damage is skipped;
  - exact duplicates, and near-duplicates (Jaccard 0.8) against the new rows and dataset v1;
  - leakage check against seeds and test (Jaccard 0.5).
  - Surface comes from the build's language heuristic.
- Maximum Jaccard of a new row: 0.092 against the test set and 0.098 against the seeds. 6 new rows contain a trigger word and are marked as hard negatives.
- Half the new rows (400 train, 50 val) replace synthetic plain SAFE `user_input` rows, and the rest are added. The replaced ids are listed in `data/processed/external_report.json`.
- Result:
  - train 4,378 rows (1,986 INJECTION, 2,392 SAFE; `en` 523, `ru_mix` 3,453, `ru_pure` 402);
  - val 548 rows (251 INJECTION, 297 SAFE);
  - hashes: train `432bb6cb72e76b2d26f6182da6247f0b82c19d73a990192a2e1572229b8e3604`, val `0b99621ae20e22beef8b69ce25faf3c93e0a14ed6ef3aa27ab4fdd02489e32cf`, dataset `f0f78baa7487829851159175e9509e0e257743e664112403a9f4afa816547afa`.
- Token check: train maximum 218 tokens, val maximum 205; worst-case window 419. Fits 512.
- Quality: the AI coding assistant spot-checked 100 new rows. They are real human text; some are rude, crude, political, or religious, and that is fine for SAFE (rude is not injection). These rows were not fully reviewed.
- **Licensing:** the CC BY-SA rows mean that any published copy of `train.jsonl` / `val.jsonl` must be shared under CC BY-SA 4.0 with the attributions above.
- Label share is now about 45% INJECTION / 55% SAFE (v1 was 50/50).
