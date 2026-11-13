"""Check that system prompt + window + label fit max_seq_len with the Qwen2.5 tokenizer.

    python scripts/token_report.py data/seeds/seeds.jsonl data/processed/train.jsonl
Exit code 0 when everything fits, 1 when something does not.
"""

import argparse
import json
import statistics
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.jsonl import read_rows  # noqa: E402
from training.normalize import normalize_text  # noqa: E402
from training.prompt import build_messages  # noqa: E402
from training.schemas import Source  # noqa: E402

LONGEST_TARGET = "INJECTION|exfiltration"


def chat_tokens(tokenizer: Any, text: str, source: str, target: str) -> int:
    """Token count of the full training example (system + user + assistant answer)."""
    rendered = tokenizer.apply_chat_template(build_messages(text, source, target), tokenize=False)
    return len(tokenizer(rendered, add_special_tokens=False)["input_ids"])


def worst_case_windows(texts: Iterable[str], window_chars: int) -> list[str]:
    """Full-size windows cut from joined normalized texts (serving windows normalized text)."""
    joined = " ".join(normalize_text(t) for t in texts)
    if not joined:
        return []
    while len(joined) < window_chars * 3:
        joined = joined + " " + joined
    return [joined[i:i + window_chars] for i in range(0, window_chars * 3, window_chars)]


def summarize(values: list[int]) -> dict[str, float]:
    """Max, p95, and mean of token counts."""
    s = sorted(values)
    return {"n": len(s), "max": s[-1], "p95": s[min(len(s) - 1, int(0.95 * len(s)))],
            "mean": round(statistics.fmean(s), 1)}


def report(tokenizer: Any, files: list[Path], window_chars: int, max_seq_len: int) -> dict:
    """Token statistics per file plus the worst-case full window per source."""
    out: dict = {"max_seq_len": max_seq_len, "window_chars": window_chars, "files": {}, "worst_case": {}}
    all_texts: list[str] = []
    for f in files:
        rows, errors = read_rows(f)
        if errors:
            raise SystemExit(f"{f}: {errors[:3]}")
        out["files"][f.name] = summarize([chat_tokens(tokenizer, r.text, r.source, r.target) for r in rows])
        all_texts += [r.text for r in rows]
    windows = worst_case_windows(all_texts, window_chars)
    for src in Source:
        counts = [chat_tokens(tokenizer, w, src.value, LONGEST_TARGET) for w in windows]
        out["worst_case"][src.value] = max(counts) if counts else 0
    biggest = max([v["max"] for v in out["files"].values()] + list(out["worst_case"].values()))
    out["largest"] = biggest
    out["fits"] = biggest <= max_seq_len
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--tokenizer", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--window-chars", type=int, default=1000)
    ap.add_argument("--max-seq-len", type=int, default=512)
    args = ap.parse_args(argv)
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(args.tokenizer)
    result = report(tok, args.files, args.window_chars, args.max_seq_len)
    result["tokenizer"] = args.tokenizer
    print(json.dumps(result, indent=1))
    return 0 if result["fits"] else 1


if __name__ == "__main__":
    sys.exit(main())
