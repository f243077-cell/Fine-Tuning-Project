"""Rate synthetic rows with the generator model (coherence 1-5, label fit); writes judgements.jsonl.

Run on Colab after generate_data.py, with the same output folder:
    python -m training.judge_data --config training/configs/generate.yaml --out <drive dir>
build_dataset.py drops rows whose judgement fails (D31).
"""

import argparse
import glob
import json
import logging
import os
import re
from pathlib import Path

from training.gen_prompts import JUDGE_SYSTEM, build_judge_prompt
from training.generate_data import GenerateFn, load_config, make_hf_backend, make_vllm_backend
from training.jsonl import read_rows
from training.schemas import DataRow

log = logging.getLogger("judge_data")

# Fluency words map to the coherence scale used by build_dataset.py (keep >= 4), D32.
FLUENCY = {"GOOD": 5, "MINOR": 4, "BROKEN": 2}
ANSWER_RE = re.compile(r"\b(GOOD|MINOR|BROKEN)\b\W+(YES|NO)\b", re.IGNORECASE)


def parse_judgement(raw: str) -> tuple[int, bool] | None:
    """Extract (coherence score, label_ok) from a 'FLUENCY YES|NO' answer; None if malformed."""
    m = ANSWER_RE.search(raw)
    if not m:
        return None
    return FLUENCY[m.group(1).upper()], m.group(2).upper() == "YES"


def load_shard_rows(out_dir: Path) -> list[DataRow]:
    """All rows from the generation shards, sorted by id."""
    rows: list[DataRow] = []
    for path in sorted(glob.glob(str(out_dir / "shards" / "*.jsonl"))):
        got, errors = read_rows(Path(path))
        if errors:
            log.warning("%s: %d unreadable lines skipped", Path(path).name, len(errors))
        rows.extend(got)
    return sorted(rows, key=lambda r: r.id)


def judged_ids(path: Path) -> set[str]:
    """Ids already judged (for resume)."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["id"] for line in f if line.strip()}


def run_judge(rows: list[DataRow], generate: GenerateFn, out_path: Path, batch: int) -> dict[str, int]:
    """Judge rows not yet in out_path; append one JSON line per row; return summary counts."""
    done = judged_ids(out_path)
    todo = [r for r in rows if r.id not in done]
    counts = {"judged": 0, "parse_error": 0}
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        prompts = [[{"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": build_judge_prompt(r)}] for r in chunk]
        outputs = generate(prompts, [0] * len(chunk))
        with out_path.open("a", encoding="utf-8", newline="\n") as f:
            for r, raw in zip(chunk, outputs):
                parsed = parse_judgement(raw)
                rec = {"id": r.id, "coherent": parsed[0] if parsed else 0,
                       "label_ok": parsed[1] if parsed else False, "parse_error": parsed is None}
                counts["parse_error"] += parsed is None
                f.write(json.dumps(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())
        counts["judged"] += len(chunk)
        log.info("judged %d / %d", len(done) + counts["judged"], len(rows))
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="generation output folder (holds shards/)")
    ap.add_argument("--backend", choices=["vllm", "hf"])
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    judge_cfg = cfg.model_copy(update={"temperature": 0.0, "max_new_tokens": cfg.judge_max_new_tokens})
    rows = load_shard_rows(args.out)
    if not rows:
        log.error("no shard rows in %s", args.out)
        return 1
    backend = args.backend or cfg.backend
    generate = make_vllm_backend(judge_cfg) if backend == "vllm" else make_hf_backend(judge_cfg)
    counts = run_judge(rows, generate, args.out / "judgements.jsonl", cfg.judge_batch)
    log.info("done: %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
