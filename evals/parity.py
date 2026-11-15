"""Parity check (Phase 6): the same rows through guard-api and through the evaluation harness must give the same labels.

    python evals/parity.py --model ru-guard-1.5b-v2 --guard-url http://localhost:8001   # GUARD_API_KEY from env

Uses 50 test rows (every 6th row of the frozen test set, read-only). Reaches the guard only over HTTP through client/.
Writes evals/reports/parity/<model>.json and exits 1 on any mismatch.
"""

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from client.ruguard_client import GuardClient  # noqa: E402
from evals.baselines import OllamaScanner  # noqa: E402
from evals.eval_guard import SPLITS, scan  # noqa: E402
from training.build_dataset import verify_test_lock  # noqa: E402
from training.jsonl import read_rows  # noqa: E402


def service_label(body: dict) -> str | None:
    """guard-api response as a harness label (None for a scanner error)."""
    if body["verdict"] == "safe":
        return "SAFE"
    if body["verdict"] == "injection":
        return f"INJECTION|{body['attack_type']}"
    return None


def pct(values: list[float], q: float) -> float:
    """Nearest-rank percentile (same rule as eval_guard)."""
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * q))]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--guard-url", default="http://localhost:8001")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", type=Path, default=REPO / "evals" / "reports" / "parity")
    args = ap.parse_args(argv)
    path = SPLITS["test"]
    verify_test_lock(path)
    rows, errors = read_rows(path)
    if errors:
        raise SystemExit(f"data errors: {errors[:3]}")
    step = max(1, len(rows) // args.n)
    rows = rows[::step][: args.n]
    harness = OllamaScanner(args.model, args.ollama_url)
    guard = GuardClient(args.guard_url, os.environ.get("GUARD_API_KEY", ""), fail_mode="raise")
    health = guard.health().model_dump()
    if health.get("model") != args.model:
        raise SystemExit(f"guard-api serves {health.get('model')!r}, not {args.model!r}")
    records, mismatches = [], []
    with guard:
        for i, r in enumerate(rows, 1):
            h_raw, h_pred, h_secs = scan(harness, r.text, r.source)
            body = guard.scan(r.text, r.source, request_id=f"parity-{r.id}").model_dump()
            s_pred = service_label(body)
            rec = {"id": r.id, "harness": h_pred, "service": s_pred, "harness_raw": h_raw,
                   "service_latency_ms": body["latency_ms"], "harness_seconds": round(h_secs, 4),
                   "windows": body["windows"], "scanner_error": body["scanner_error"]}
            records.append(rec)
            if h_pred != s_pred:
                mismatches.append(rec)
            if i % 10 == 0:
                print(f"parity: {i}/{len(rows)}, mismatches {len(mismatches)}", flush=True)
    lat = [float(x["service_latency_ms"]) for x in records]
    report = {
        "model": args.model, "rows": len(records), "row_step": step, "matches": len(records) - len(mismatches),
        "mismatches": mismatches,
        # Each service call follows the harness call on the same prompt, so Ollama's prompt cache makes it faster.
        # Not a latency measurement; use evals/bench_latency.py --guard-url for that.
        "service_latency_ms_after_harness": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95)},
        "service": health, "command": " ".join(["python", "evals/parity.py", *(argv or sys.argv[1:])]),
        "records": records,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"{args.model.replace(':', '-')}.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"parity {args.model}: {report['matches']}/{len(records)} match -> {out}")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
