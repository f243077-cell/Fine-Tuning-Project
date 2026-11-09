# Phase 0: Scaffold and environment
Branch / commit: `main` (owner instruction, D14); scaffold commit `e6d95cd`.

Done:
- Folder skeleton from `Architecture.md` section 5, with `__init__.py` files, `.gitkeep` placeholders, and a README stub.
- `docs/understanding/` diagrams committed unchanged. The image links in `Architecture.md` (01, 02, 03 PNGs) resolve.
- `.gitignore`, `.gitattributes`, `.dockerignore`, `.env.example`.
- `requirements.txt` and `requirements-dev.txt` pinned after a successful install. `requirements-demo.txt` (Phase 7) and `requirements-train.txt` (Colab, Phases 2 and 4) are listed but not pinned yet, because they are not installed yet.
- `training/normalize.py` (six rules, `leet_fold` off by default) and `training/schemas.py` (`DataRow`, plus the enums `Source`, `Label`, `AttackType`, `Surface`, `Origin`), with tests.
- `guard/app/main.py` with `GET /health` and `StubScanner`. Returns 503 when the scanner is unhealthy.
- `tests/test_boundaries.py`: checks the per-package import rules and fails on third-party imports that are not on the whitelist (D13).
- `docker/Dockerfile.guard` (python:3.12-slim, non-root user, healthcheck) and `docker-compose.yml` (ollama + guard-api).
- `.github/workflows/ci.yml` runs `pytest -q` on pull requests and on pushes to `main`.
- `docs/ENVIRONMENT.md`.
- `CLAUDE.md` Commands: added Windows setup and marked commands that start in later phases.

Numbers (real runs, 2026-11-09):
- `pytest -q`: 39 passed (Windows, Python 3.12.10).
- `docker compose build`: ok.
- `docker compose up -d --no-deps guard-api`, then `curl http://127.0.0.1:8001/health`: 200 from the host and from inside the container.
- `uvicorn guard.app.main:app --port 8001`, then `curl /health`: 200.
- CI on GitHub (push to `main`, commit `e6d95cd`): success, https://github.com/f243077-cell/Fine-Tuning-Project/actions/runs/42664949060

Decisions: D11 to D14 added to the `Architecture.md` decision log.

Open issues:
- `docker compose up` with the Ollama container: not run. The `ollama/ollama:latest` image was not pulled. Its tag is pinned in Phase 6, when it is tested.
- The CI acceptance item says "CI green on a test PR". CI ran on the push to `main` instead, because work goes to `main` directly (D14).
- `fastapi.testclient` gives a Starlette deprecation warning that recommends `httpx2`. `httpx2` is not on the whitelist, so `httpx` stays.
- PRD open question 2 (approve `httpx` and `PyYAML`) is still open. `httpx` is in use per `phases.md` Phase 0. `PyYAML` is not used yet.
- Stale pictures: none.

Needs from owner:
- Confirm CPU and RAM in `docs/ENVIRONMENT.md` (Intel i7-7500U, 2 cores / 4 threads, 15.9 GB). The 2-core CPU puts the 1.5B latency target at risk.
- Answer PRD open question 2 (`httpx`, `PyYAML`).
- Say "start phase 1" to continue.
