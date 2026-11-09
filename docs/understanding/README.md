# understanding/

Diagrams for learning how RU-Guard fits together. Each has a PNG (open anywhere) and an SVG (scales cleanly; diagrams 01 to 03 follow light and dark mode).

| # | Diagram | What it shows | Read with |
|---|---|---|---|
| 01 | `01-rag-pipeline-with-guard-checkpoints` | The reference RAG (`demo_rag`) with guard checkpoints G0 to G4, and the guard service behind them | `Architecture.md` sections 2 and 7 |
| 02 | `02-grand-workflow` | Everything in one view: build, serve, protect, prove and gate | `Architecture.md` section 1 |
| 03 | `03-ci-cd-pipeline` | Pull-request checks, nightly runs, and the owner's release steps | `Architecture.md` section 15, `phases.md` Phases 8 and 10 |
| 04 | `04-one-guarded-request-sequence` | One question, step by step, between client, `demo_rag`, `guard-api`, Ollama, Chroma and the audit log | `Architecture.md` section 3 |
| 05 | `05-training-and-release-pipeline` | Seeds to synthetic data, QLoRA training, GGUF export, evaluation, and the retrain loop | `Architecture.md` section 10 |

Suggested order: 02 for the big picture, then 01, 04, 05, and 03 last.

Diagrams 04 and 05 come from the Mermaid blocks in `Architecture.md`. If those blocks change, re-export these two. Diagram 05 is exported top to bottom here for readability; the source is left to right.
