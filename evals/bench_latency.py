"""Latency benchmark (Phase 5): p50/p95 per window on this CPU, cold vs warm, through Ollama.

    python evals/bench_latency.py --model ru-guard-0.5b --n 200 --cold 5

Uses val windows (never the test set). Cold = the model is unloaded (keep_alive 0) before each timed call,
so the time includes loading. Warm = after 3 warm-up calls, n calls with the model resident.
Writes evals/reports/latency/<model>.json.
"""

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import httpx  # noqa: E402

from evals.baselines import OLLAMA_OPTIONS, OllamaScanner  # noqa: E402
from training.jsonl import read_rows  # noqa: E402

VAL = REPO / "data" / "processed" / "val.jsonl"
OUT = REPO / "evals" / "reports" / "latency"


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile of a non-empty list."""
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q / 100 * len(s))) - 1))]


def summary(values: list[float]) -> dict[str, float]:
    """p50, p95, mean, n (seconds)."""
    return {"p50": round(percentile(values, 50), 4), "p95": round(percentile(values, 95), 4),
            "mean": round(sum(values) / len(values), 4), "n": len(values)}


def unload(url: str, model: str) -> None:
    """Ask Ollama to drop the model from memory."""
    httpx.post(f"{url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60).raise_for_status()


def timed_call(scanner: OllamaScanner, text: str, source: str) -> float:
    """Wall time of one scan."""
    t0 = time.perf_counter()
    scanner(text, source)
    return time.perf_counter() - t0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--cold", type=int, default=5)
    ap.add_argument("--url", default="http://localhost:11434")
    args = ap.parse_args(argv)
    rows, errors = read_rows(VAL)
    if errors:
        raise SystemExit(f"val errors: {errors[:3]}")
    rows = sorted(rows, key=lambda r: r.id)[: args.n]
    scanner = OllamaScanner(args.model, args.url, options=dict(OLLAMA_OPTIONS))
    cold = []
    for r in rows[: args.cold]:
        unload(args.url, args.model)
        cold.append(timed_call(scanner, r.text, str(r.source)))
    for r in rows[:3]:
        scanner(r.text, str(r.source))
    warm = [timed_call(scanner, r.text, str(r.source)) for r in rows]
    result = {"model": args.model, "cold_seconds": summary(cold), "warm_seconds": summary(warm),
              "machine": {"cpu": platform.processor(), "cpu_count": os.cpu_count(), "os": platform.platform()},
              "ollama": httpx.get(f"{args.url}/api/version", timeout=10).json().get("version"),
              "options": OLLAMA_OPTIONS, "command": " ".join(["python", "evals/bench_latency.py", *(argv or sys.argv[1:])])}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.model.replace(':', '-')}.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("model", "cold_seconds", "warm_seconds")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
