"""Turn English synthetic rows into the final surface mix: keep some as en, translate the rest (D35).

Run on Colab after an English-only generation run (training/configs/generate_en.yaml):
    python -m training.translate_data --config training/configs/generate_en.yaml --in <en run dir> --out <dir>
Labels, sources, and attack types are copied from the English row; only the surface and text change.
"""

import argparse
import hashlib
import json
import logging
import os
import random
from pathlib import Path

from pydantic import ValidationError

from training.gen_prompts import TRANSLATE_SYSTEM, build_translate_prompt
from training.generate_data import GenerateFn, load_config, make_hf_backend, make_vllm_backend
from training.judge_data import load_shard_rows
from training.normalize import normalize_text
from training.schemas import DataRow

log = logging.getLogger("translate_data")

SURFACE_ORDER = ("en", "ru_mix", "ru_pure")


def assign_surface(row_id: str, shares: dict[str, float]) -> str:
    """Deterministic target surface for an English row, from a hash of its id."""
    u = int(hashlib.sha256(row_id.encode()).hexdigest()[:8], 16) / 0x100000000
    total = sum(shares[s] for s in SURFACE_ORDER)
    acc = 0.0
    for s in SURFACE_ORDER:
        acc += shares[s] / total
        if u < acc:
            return s
    return SURFACE_ORDER[-1]


def clean_translation(raw: str) -> str:
    """Strip code fences, a leading label, trailing extra examples, and wrapping quotes."""
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0].strip()
    for prefix in ("Roman Urdu:", "Translation:"):
        if t.lower().startswith(prefix.lower()):
            t = t[len(prefix):].strip()
    t = t.split("\nEnglish:", 1)[0].strip()
    if len(t) >= 2 and t[0] == t[-1] == '"':
        t = t[1:-1].strip()
    return t


def done_ids(path: Path) -> set[str]:
    """Ids of English source rows already handled (for resume)."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["source_id"] for line in f if line.strip()}


def _append(path: Path, lines: list[str]) -> None:
    """Append lines and flush to disk (safe against Colab disconnects)."""
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.writelines(line + "\n" for line in lines)
        f.flush()
        os.fsync(f.fileno())


def translate_one(row: DataRow, surface: str, raw: str) -> DataRow | None:
    """The translated row, or None if the output is empty, unchanged, or invalid."""
    text = clean_translation(raw)
    if not text or normalize_text(text) == normalize_text(row.text):
        return None
    try:
        return DataRow.model_validate({**row.model_dump(mode="json"), "id": f"{row.id}-{surface}",
                                       "surface": surface, "text": text})
    except ValidationError:
        return None


def run_translate(rows: list[DataRow], generate: GenerateFn, out_dir: Path, shares: dict[str, float],
                  batch: int, seed: int, only: str | None = None, as_surface: str | None = None) -> dict[str, int]:
    """Write final rows to out_dir/shards/rows.jsonl and per-source status to out_dir/progress.jsonl.

    With `only`, handle just the rows whose target surface is `only` (to redo one surface, D37).
    With `as_surface`, translate every handled row into that surface instead (D38).
    """
    shard = out_dir / "shards" / "rows.jsonl"
    shard.parent.mkdir(parents=True, exist_ok=True)
    progress = out_dir / "progress.jsonl"
    done = done_ids(progress)
    todo = [r for r in rows if r.id not in done and r.surface == "en"
            and (only is None or assign_surface(r.id, shares) == only)]
    counts = {"kept_en": 0, "translated": 0, "failed": 0}
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        targets = [as_surface or assign_surface(r.id, shares) for r in chunk]
        need = [(r, s) for r, s in zip(chunk, targets) if s != "en"]
        prompts = [[{"role": "system", "content": TRANSLATE_SYSTEM},
                    {"role": "user", "content": build_translate_prompt(r.text, s, random.Random(f"{seed}|{r.id}"))}]
                   for r, s in need]
        outs = iter(generate(prompts, [seed] * len(prompts)) if prompts else [])
        out_rows: list[str] = []
        marks: list[str] = []
        for r, s in zip(chunk, targets):
            new = r if s == "en" else translate_one(r, s, next(outs))
            status = "kept_en" if s == "en" else ("translated" if new else "failed")
            counts[status] += 1
            if new:
                out_rows.append(json.dumps(new.model_dump(mode="json"), ensure_ascii=False))
            marks.append(json.dumps({"source_id": r.id, "surface": s, "status": status}))
        _append(shard, out_rows)
        _append(progress, marks)
        log.info("handled %d / %d", len(done) + start + len(chunk), len(done) + len(todo))
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--in", dest="in_dir", type=Path, required=True, help="English generation folder (holds shards/)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--backend", choices=["vllm", "hf"])
    ap.add_argument("--only", choices=list(SURFACE_ORDER), help="redo only the rows assigned to this surface")
    ap.add_argument("--as", dest="as_surface", choices=["ru_mix", "ru_pure"], help="translate into this surface instead")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    rows = load_shard_rows(args.in_dir)
    if not rows:
        log.error("no rows in %s", args.in_dir)
        return 1
    tcfg = cfg.model_copy(update={"temperature": cfg.translate_temperature, "top_p": 0.9,
                                  "max_new_tokens": cfg.translate_max_new_tokens})
    backend = args.backend or cfg.backend
    generate = make_vllm_backend(tcfg) if backend == "vllm" else make_hf_backend(tcfg)
    counts = run_translate(rows, generate, args.out, cfg.translate_surface_share, cfg.translate_batch, cfg.seed,
                           only=args.only, as_surface=args.as_surface)
    log.info("done: %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
