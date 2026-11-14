"""One evaluation runner for every model (Phase 3 onward): same normalizer, prompt, and output grammar.

    python evals/eval_guard.py --model rules --split test
    python evals/eval_guard.py --model qwen-zs --split test        # Qwen2.5-1.5B-Instruct zero-shot (Ollama)
    python evals/eval_guard.py --model qwen-fs --split test        # the same with 8 seed examples
    python evals/eval_guard.py --model llama-guard --split test    # Llama Guard 3 1B (Ollama)
    python evals/eval_guard.py --model ollama:ru-guard-0.5b --split test   # Phase 4 onward

Writes evals/reports/runs/<name>/predictions.jsonl and metrics.json. Texts longer than one window are split
(Architecture 6.2) and any flagged window flags the row.
"""

import argparse
import json
import platform
import sys
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import httpx  # noqa: E402

from evals.baselines import (OLLAMA_OPTIONS, LlamaGuardScanner, OllamaScanner, few_shot_turns,  # noqa: E402
                             rule_predict, timed)
from evals.metrics import evaluate  # noqa: E402
from training.build_dataset import verify_test_lock  # noqa: E402
from training.jsonl import read_rows  # noqa: E402

WINDOW_CHARS, OVERLAP_CHARS = 1000, 200
SPLITS = {"test": REPO / "data" / "eval" / "test.jsonl", "val": REPO / "data" / "processed" / "val.jsonl"}
QWEN = "qwen2.5:1.5b-instruct"


def windows(text: str, size: int = WINDOW_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Overlapping character windows covering the text (one window when it fits)."""
    if len(text) <= size:
        return [text]
    step = size - overlap
    return [text[i:i + size] for i in range(0, max(len(text) - overlap, 1), step)]


def scan(scanner, text: str, source: str) -> tuple[str, str | None, float]:
    """Scan every window; the first flagged (or invalid) window decides, else SAFE."""
    total, raws = 0.0, []
    for w in windows(text):
        raw, pred, secs = timed(scanner, w, source)
        total += secs
        raws.append(raw)
        if pred is None or pred != "SAFE":
            return " || ".join(raws), pred, total
    return " || ".join(raws), "SAFE", total


def make_scanner(name: str, url: str):
    """(scanner, run name, model info) for a --model value."""
    if name == "rules":
        return (lambda text, source: (p := rule_predict(text), p)), "rules", {"type": "regex rules"}
    if name == "qwen-zs":
        return OllamaScanner(QWEN, url), "qwen2.5-1.5b-zeroshot", {"type": "ollama", "model": QWEN}
    if name == "qwen-fs":
        opts = dict(OLLAMA_OPTIONS, num_ctx=2048)
        shots = few_shot_turns(REPO / "data" / "seeds" / "seeds.jsonl")
        return (OllamaScanner(QWEN, url, shots=shots, options=opts), "qwen2.5-1.5b-fewshot",
                {"type": "ollama", "model": QWEN, "shots": len(shots) // 2, "num_ctx": 2048})
    if name == "llama-guard":
        return LlamaGuardScanner(url=url), "llama-guard3-1b", {"type": "ollama", "model": "llama-guard3:1b"}
    if name.startswith("ollama:"):
        model = name.split(":", 1)[1]
        return OllamaScanner(model, url), model.replace(":", "-"), {"type": "ollama", "model": model}
    raise SystemExit(f"unknown model {name}")


def versions(info: dict, url: str) -> dict:
    """Library, Ollama, and model digest versions for the report."""
    out = {"python": platform.python_version(), "numpy": metadata.version("numpy"), "httpx": metadata.version("httpx")}
    if info.get("type") == "ollama":
        out["ollama"] = httpx.get(f"{url}/api/version", timeout=10).json().get("version")
        tags = httpx.get(f"{url}/api/tags", timeout=10).json().get("models", [])
        names = {info["model"], f"{info['model']}:latest"}  # Ollama lists an untagged model as <name>:latest
        out["model_digest"] = next((m["digest"] for m in tags if m["name"] in names), None)
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--split", choices=list(SPLITS), default="test")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--limit", type=int, help="first N rows only (smoke runs)")
    ap.add_argument("--out", type=Path, default=REPO / "evals" / "reports" / "runs")
    args = ap.parse_args(argv)
    path = SPLITS[args.split]
    if args.split == "test":
        verify_test_lock(path)
    rows, errors = read_rows(path)
    if errors:
        raise SystemExit(f"data errors: {errors[:3]}")
    rows = rows[: args.limit] if args.limit else rows
    scanner, run_name, info = make_scanner(args.model, args.ollama_url)
    out_dir = args.out / f"{run_name}{'' if args.split == 'test' else '-' + args.split}"
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for i, r in enumerate(rows, 1):
            raw, pred, secs = scan(scanner, r.text, r.source)
            rec = {"id": r.id, "label": r.label, "attack_type": r.attack_type, "surface": r.surface,
                   "source": r.source, "hard_negative": r.hard_negative, "raw": raw, "pred": pred,
                   "seconds": round(secs, 4)}
            records.append(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 25 == 0:
                print(f"{run_name}: {i}/{len(rows)}", flush=True)
    secs = sorted(rec["seconds"] for rec in records)
    metrics = evaluate(records)
    metrics.update({
        "run": run_name, "split": args.split, "rows": len(records), "model": info,
        "latency_seconds": {"p50": secs[len(secs) // 2], "p95": secs[min(len(secs) - 1, int(len(secs) * 0.95))]},
        "versions": versions(info, args.ollama_url), "command": " ".join(["python", "evals/eval_guard.py", *(argv or sys.argv[1:])]),
    })
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=1), encoding="utf-8")
    o = metrics["overall"]["point"]
    print(f"{run_name}: recall {o['recall']:.3f} fpr {o['fpr']:.3f} f1 {o['f1']:.3f} "
          f"macroF1 {o['macro_f1_attack_type']:.3f} invalid {o['invalid_rate']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
