# Phase 2: Synthetic data generation

Branch / commit: `main` (D14). Status: **all Claude Code tasks are done. Waiting for the owner's Colab run (the [HUMAN] step).** Gate 2 is not reached yet.

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

## Open issues

- vLLM 0.33 on a T4 has not been tried. The fallback path and the config switches are in the Colab doc.
- `requirements-train.txt` is unpinned until `manifest.json` comes back.
- Phase 6: `guard/` must import `training/prompt.py` (extend the boundary rule). Windows of unusual characters can exceed 512 tokens.
- One seed is mislabeled for its surface (see above). The seeds are not edited here. Fix it in a later seeds revision if you want.
- The `data/eval/.gitkeep` note from Phase 1 still applies.

## Owner steps ([HUMAN])

1. Follow `docs/colab/02_generate.md`. Bring back `data/synthetic/` (shards, manifest, state).
2. Tell Claude Code that the data is in place. Claude Code runs the build, the token report on train/val, and the 200-row sample, then fills in `DATA_CARD.md`.
3. Review `data/review/review_sample.csv` (keep/fix/drop), then run `apply_review.py`.
4. Decide go or no-go. Gate 2 means: you approve dataset v1, and its hash is recorded in `DATA_CARD.md`.
