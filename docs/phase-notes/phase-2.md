# Phase 2: Synthetic data generation

Branch / commit: `main` (D14). Status: **Gate 2 passed (D41).** Dataset v1 is the v3.2 build (en and `ru_mix` only, D38) with its review applied: 3,977 train and 499 val rows, hash `c09b65da...`. The review found 12% bad rows (D40). The owner delegated the go decision. Phase 3 starts when the owner says "start phase 3". **Current data: dataset v1.1** (D42: v1 plus 900 human-written Roman Urdu SAFE rows from UCI and the Roman Urdu Cyber Abuse Dataset; 4,378 train and 548 val, hash `f0f78baa...`). ERUPD (arXiv 2412.17562) was considered but not used: there is no public download, and the owner chose to go ahead with v1.1. Earlier builds: v1 24%, v2 30.5%, v3 23% (`ru_pure` 44%).

## Done (Claude Code)

- `training/prompt.py`: the classifier chat template from Architecture 6.3 (`build_messages`), which normalizes the text. Training and serving share it (D26).
- `training/gen_prompts.py` and `training/generate_data.py`:
  - The cell plan: 63 cells, 6,600 raw rows (D24).
  - Few-shot prompts built from the seeds, with spelling-style and topic variation and benign placeholder payloads.
  - Two backends: vLLM with the AWQ checkpoint, and Transformers + bitsandbytes NF4 as the fallback (D23).
  - Resumable shards, `state.json`, and `manifest.json` (library versions are recorded so they can be pinned).
  - `--dry-run` previews the prompts; `--max-calls` runs a smoke test.
- `training/configs/generate.yaml`, `build.yaml`, and `denylist.yaml`.
- `training/build_dataset.py`. The pipeline does these steps in order:
  1. Verifies the test lock.
  2. Checks the schema.
  3. Checks the length (15 to 1,000 characters).
  4. Applies the denylist.
  5. Applies the language-mix heuristic.
  6. Removes exact duplicates.
  7. Removes rows that leak from the seeds or the test set (Jaccard 0.5 or higher).
  8. Removes near-duplicates (Jaccard 0.8 or higher).
  9. Balances the labels.
  10. Splits train/val, stratified by cell.

  It writes `build_report.json` with the hashes (D25).
- `scripts/token_report.py` (D27), `scripts/sample_for_review.py`, and `scripts/apply_review.py` (D28).
- `docs/colab/02_generate.md` (the hand-off) and `data/DATA_CARD.md` (a template; numbers are "not run" until the real build).
- Tests: `training/tests/test_generate_data.py`, `training/tests/test_build_dataset.py`, `scripts/tests/test_token_report.py`, and `scripts/tests/test_review.py`. They cover dedup (prefix-filter index checked against brute force), leakage against a fixture test set, a changed test lock, split determinism, the denylist, language mix, balance, resume, and the attempt cap.

## Numbers (real runs, 2026-11-13)

- `pytest -q`: 87 passed.
- `python -m training.generate_data --config training/configs/generate.yaml --out <scratch> --dry-run`: 63 cells, 6,600 target rows; prompts written.
- `python scripts/token_report.py data/seeds/seeds.jsonl`: seeds maximum 131 tokens, p95 128; worst-case 1,000-character window 428 tokens; fits 512. The same largest value (428) with `--tokenizer Qwen/Qwen2.5-1.5B-Instruct`.
- Language-mix heuristic on the seeds: 79 of 80 pass. The failure is seed "Bus booking confirmed: Daewoo, Lahore to Multan..." (all English, labeled `ru_mix`).
- Generation, build, review: not run (they need the Colab run).

## Colab run and build (2026-11-13)

Claude Code ran Colab through the owner's browser. The owner approved the Drive mount and the download.
- Smoke test with 7B (8 calls): an `en` cell got Roman Urdu items. Fixed by putting same-language seeds first (commit `b60ef57`).
- Full run with 7B: stopped after about 200 calls. It gave about 1.1 usable rows per call, and much of the Roman Urdu was incoherent.
- Smoke test with 14B (64 calls): 284 rows, with clearly better Roman Urdu. The generator was switched to Qwen2.5-14B-Instruct-AWQ and the payload lists were widened (D29, commit `c5e15f7`).
- Full run with 14B: 6,600 rows from 1,518 calls in 2,612 s on a T4. Manifest: `data/processed/generation_manifest.json`.
- Colab note: killing the generator with `pkill` left an orphaned `VLLM::EngineCore` process holding 14 GB of GPU memory. Kill the GPU processes by pid (`nvidia-smi --query-compute-apps=pid`).
- `python -m training.build_dataset --config training/configs/build.yaml`: 4,004 train and 496 val rows; dataset hash `75482df3...`; maximum Jaccard 0.446 against the test set. Drops are listed in `data/DATA_CARD.md`.
- `python scripts/token_report.py data/processed/train.jsonl data/processed/val.jsonl`: largest 291 tokens; fits 512.
- `python scripts/sample_for_review.py --n 200`: `data/review/review_sample.csv`.
- `requirements-train.txt` is pinned from the manifest.

## v3 run (2026-11-13)

Claude Code ran Colab through the owner's Chrome. The owner approved the Drive mount.
- English generation: 7,000 rows in 2,414 s. Translation: 5,858 translated, 1,017 kept as `en`, 125 failed; 1,517 s.
- Build: 3,996 train and 504 val rows, dataset hash `297f48cb...`. Token check fits 512 (largest 192).
- AI review: 23% bad (`ru_pure` 44%). Details are in `data/DATA_CARD.md` and D36.
- Proposed next step: re-translate only the `ru_pure` rows with a simpler prompt (see D36). About 15 minutes on Colab, because `en_v3` is on Drive.

## v3.1 and v3.2 (2026-11-13)

- v3.1 (D37): a simpler `ru_pure` prompt was still garbled in a 15-row spot check (about 10 of 15 bad). The run was stopped.
- The free Colab GPU quota ran out. Kaggle's free T4 was added as backup compute after the owner approved it (D39). The owner verified the account by phone.
- v3.2 (D38): the `ru_pure`-assigned rows were translated into `ru_mix` on Kaggle (2,696 rows). Build `21b2a10b`: 4,000 train and 500 val; tokens fit (largest 209).
- AI review: 12% bad (`ru_mix` 13%, `en` 6%). Details are in `data/DATA_CARD.md`.

Gate 2 options for the owner:
1. Approve v3.2: run `python scripts/apply_review.py data/review/review_sample.csv` (removes the 24 bad rows). Record the new hash in `DATA_CARD.md`, then start Phase 3.
2. Another round: for example, drop hard negatives that need relabeling, or re-translate with stricter checks. Then rebuild and review again.

## Open issues

- vLLM 0.33 works on the T4 with the AWQ checkpoint; the Transformers fallback was not needed.
- Data quality: see the spot-check limits in `data/DATA_CARD.md`. The review decides go or no-go.
- Phase 6: `guard/` must import `training/prompt.py` (extend the boundary rule). Windows of unusual characters can exceed 512 tokens.
- One seed is mislabeled for its surface (see above). The seeds are not edited here. Fix it in a later seeds revision if you want.
- The `data/eval/.gitkeep` note from Phase 1 still applies.

## Owner steps ([HUMAN])

1. Follow `docs/colab/02_generate.md`. Bring back `data/synthetic/` (shards, manifest, state).
2. Tell Claude Code that the data is in place. Claude Code runs the build, the token report on train/val, and the 200-row sample, then fills in `DATA_CARD.md`.
3. Review `data/review/review_sample.csv` (keep/fix/drop), then run `apply_review.py`.
4. Decide go or no-go. Gate 2 means: you approve dataset v1, and its hash is recorded in `DATA_CARD.md`.
