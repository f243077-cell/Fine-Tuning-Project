"""Dataset v1.1 (D42): add human-written Roman Urdu SAFE rows from public datasets to dataset v1.

    python -m training.add_external --config training/configs/external.yaml

The rows are real comments, so they are labeled SAFE (no injection), with source `user_input` and origin
`external`. The surface (`ru_pure` / `ru_mix`) comes from the same language heuristic as the build. Rows go
through the length, denylist, leakage (seeds + test), and near-duplicate checks. Half of them replace synthetic
plain SAFE `user_input` rows, and the rest are added.
"""

import argparse
import csv
import json
import logging
import random
import re
from collections import Counter
from pathlib import Path

import yaml
from pydantic import BaseModel

from training.build_dataset import (EN_MARKERS, NON_LATIN_SCRIPT_RE, RU_MARKERS, WORD_RE, LangConfig,
                                    SimilarityIndex, has_trigger, load_denylist, max_similarity, shingles,
                                    verify_test_lock)
from training.jsonl import content_sha256, dataset_sha256, read_rows, write_rows
from training.normalize import normalize_text
from training.schemas import DataRow

log = logging.getLogger("add_external")


class SourceConfig(BaseModel):
    """One public dataset to import."""

    name: str
    path: str
    format: str  # "uci" (no header: sentence, sentiment) or "abuse" (id, comment, label)
    take: dict[str, int]


class ExternalConfig(BaseModel):
    """Settings from training/configs/external.yaml."""

    processed_dir: str
    seeds_path: str
    test_path: str
    denylist_path: str
    seed: int = 1234
    min_chars: int = 20
    max_chars: int = 400
    min_tokens: int = 4
    ngram: int = 5
    leak_threshold: float = 0.5
    near_dup_threshold: float = 0.8
    val_share: float = 0.11
    replace_share: float = 0.5
    lang: LangConfig = LangConfig()
    sources: list[SourceConfig]


def read_source(src: SourceConfig) -> list[tuple[str, str]]:
    """(text, group) pairs; group is the sentiment or the H/O label."""
    with open(src.path, encoding="utf-8", errors="replace", newline="") as f:
        rows = list(csv.reader(f))
    if src.format == "abuse":
        return [(r[1], r[2].strip()) for r in rows[1:] if len(r) >= 3]
    return [(r[0], r[1].strip().lower()) for r in rows if len(r) >= 2]


def detect_surface(text: str, cfg: ExternalConfig) -> str | None:
    """ru_pure, ru_mix, en, or None (too short, non-Latin script, or unclear)."""
    norm = normalize_text(text)
    if NON_LATIN_SCRIPT_RE.search(norm):
        return None
    words = WORD_RE.findall(norm)
    if len(words) < cfg.min_tokens:
        return None
    ru = sum(w in RU_MARKERS for w in words) / len(words)
    en = sum(w in EN_MARKERS for w in words) / len(words)
    if ru >= cfg.lang.ru_pure_min_ru and en <= cfg.lang.ru_pure_max_en:
        return "ru_pure"
    if ru >= cfg.lang.ru_mix_min_ru:
        return "ru_mix"
    if ru <= cfg.lang.en_max_ru:
        return "en"
    return None


BROKEN_RE = re.compile("[\x80-\x9f�]")  # C1 controls or replacement chars: encoding damage in the source


def clean_text(text: str) -> str:
    """Collapse whitespace, or return "" if the text has encoding damage (the row is then skipped)."""
    return "" if BROKEN_RE.search(text) else re.sub(r"\s+", " ", text).strip()


def select_rows(cfg: ExternalConfig, existing: list[DataRow], reference: list[DataRow],
                rng: random.Random) -> tuple[list[DataRow], dict]:
    """Pick rows per source and surface quota after all filters."""
    deny = load_denylist(Path(cfg.denylist_path))
    stats: Counter = Counter()
    seen = {normalize_text(r.text) for r in existing + reference}
    ref_sets = [shingles(r.text, cfg.ngram) for r in reference]
    old_sets = [shingles(r.text, cfg.ngram) for r in existing]
    leak = SimilarityIndex(cfg.leak_threshold, Counter(g for s in ref_sets for g in s))
    for s in ref_sets:
        leak.add(s)
    within = SimilarityIndex(cfg.near_dup_threshold, Counter(g for s in old_sets for g in s))
    for s in old_sets:
        within.add(s)
    picked: list[DataRow] = []
    for src in cfg.sources:
        items = list(enumerate(read_source(src)))
        rng.shuffle(items)
        groups = sorted({g for _, (_, g) in items})
        # Quota per (surface, group): even split across groups for the abuse set (H / O), none for UCI.
        quota = {(s, g): n // len(groups) + (i < n % len(groups))
                 for s, n in src.take.items() for i, g in enumerate(groups)} if src.format == "abuse" \
            else {(s, None): n for s, n in src.take.items()}
        for idx, (raw, group) in items:
            text = clean_text(raw)
            norm = normalize_text(text)
            surface = detect_surface(text, cfg)
            key = (surface, group if src.format == "abuse" else None)
            if quota.get(key, 0) <= 0:
                stats[f"{src.name}:skipped_surface_or_full"] += 1
                continue
            if not cfg.min_chars <= len(norm) <= cfg.max_chars:
                stats[f"{src.name}:length"] += 1
            elif deny.search(norm):
                stats[f"{src.name}:denylist"] += 1
            elif norm in seen:
                stats[f"{src.name}:exact_duplicate"] += 1
            else:
                s = shingles(text, cfg.ngram)
                if leak.best_match(s) > 0:
                    stats[f"{src.name}:leak_seed_or_test"] += 1
                elif within.best_match(s) > 0:
                    stats[f"{src.name}:near_duplicate"] += 1
                else:
                    seen.add(norm)
                    within.add(s)
                    quota[key] -= 1
                    picked.append(DataRow(id=f"ext-{src.name}-{idx:05d}", text=text, source="user_input",
                                          label="SAFE", surface=surface, origin="external",
                                          hard_negative=has_trigger(text)))
        stats[f"{src.name}:short_of_quota"] = sum(v for v in quota.values() if v > 0)
    return sorted(picked, key=lambda r: r.id), dict(stats)


def merge(split_rows: list[DataRow], new: list[DataRow], replace_share: float,
          rng: random.Random) -> tuple[list[DataRow], list[str]]:
    """Add new rows; drop round(len(new) * replace_share) synthetic plain SAFE user_input rows."""
    pool = [r for r in split_rows if r.origin == "synthetic" and r.label == "SAFE"
            and r.source == "user_input" and not r.hard_negative]
    drop = {r.id for r in rng.sample(pool, min(len(pool), round(len(new) * replace_share)))}
    kept = [r for r in split_rows if r.id not in drop] + new
    return sorted(kept, key=lambda r: r.id), sorted(drop)


def run(cfg: ExternalConfig) -> dict:
    """Write the new train.jsonl / val.jsonl and external_report.json."""
    verify_test_lock(Path(cfg.test_path))
    out = Path(cfg.processed_dir)
    train, e1 = read_rows(out / "train.jsonl")
    val, e2 = read_rows(out / "val.jsonl")
    seeds, e3 = read_rows(Path(cfg.seeds_path))
    test, e4 = read_rows(Path(cfg.test_path))
    if e1 or e2 or e3 or e4:
        raise SystemExit(f"input files have errors: {(e1 + e2 + e3 + e4)[:3]}")
    if any(r.origin == "external" for r in train + val):
        raise SystemExit("external rows are already present; refusing to add them twice")
    rng = random.Random(cfg.seed)
    new, stats = select_rows(cfg, train + val, seeds + test, rng)
    n_val = round(len(new) * cfg.val_share)
    order = list(new)
    rng.shuffle(order)
    new_val, new_train = sorted(order[:n_val], key=lambda r: r.id), sorted(order[n_val:], key=lambda r: r.id)
    train2, drop_train = merge(train, new_train, cfg.replace_share, rng)
    val2, drop_val = merge(val, new_val, cfg.replace_share, rng)
    write_rows(out / "train.jsonl", train2)
    write_rows(out / "val.jsonl", val2)
    th, vh = content_sha256(out / "train.jsonl"), content_sha256(out / "val.jsonl")
    report = {
        "added": {"train": len(new_train), "val": len(new_val)},
        "by_source_surface": dict(Counter(f"{r.id.split('-')[1]}|{r.surface}" for r in new)),
        "hard_negative": sum(r.hard_negative for r in new),
        "replaced_synthetic_ids": {"train": drop_train, "val": drop_val},
        "filter_stats": stats,
        "rows": {"train": len(train2), "val": len(val2)},
        "label": {"train": dict(Counter(r.label for r in train2)), "val": dict(Counter(r.label for r in val2))},
        "surface": {"train": dict(Counter(r.surface for r in train2)), "val": dict(Counter(r.surface for r in val2))},
        "max_jaccard_new_vs_test": max_similarity(new, test, cfg.ngram),
        "max_jaccard_new_vs_seeds": max_similarity(new, seeds, cfg.ngram),
        "sha256": {"train": th, "val": vh, "dataset": dataset_sha256(th, vh)},
        "test_lock_verified": True,
        "config": cfg.model_dump(),
    }
    (out / "external_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = ExternalConfig.model_validate(yaml.safe_load(args.config.read_text(encoding="utf-8")))
    r = run(cfg)
    log.info("added %s, by source/surface %s", r["added"], r["by_source_surface"])
    log.info("rows %s, labels %s", r["rows"], r["label"])
    log.info("max Jaccard new vs test %.3f, dataset sha256 %s", r["max_jaccard_new_vs_test"], r["sha256"]["dataset"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
