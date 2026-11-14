"""Error analysis for one evaluation run (Phase 5): confusion by attack type, every false negative and false
positive with cause tags, and tag counts. Writes markdown.

    python evals/error_analysis.py evals/reports/runs/ru-guard-1.5b --out evals/reports/errors_ru-guard-1.5b.md

Cause tags are heuristics that point the human analysis to a group; they are not ground truth:
roman_urdu (surface ru_mix or ru_pure), hard_negative, indirect_source (retrieved_chunk or tool_output),
guard_targeting (the text talks to or about the classifier), windowing (longer than one window), invalid_output.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evals.eval_guard import WINDOW_CHARS  # noqa: E402
from evals.metrics import ATTACK_TYPES  # noqa: E402
from training.jsonl import read_rows  # noqa: E402

TEST = REPO / "data" / "eval" / "test.jsonl"
GUARD_RE = re.compile(r"\b(classifier|guard|scanner|filter|label|SAFE|INJECTION|moderat\w*)\b", re.I)
PRED_COLS = ["SAFE", *ATTACK_TYPES, "INJECTION (no type)", "INVALID"]


def pred_col(pred: str | None) -> str:
    """Column of the confusion table for one prediction."""
    if pred is None:
        return "INVALID"
    if pred == "SAFE":
        return "SAFE"
    return pred.split("|", 1)[1] if "|" in pred else "INJECTION (no type)"


def tags(rec: dict, text: str) -> list[str]:
    """Heuristic cause tags for one wrong row."""
    out = []
    if rec["surface"] != "en":
        out.append("roman_urdu")
    if rec.get("hard_negative"):
        out.append("hard_negative")
    if rec["source"] != "user_input":
        out.append("indirect_source")
    if GUARD_RE.search(text):
        out.append("guard_targeting")
    if len(text) > WINDOW_CHARS:
        out.append("windowing")
    if rec["pred"] is None:
        out.append("invalid_output")
    return out


def confusion(records: list[dict]) -> dict[str, Counter]:
    """True class (SAFE or attack type) -> counts per prediction column."""
    table: dict[str, Counter] = {}
    for r in records:
        true = r.get("attack_type") or "SAFE"
        table.setdefault(true, Counter())[pred_col(r["pred"])] += 1
    return table


def errors(records: list[dict], texts: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """(false negatives, false positives), each with text excerpt and tags. Invalid counts as a flag (D43)."""
    fns, fps = [], []
    for r in records:
        flagged = r["pred"] is None or r["pred"] != "SAFE"
        item = {**r, "text": texts.get(r["id"], ""), "tags": tags(r, texts.get(r["id"], ""))}
        if r["label"] == "INJECTION" and not flagged:
            fns.append(item)
        elif r["label"] == "SAFE" and flagged:
            fps.append(item)
    return fns, fps


def excerpt(text: str, n: int = 140) -> str:
    """One-line excerpt safe for a markdown table cell."""
    one = " ".join(text.split()).replace("|", "\\|")
    return one if len(one) <= n else one[: n - 3] + "..."


def render(run: str, records: list[dict], texts: dict[str, str]) -> str:
    """Markdown report for one run."""
    table = confusion(records)
    fns, fps = errors(records, texts)
    md = [f"## Errors: {run}", "", f"{len(records)} rows; {len(fns)} false negatives, {len(fps)} false positives "
          "(invalid output counts as a flag, D43).", "", "### Confusion by attack type (rows = truth)", "",
          "| True \\ Predicted | " + " | ".join(PRED_COLS) + " |", "|---" * (len(PRED_COLS) + 1) + "|"]
    for true in ["SAFE", *ATTACK_TYPES]:
        c = table.get(true, Counter())
        md.append(f"| {true} | " + " | ".join(str(c.get(col, 0)) for col in PRED_COLS) + " |")
    for title, items in (("False negatives (missed attacks)", fns), ("False positives (benign text flagged)", fps)):
        counts = Counter(t for i in items for t in i["tags"])
        md += ["", f"### {title}: {len(items)}", "",
               "Tag counts: " + (", ".join(f"{k} {v}" for k, v in counts.most_common()) or "none"), ""]
        if items:
            md += ["| id | type | surface | source | output | tags | text |", "|---|---|---|---|---|---|---|"]
            for i in items:
                md.append(f"| {i['id']} | {i.get('attack_type') or 'SAFE'} | {i['surface']} | {i['source']} | "
                          f"`{excerpt(str(i['raw']), 40)}` | {', '.join(i['tags'])} | {excerpt(i['text'])} |")
    return "\n".join(md) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run", type=Path, help="evals/reports/runs/<name>")
    ap.add_argument("--test", type=Path, default=TEST)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    rows, errs = read_rows(args.test)
    if errs:
        raise SystemExit(f"test file errors: {errs[:3]}")
    texts = {r.id: r.text for r in rows}
    records = [json.loads(line) for line in (args.run / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    args.out.write_text(render(args.run.name, records, texts), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
