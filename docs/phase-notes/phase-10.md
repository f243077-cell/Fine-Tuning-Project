# Phase 10: Packaging and release

Branch / commit: `main`. Status: **done except the owner's items; waiting at Gate 10 (owner publishes).**

## Done
- `README.md` rewritten for release: why, results table, the five diagrams, a clean-clone quickstart (model from Release `model-v1` with a SHA-256 check), the demo app, gateway, client and playground, limitations, ethics, related work, licences.
- Final `MODEL_CARD.md` (licences checked on the Hugging Face pages: the three Qwen models are Apache-2.0; Llama Guard 3 is a baseline only) and `data/DATA_CARD.md` (release summary with counts and hashes counted from the files).
- `docs/INTERVIEW_NOTES.md`, `docs/DEMO.md` (script and recording checklist), `CHANGELOG.md`, `docs/PRD_ACCEPTANCE.md`.
- `evals/reports/EVAL_REPORT.md`: section 9 (reference-RAG ASR and quality, red-team), PRD targets for ASR (met, 8/36 to 0/36) and golden set (met, +6.7 points).
- Novelty re-check (PRD section 2), 2026-11-16: Roman Urdu appears only in a benchmark paper, two small rule/TF-IDF course projects, and Urdu-script models. The README makes a narrow claim and says it is not a claim to be first.

## Numbers (real runs, 2026-11-16)
- Test lock verified (`1f8710e6fbae`). Full 300-row rerun of the headline command: recall 0.953, FPR 0.100, F1 0.929 (identical), macro-F1 0.877 (release 0.869), 1 of 300 rows differ, gate PASS.
- CI smoke gate: runs 51, 55, 56 passed; 52 failed. Diagnostic (`diag/jitter`): 3 runs per runner are identical; AMD EPYC 7763 differs from the saved run by 1 row of 100, AMD EPYC 9V45 by 4. Smoke margin set to 10 points (D57, D58); evidence in `evals/reports/smoke_gate_check.md`.
- Drill: untuned Qwen under the guard's name fails the Merge gate on CI (run 53).

## Fixes made in this phase
- Smoke gate margin (D57, D58); the gate step now prints metrics and failures as public run annotations.
- A broken `ci.yml` was pushed once (commit `044c1ee`, run 54) and fixed in the next commit.
- Nightly run 1 failed at install (deepeval 4.3.x vs huggingface-hub on `click`); DeepEval now runs in its own virtual environment (`requirements-redteam.txt`).

## Needs from the owner (Gate 10)
1. **Choose a licence** for the repository's code and add `LICENSE` (Apache-2.0 would match the models). Decide how to license the released weights (CC BY-SA rows in the training data, see the model card).
2. **Record the demo** (`docs/DEMO.md`) and put the link in the README.
3. **Run the all-Docker quickstart from a fresh clone** (`ollama` container path; never run here because the image download stalled).
4. **Tag `v1.0`** and create the v1.0 Release with `CHANGELOG.md` as notes (attach the GGUF or link `model-v1`).
5. Optional: open the Actions page and press "Run workflow" on `nightly` to check the fixed nightly before tonight's scheduled run.
6. Branches `drill/untuned-model` and `diag/jitter` can be deleted (I did not delete them; deleting needs your OK).
7. Native-speaker review of the test set, seeds and Roman Urdu demo texts is still open (D22, D53, D54).

## Open issues
- v2 adapters and merged weights were not kept; v1 ones on Drive not verified.
- The full 300-row gate keeps 2 points and has not run on a CI runner; it may flake on the EPYC 9V45 runner type.
- Local dev environment: installing `requirements-redteam.txt` into the main `.venv` breaks `huggingface-hub`'s `click` requirement; use `.venv-redteam`.
- Diagrams in `docs/understanding/` are not stale.
