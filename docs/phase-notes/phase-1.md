# Phase 1: Taxonomy, seeds, and the frozen test set
Branch / commit: `main` (D14). Status: **Claude Code tasks done; waiting for the owner's [HUMAN] tasks.**

Done (Claude Code):
- `docs/LABELING_GUIDE.md`: rules from PRD sections 6 and 7, a proposed attack_type tie-break (D20), 3 English examples per attack type, and 3 hard negatives. Roman Urdu examples are left for the owner.
- `hard_negative` field on `DataRow` and in the CSVs (D16). `Architecture.md` section 9 updated.
- Templates: `data/seeds/seeds_template.csv` and `data/templates/test_template.csv` (D17).
- `scripts/csv_to_jsonl.py`: errors per row (spreadsheet row numbers); writes nothing if any row fails; never overwrites a locked JSONL (D18, D19).
- `scripts/validate_data.py`: schema, duplicate ids, duplicate normalized text per source, length check, label balance, coverage matrix, required cells (D21), intent triplet checks, and PRD target warnings.
- `scripts/lock_test.py`, `scripts/verify_test_lock.py`, and `scripts/locking.py`: SHA-256 with line endings folded (D18). Locking refuses an invalid set and never overwrites an existing lock. `scripts/tests/test_locking.py::test_repo_test_set_matches_lock` skips until the lock exists.
- `scripts/eda.py`: `<name>_lengths.png` and `<name>_coverage.png` in `docs/figures/`.
- `training/jsonl.py`: shared JSONL read and write with line-level errors.

Numbers (real runs, 2026-11-09):
- `pytest -q`: 62 passed, 1 skipped (the repo lock check; no lock yet).
- `python scripts/verify_test_lock.py`: exit 2, "no lock yet".
- Seeds and test set statistics: not run, because the data does not exist yet.

Decisions: D15 to D21 in the `Architecture.md` decision log.

Open issues:
- In Phase 0, I created an empty `data/eval/.gitkeep` so that the folder exists in git. This conflicts with the rule "never write into `data/eval/`". It is empty and harmless. Delete it if you want strict compliance.
- The attack_type tie-break (D20) is a proposal. Confirm or change it before you write the test set.

## Owner steps ([HUMAN])

1. Read `docs/LABELING_GUIDE.md`. Add your Roman Urdu examples if you want them there.
2. **Seeds.** Copy `data/seeds/seeds_template.csv` to `data/seeds/seeds.csv` and fill it in a spreadsheet (about 80 rows: 40 injection with at least 8 per attack type, 40 benign with at least 20 hard negatives, mostly `ru_mix` and `ru_pure`). Save as CSV UTF-8. Then run:
   ```bash
   python scripts/csv_to_jsonl.py data/seeds/seeds.csv data/seeds/seeds.jsonl --origin seed
   python scripts/validate_data.py data/seeds/seeds.jsonl
   ```
   Fix the reported rows in the CSV and rerun (add `--force` to `csv_to_jsonl.py` to overwrite) until there are 0 errors.
3. **Test set.** Copy `data/templates/test_template.csv` to a private working file **outside the repo** or in `data/templates/` (do not commit drafts). Write 100 intents x 3 surfaces = 300 rows. Use the same `intent_id` (for example `t-001`) for the `en`, `ru_mix`, and `ru_pure` rows of one intent. Then run:
   ```bash
   python scripts/csv_to_jsonl.py <your_test.csv> data/eval/test.jsonl --origin test
   python scripts/validate_data.py data/eval/test.jsonl
   ```
   Repeat until there are 0 errors. Read every warning.
4. Self-review. Drop ambiguous items (PRD section 7, rule 5).
5. **Lock** (once):
   ```bash
   python scripts/lock_test.py
   python scripts/verify_test_lock.py
   ```
6. Optional figures: `python scripts/eda.py data/seeds/seeds.jsonl` and `python scripts/eda.py data/eval/test.jsonl`.
7. Commit `data/seeds/seeds.csv`, `data/seeds/seeds.jsonl`, `data/eval/test.jsonl`, and `data/eval/test.lock`. Then say "test set locked" (Gate 1).

Needs from owner: the steps above. Claude Code cannot write seeds or test items.
