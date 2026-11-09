# Environment

Recorded 2026-11-09 (Phase 0). Values were read from the machine with `Get-CimInstance`, `docker info`, and `wsl --version`. **Owner: confirm CPU and RAM below.**

## Host

| Item | Value |
|---|---|
| OS | Windows 10 Pro 10.0.19045 |
| CPU | Intel Core i7-7500U @ 2.70 GHz, 2 cores / 4 threads (owner to confirm) |
| RAM | 15.9 GB (owner to confirm) |
| GPU | Intel HD Graphics 620 (no CUDA GPU; all training runs on Colab) |
| WSL | 3.0.3.0, kernel 6.18.54.1-1. Only the `docker-desktop` distro is installed; no Ubuntu distro. |

## Toolchain

| Item | Version |
|---|---|
| Python (venv) | 3.12.10 (Windows, via `py -3.12`) |
| Git | 2.54.0.windows.1 |
| Docker Engine | 29.8.2 (Docker Desktop, WSL2 backend) |
| Docker Compose | v5.6.0 |
| Docker VM limits | 4 CPUs, 9.7 GiB RAM |

## Notes

- `CLAUDE.md` assumes WSL2 Ubuntu. This machine runs the Python tooling on Windows directly; both setups are listed in the `CLAUDE.md` Commands section.
- The CPU has 2 physical cores. The 1.5B latency target (p95 <= 1,000 ms per window, PRD NFR-3) is at risk; measure in Phase 5 and fall back to 0.5B if needed (PRD section 16).
