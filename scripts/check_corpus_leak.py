"""Near-duplicate check of demo texts against the frozen test set (read-only), Phase 7.

    python scripts/check_corpus_leak.py                      # demo_rag corpus, poisoned docs, attack suite, golden set
    python scripts/check_corpus_leak.py path/to/file.md ...  # specific files

Each paragraph (and each YAML string field) is compared with every test row by character 5-gram Jaccard after
normalize_text, with the same leak threshold as the dataset build (0.5). Exits 1 when any pair reaches it.
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from training.build_dataset import jaccard, shingles, verify_test_lock  # noqa: E402
from training.jsonl import read_rows  # noqa: E402

TEST = REPO / "data" / "eval" / "test.jsonl"
NGRAM, THRESHOLD = 5, 0.5
DEFAULT_PATHS = [REPO / "demo_rag" / "corpus", REPO / "demo_rag" / "corpus_poisoned",
                 REPO / "evals" / "attack_suite.yaml", REPO / "evals" / "golden_set.yaml",
                 REPO / "gateway" / "notes", REPO / "evals" / "promptfoo",
                 REPO / "flutter_app" / "assets" / "samples.json"]


def _yaml_strings(node: object) -> list[str]:
    """Every string value in a YAML document."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _yaml_strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _yaml_strings(v)]
    return []


def texts_of(path: Path) -> list[tuple[str, str]]:
    """(label, text) pieces: paragraphs of .md/.txt files, string fields of .yaml files."""
    if path.is_dir():
        return [t for p in sorted(path.rglob("*")) if p.is_file() for t in texts_of(p)]
    if path.suffix in (".yaml", ".yml"):
        strings = _yaml_strings(yaml.safe_load(path.read_text(encoding="utf-8")))
        return [(f"{path.name}#{i}", s) for i, s in enumerate(strings) if len(s) >= 20]
    if path.suffix == ".json":
        strings = _yaml_strings(json.loads(path.read_text(encoding="utf-8")))
        return [(f"{path.name}#{i}", s) for i, s in enumerate(strings) if len(s) >= 20]
    if path.suffix in (".md", ".txt"):
        paras = [p.strip() for p in path.read_text(encoding="utf-8").split("\n\n")]
        return [(f"{path.name}#{i}", p) for i, p in enumerate(paras) if len(p) >= 20]
    return []


def check(paths: list[Path]) -> list[tuple[str, str, float]]:
    """(piece, test id, similarity) for every pair at or above the threshold."""
    verify_test_lock(TEST)
    rows, errors = read_rows(TEST)
    if errors:
        raise SystemExit(f"test set errors: {errors[:3]}")
    test_sets = [(r.id, shingles(r.text, NGRAM)) for r in rows]
    hits = []
    for p in paths:
        if not p.exists():
            continue
        for label, text in texts_of(p):
            s = shingles(text, NGRAM)
            for tid, ts in test_sets:
                j = jaccard(s, ts)
                if j >= THRESHOLD:
                    hits.append((label, tid, round(j, 3)))
    return hits


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", type=Path)
    args = ap.parse_args(argv)
    paths = args.paths or DEFAULT_PATHS
    hits = check(paths)
    pieces = sum(len(texts_of(p)) for p in paths if p.exists())
    for h in hits:
        print(f"LEAK {h[0]} ~ {h[1]} (jaccard {h[2]})")
    print(f"checked {pieces} pieces against {TEST.name}: {len(hits)} at or above {THRESHOLD}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
