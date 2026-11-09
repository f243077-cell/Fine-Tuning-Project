"""Validate a data JSONL file: schema, duplicates, balance, coverage matrix, and intent triplets."""

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.jsonl import read_rows  # noqa: E402
from training.normalize import normalize_text  # noqa: E402
from training.schemas import AttackType, DataRow, Label, Origin, Source, Surface  # noqa: E402

ATTACKS = [a.value for a in AttackType]
SURFACES = [s.value for s in Surface]
SOURCES = [s.value for s in Source]
CLASSES = ATTACKS + ["SAFE"]
MAX_CHARS = 12000


@dataclass
class Report:
    """Findings of one validation run."""

    kind: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def row_class(row: DataRow) -> str:
    """Coverage class of a row: its attack_type, or SAFE."""
    return row.attack_type if row.label == Label.INJECTION else "SAFE"


def detect_kind(rows: list[DataRow]) -> str:
    """seed, test, or synthetic, from the rows' origin (mixed counts as synthetic)."""
    origins = {r.origin for r in rows}
    return origins.pop() if len(origins) == 1 else Origin.SYNTHETIC.value


def coverage(rows: list[DataRow]) -> Counter:
    """Count rows per (class, surface, source)."""
    return Counter((row_class(r), r.surface, r.source) for r in rows)


def format_matrix(cov: Counter) -> str:
    """Render the class x (surface/source) coverage matrix as text."""
    cols = [(s, src) for s in SURFACES for src in SOURCES]
    short = {"user_input": "usr", "retrieved_chunk": "chk", "tool_output": "tool"}
    head = f"{'class':<13}" + "".join(f"{s + '/' + short[src]:>13}" for s, src in cols) + f"{'total':>8}"
    lines = [head]
    for c in CLASSES:
        counts = [cov[(c, s, src)] for s, src in cols]
        lines.append(f"{c:<13}" + "".join(f"{n:>13}" for n in counts) + f"{sum(counts):>8}")
    return "\n".join(lines)


def check_duplicates(rows: list[DataRow], rep: Report) -> None:
    """Duplicate ids, and identical normalized text for the same source."""
    for rid, n in Counter(r.id for r in rows).items():
        if n > 1:
            rep.errors.append(f"duplicate id {rid} ({n} rows)")
    by_text: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        by_text[(normalize_text(r.text), r.source)].append(r.id)
    for (_, src), ids in by_text.items():
        if len(ids) > 1:
            rep.errors.append(f"duplicate text for source {src}: {', '.join(ids)}")


def check_lengths(rows: list[DataRow], rep: Report) -> None:
    """Warn on texts longer than the service limit."""
    for r in rows:
        if len(r.text) > MAX_CHARS:
            rep.warnings.append(f"{r.id}: text has {len(r.text)} chars (> {MAX_CHARS})")


def required_cells(kind: str) -> list[tuple[str, str | None, str | None]]:
    """Cells (class, surface, source) that must be non-empty; None means any."""
    if kind == Origin.SEED:
        return [(c, s, None) for c in CLASSES for s in ("ru_mix", "ru_pure")]
    if kind == Origin.TEST:
        return ([(c, s, None) for c in CLASSES for s in SURFACES]
                + [(c, None, src) for c in CLASSES for src in SOURCES])
    return [(c, s, src) for c in CLASSES for s in SURFACES for src in SOURCES]


def check_coverage(rows: list[DataRow], rep: Report) -> None:
    """Flag empty required coverage cells."""
    cov = coverage(rows)
    for c, s, src in required_cells(rep.kind):
        n = sum(v for (kc, ks, ksrc), v in cov.items()
                if kc == c and (s is None or ks == s) and (src is None or ksrc == src))
        if n == 0:
            rep.errors.append(f"empty coverage cell: class={c} surface={s or 'any'} source={src or 'any'}")
    if rep.kind == Origin.TEST:
        for s in SURFACES:
            if not any(r.hard_negative and r.surface == s for r in rows):
                rep.errors.append(f"no hard negatives with surface={s}")


def check_intents(rows: list[DataRow], rep: Report) -> dict[str, list[DataRow]]:
    """Each test intent must have exactly one row per surface and consistent labels."""
    intents: dict[str, list[DataRow]] = defaultdict(list)
    for r in rows:
        if r.intent_id:
            intents[r.intent_id].append(r)
    if rep.kind != Origin.TEST:
        return intents
    for iid, group in sorted(intents.items()):
        surfaces = Counter(r.surface for r in group)
        missing = [s for s in SURFACES if surfaces[s] == 0]
        extra = [s for s, n in surfaces.items() if n > 1]
        if missing:
            rep.errors.append(f"intent {iid}: missing surface(s) {', '.join(missing)}")
        if extra:
            rep.errors.append(f"intent {iid}: more than one row for surface(s) {', '.join(extra)}")
        keys = {(r.label, r.attack_type, r.source, r.hard_negative) for r in group}
        if len(keys) > 1:
            rep.errors.append(f"intent {iid}: label/attack_type/source/hard_negative differ across surfaces")
    return intents


def check_targets(rows: list[DataRow], intents: dict[str, list[DataRow]], rep: Report) -> None:
    """Warn when counts miss the PRD section 10 targets."""
    cls = Counter(row_class(r) for r in rows)
    hard = sum(r.hard_negative for r in rows)
    if rep.kind == Origin.SEED:
        for a in ATTACKS:
            if cls[a] < 8:
                rep.warnings.append(f"seeds: {a} has {cls[a]} rows (target >= 8)")
        if cls["SAFE"] < 40:
            rep.warnings.append(f"seeds: {cls['SAFE']} benign rows (target 40)")
        if hard < 20:
            rep.warnings.append(f"seeds: {hard} hard negatives (target >= 20)")
    elif rep.kind == Origin.TEST:
        first = {iid: g[0] for iid, g in intents.items()}
        icls = Counter(row_class(r) for r in first.values())
        if len(rows) != 300:
            rep.warnings.append(f"test: {len(rows)} rows (target 300)")
        for a in ATTACKS:
            if icls[a] != 10:
                rep.warnings.append(f"test: {a} has {icls[a]} intents (target 10)")
        if icls["SAFE"] != 50:
            rep.warnings.append(f"test: {icls['SAFE']} benign intents (target 50)")
        hard_i = sum(r.hard_negative for r in first.values())
        if hard_i < 25:
            rep.warnings.append(f"test: {hard_i} hard-negative intents (target >= 25)")
        inj = [r for r in first.values() if r.label == Label.INJECTION]
        if inj:
            share = sum(r.source != Source.USER_INPUT for r in inj) / len(inj)
            rep.info.append(f"indirect share of injection intents: {share:.0%} (target about 40%)")
            if not 0.30 <= share <= 0.50:
                rep.warnings.append(f"test: indirect share {share:.0%} is outside 30% to 50%")


def validate(rows: list[DataRow], kind: str | None = None) -> Report:
    """Run every check and return a report."""
    rep = Report(kind=kind or detect_kind(rows))
    if not rows:
        rep.errors.append("no valid rows")
        return rep
    check_duplicates(rows, rep)
    check_lengths(rows, rep)
    check_coverage(rows, rep)
    intents = check_intents(rows, rep)
    check_targets(rows, intents, rep)
    labels = Counter(r.label for r in rows)
    rep.info.append(f"rows: {len(rows)}; labels: " + ", ".join(f"{k}={v}" for k, v in sorted(labels.items()))
                    + f"; hard negatives: {sum(r.hard_negative for r in rows)}; intents: {len(intents)}")
    rep.info.append("coverage (class x surface/source):\n" + format_matrix(coverage(rows)))
    return rep


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; exit 1 if any error is found."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path)
    p.add_argument("--kind", choices=[o.value for o in Origin], help="default: detected from origin")
    args = p.parse_args(argv)

    rows, parse_errors = read_rows(args.path)
    rep = validate(rows, args.kind)
    rep.errors[:0] = parse_errors
    print(f"{args.path} (kind: {rep.kind})")
    for line in rep.info:
        print(line)
    for w in rep.warnings:
        print(f"WARNING: {w}")
    for e in rep.errors:
        print(f"ERROR: {e}")
    print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
