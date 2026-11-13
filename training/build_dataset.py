"""Filter, deduplicate, decontaminate, balance, and split synthetic rows into train/val JSONL.

    python -m training.build_dataset --config training/configs/build.yaml
"""

import argparse
import glob
import json
import logging
import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel

from training.jsonl import content_sha256, dataset_sha256, read_rows, write_rows
from training.normalize import normalize_text
from training.schemas import DataRow

log = logging.getLogger("build_dataset")

RU_MARKERS = frozenset(
    "hai hain hy nahi nahin nai ni kya kia ko ki ka ke se mein main mai aur yeh ye woh wo karo kro "
    "kar jo bhi tum tumhara tumhari tumhare aap apna apni apne mujhe mujhy mjhe sirf ab sab kuch liye "
    "par tak hum hamara raha rahi rahe gaya gayi diya wala wali wale kaise kyun kyu bata batao dikhao "
    "bhejo chahiye hota hoti hoga hogi tha thi thay jab agar lekin phir abhi pehle baad mera meri mere "
    "iss uss jis kis yahan wahan kahan kuchh zara saari sara saare kaam baat".split()
)
EN_MARKERS = frozenset(
    "the are and of you your please this that with for what how all any from it be can will my an not "
    "should would now only just have has was were which their they we our there here been".split()
)
WORD_RE = re.compile(r"[a-z']+")
NON_LATIN_SCRIPT_RE = re.compile(r"[֐-ࣿऀ-෿぀-ヿ一-鿿가-힯]")


class LangConfig(BaseModel):
    """Thresholds for the language-mix heuristic."""

    en_max_ru: float = 0.06
    ru_mix_min_ru: float = 0.12
    ru_pure_min_ru: float = 0.20
    ru_pure_max_en: float = 0.10
    tool_output_factor: float = 0.5
    min_tokens: int = 3


class BuildConfig(BaseModel):
    """Settings from training/configs/build.yaml."""

    synthetic_glob: str
    seeds_path: str
    test_path: str
    out_dir: str
    denylist_path: str
    min_chars: int = 15
    max_chars: int = 1000
    ngram: int = 5
    near_dup_threshold: float = 0.8
    leak_threshold: float = 0.5
    lang: LangConfig = LangConfig()
    train_size: int = 4000
    val_size: int = 500
    hard_negative_min_share_of_safe: float = 0.5
    seed: int = 1234


@dataclass
class Report:
    """Counts collected while building, written to build_report.json."""

    input_rows: int = 0
    parse_errors: list[str] = field(default_factory=list)
    dropped: Counter = field(default_factory=Counter)
    extra: dict = field(default_factory=dict)


def shingles(text: str, n: int) -> frozenset[str]:
    """Character n-grams of the normalized text."""
    t = normalize_text(text)
    if len(t) <= n:
        return frozenset([t])
    return frozenset(t[i:i + n] for i in range(len(t) - n + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity of two sets."""
    if not a and not b:
        return 1.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


class SimilarityIndex:
    """Exact Jaccard >= threshold lookup using prefix filtering (rare n-grams first)."""

    def __init__(self, threshold: float, freq: Counter):
        self.t = threshold
        self.freq = freq
        self.sets: list[frozenset[str]] = []
        self.index: dict[str, list[int]] = defaultdict(list)

    def _prefix(self, s: frozenset[str]) -> list[str]:
        """Rarest tokens that any set with Jaccard >= t must share with s."""
        ordered = sorted(s, key=lambda g: (self.freq[g], g))
        return ordered[: len(ordered) - math.ceil(self.t * len(ordered)) + 1]

    def add(self, s: frozenset[str]) -> None:
        """Index one set."""
        i = len(self.sets)
        self.sets.append(s)
        for g in self._prefix(s):
            self.index[g].append(i)

    def best_match(self, s: frozenset[str]) -> float:
        """Highest Jaccard >= t against indexed sets, or 0.0 if none reaches t."""
        seen: set[int] = set()
        best = 0.0
        for g in self._prefix(s):
            for i in self.index.get(g, ()):
                if i not in seen:
                    seen.add(i)
                    j = jaccard(s, self.sets[i])
                    if j >= self.t and j > best:
                        best = j
        return best


def load_denylist(path: Path) -> re.Pattern[str]:
    """Compile denylist terms into one word-start regex."""
    terms = yaml.safe_load(path.read_text(encoding="utf-8"))["terms"]
    alts = "|".join(re.escape(normalize_text(t)) for t in terms)
    return re.compile(rf"(?<![a-z])(?:{alts})")


def language_ok(row: DataRow, cfg: LangConfig) -> bool:
    """Check that the text's language mix matches its surface label."""
    norm = normalize_text(row.text)
    if NON_LATIN_SCRIPT_RE.search(norm):
        return False
    words = WORD_RE.findall(norm)
    if len(words) < cfg.min_tokens:
        return False
    ru = sum(w in RU_MARKERS for w in words) / len(words)
    en = sum(w in EN_MARKERS for w in words) / len(words)
    # Tool outputs carry JSON keys, ids, and numbers, so the Roman Urdu minimum is relaxed.
    factor = cfg.tool_output_factor if row.source == "tool_output" else 1.0
    if row.surface == "en":
        return ru <= cfg.en_max_ru
    if row.surface == "ru_mix":
        return ru >= cfg.ru_mix_min_ru * factor
    return ru >= cfg.ru_pure_min_ru * factor and en <= cfg.ru_pure_max_en


def verify_test_lock(test_path: Path) -> None:
    """Refuse to run if the frozen test set does not match its lock."""
    lock = test_path.with_suffix(".lock")
    if not lock.exists():
        raise SystemExit(f"no lock at {lock}; the test set must be locked before building")
    expected = lock.read_text(encoding="utf-8").split()[0]
    if content_sha256(test_path) != expected:
        raise SystemExit(f"HASH MISMATCH for {test_path}; the frozen test set changed. Tell the owner.")


def load_synthetic(pattern: str, report: Report) -> list[DataRow]:
    """Read all shards; schema errors are counted and reported."""
    rows: list[DataRow] = []
    for path in sorted(glob.glob(pattern)):
        got, errors = read_rows(Path(path))
        rows.extend(got)
        report.parse_errors.extend(f"{Path(path).name} {e}" for e in errors)
    report.input_rows = len(rows) + len(report.parse_errors)
    report.dropped["schema"] = len(report.parse_errors)
    return [r for r in rows if r.origin == "synthetic"]


def filter_rows(rows: list[DataRow], cfg: BuildConfig, deny: re.Pattern[str], report: Report) -> list[DataRow]:
    """Apply length, denylist, language-mix, and exact-duplicate filters (in that order)."""
    kept: list[DataRow] = []
    seen_text: set[str] = set()
    for r in sorted(rows, key=lambda r: r.id):
        norm = normalize_text(r.text)
        if not cfg.min_chars <= len(norm) <= cfg.max_chars:
            report.dropped["length"] += 1
        elif deny.search(norm):
            report.dropped["denylist"] += 1
        elif not language_ok(r, cfg.lang):
            report.dropped["language_mix"] += 1
        elif norm in seen_text:
            report.dropped["exact_duplicate"] += 1
        else:
            seen_text.add(norm)
            kept.append(r)
    return kept


def remove_near_duplicates(rows: list[DataRow], reference: list[DataRow], cfg: BuildConfig,
                           report: Report) -> list[DataRow]:
    """Drop rows too close to seeds/test (leakage) or to an earlier kept row."""
    sets = [shingles(r.text, cfg.ngram) for r in rows]
    ref_sets = [shingles(r.text, cfg.ngram) for r in reference]
    freq: Counter = Counter(g for s in (*sets, *ref_sets) for g in s)
    leak = SimilarityIndex(cfg.leak_threshold, freq)
    for s in ref_sets:
        leak.add(s)
    within = SimilarityIndex(cfg.near_dup_threshold, freq)
    kept: list[DataRow] = []
    for r, s in zip(rows, sets):
        if leak.best_match(s) > 0:
            report.dropped["leak_seed_or_test"] += 1
        elif within.best_match(s) > 0:
            report.dropped["near_duplicate"] += 1
        else:
            within.add(s)
            kept.append(r)
    return kept


def max_similarity(rows: Iterable[DataRow], reference: list[DataRow], n: int) -> float:
    """Brute-force maximum Jaccard between any row and any reference row (for the report)."""
    ref = [shingles(r.text, n) for r in reference]
    best = 0.0
    for r in rows:
        s = shingles(r.text, n)
        for t in ref:
            best = max(best, jaccard(s, t))
    return round(best, 4)


def balance(rows: list[DataRow], cfg: BuildConfig, rng: random.Random) -> list[DataRow]:
    """Downsample to 50% injection / 50% safe with the hard-negative share kept, capped at train+val."""
    inj = [r for r in rows if r.label == "INJECTION"]
    hn = [r for r in rows if r.label == "SAFE" and r.hard_negative]
    plain = [r for r in rows if r.label == "SAFE" and not r.hard_negative]
    half = min((cfg.train_size + cfg.val_size) // 2, len(inj), len(hn) + len(plain))
    hn_take = min(len(hn), max(half - len(plain), math.ceil(half * cfg.hard_negative_min_share_of_safe)))
    plain_take = min(len(plain), half - hn_take)
    hn_take = half - plain_take
    picked = rng.sample(inj, half) + rng.sample(hn, hn_take) + rng.sample(plain, plain_take)
    return sorted(picked, key=lambda r: r.id)


def cell_of(r: DataRow) -> str:
    """Stratification key."""
    return f"{r.label}|{r.attack_type}|{r.surface}|{r.source}|{r.hard_negative}"


def split(rows: list[DataRow], cfg: BuildConfig, rng: random.Random) -> tuple[list[DataRow], list[DataRow]]:
    """Stratified train/val split by cell; deterministic for a given seed."""
    frac = cfg.val_size / (cfg.train_size + cfg.val_size)
    by_cell: dict[str, list[DataRow]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r.id):
        by_cell[cell_of(r)].append(r)
    train: list[DataRow] = []
    val: list[DataRow] = []
    for key in sorted(by_cell):
        group = by_cell[key]
        rng.shuffle(group)
        k = round(len(group) * frac)
        val.extend(group[:k])
        train.extend(group[k:])
    return sorted(train, key=lambda r: r.id), sorted(val, key=lambda r: r.id)


def counts(rows: list[DataRow]) -> dict:
    """Summary counts for the report and data card."""
    return {
        "rows": len(rows),
        "label": dict(Counter(r.label for r in rows)),
        "attack_type": dict(Counter(r.attack_type for r in rows if r.attack_type)),
        "surface": dict(Counter(r.surface for r in rows)),
        "source": dict(Counter(r.source for r in rows)),
        "hard_negative": sum(r.hard_negative for r in rows),
        "cells": dict(sorted(Counter(cell_of(r) for r in rows).items())),
    }


def build(cfg: BuildConfig) -> dict:
    """Run the whole pipeline and write train.jsonl, val.jsonl, and build_report.json."""
    test_path = Path(cfg.test_path)
    verify_test_lock(test_path)
    report = Report()
    seeds, seed_err = read_rows(Path(cfg.seeds_path))
    test, test_err = read_rows(test_path)
    if seed_err or test_err:
        raise SystemExit(f"reference files have errors: {(seed_err + test_err)[:3]}")
    rows = load_synthetic(cfg.synthetic_glob, report)
    if not rows:
        raise SystemExit(f"no synthetic rows match {cfg.synthetic_glob}")
    rows = filter_rows(rows, cfg, load_denylist(Path(cfg.denylist_path)), report)
    rows = remove_near_duplicates(rows, seeds + test, cfg, report)
    clean = len(rows)
    rng = random.Random(cfg.seed)
    rows = balance(rows, cfg, rng)
    report.dropped["balance_cap"] = clean - len(rows)
    train, val = split(rows, cfg, rng)
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / "train.jsonl", train)
    write_rows(out / "val.jsonl", val)
    train_hash, val_hash = content_sha256(out / "train.jsonl"), content_sha256(out / "val.jsonl")
    result = {
        "input_rows": report.input_rows,
        "dropped": dict(report.dropped),
        "parse_errors_sample": report.parse_errors[:10],
        "clean_rows_before_balance": clean,
        "train": counts(train),
        "val": counts(val),
        "max_jaccard_vs_test": max_similarity(train + val, test, cfg.ngram),
        "max_jaccard_vs_seeds": max_similarity(train + val, seeds, cfg.ngram),
        "sha256": {"train": train_hash, "val": val_hash,
                   "dataset": dataset_sha256(train_hash, val_hash)},
        "test_lock_verified": True,
        "config": cfg.model_dump(),
    }
    (out / "build_report.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = BuildConfig.model_validate(yaml.safe_load(args.config.read_text(encoding="utf-8")))
    r = build(cfg)
    log.info("input %d, dropped %s", r["input_rows"], r["dropped"])
    log.info("train %d, val %d, max Jaccard vs test %.3f", r["train"]["rows"], r["val"]["rows"],
             r["max_jaccard_vs_test"])
    log.info("dataset sha256 %s", r["sha256"]["dataset"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
