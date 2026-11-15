"""Ingest the corpus into Chroma with the G0 guard scan (Architecture.md section 12).

    python -m demo_rag.ingest                       # corpus + poisoned docs, G0 on: flagged chunks are quarantined
    python -m demo_rag.ingest --guard off           # index everything (a "legacy" index; G2 protects at query time)
    python -m demo_rag.ingest --report              # also print the quarantine report
    python -m demo_rag.ingest --no-poisoned         # clean corpus only

G0 scans every chunk through client/ (source retrieved_chunk). guard-api stores flagged chunks PII-masked in its
quarantine table; this script keeps them out of the index and writes demo_rag/reports/ingest_report.json.
"""

import argparse
import json
import logging
from pathlib import Path

from client.ruguard_client import BatchItem, GuardClient
from demo_rag.chunking import Chunk, chunk_doc, count_tokens, load_docs
from demo_rag.config import PKG, get_settings
from demo_rag.store import add_chunks, open_collection

logger = logging.getLogger("demo_rag.ingest")
BATCH = 16


def scan_chunks(guard: GuardClient, chunks: list[Chunk]) -> list[dict]:
    """G0 verdict per chunk, in order."""
    out = []
    for i in range(0, len(chunks), BATCH):
        part = chunks[i:i + BATCH]
        res = guard.scan_batch([BatchItem(id=c.chunk_id, text=c.text, source="retrieved_chunk", doc_id=c.doc_id)
                                for c in part])
        out += [{"chunk_id": c.chunk_id, "doc_id": c.doc_id, "poisoned": c.poisoned, "verdict": r.verdict,
                 "attack_type": r.attack_type, "action": r.action, "flagged": r.flagged,
                 "scanner_error": r.scanner_error} for c, r in zip(part, res)]
    return out


def ingest(guard_on: bool, with_poisoned: bool, guard: GuardClient | None = None) -> dict:
    """Chunk, scan (G0), and index; returns the report."""
    s = get_settings()
    docs = load_docs(s.corpus_dir) + (load_docs(s.poisoned_dir, poisoned=True) if with_poisoned else [])
    chunks = [c for d in docs for c in chunk_doc(d)]
    scans = []
    if guard_on:
        guard = guard or GuardClient(s.guard_url, s.guard_api_key)
        scans = scan_chunks(guard, chunks)
        flagged = {x["chunk_id"] for x in scans if x["flagged"]}
    else:
        flagged = set()
    keep = [c for c in chunks if c.chunk_id not in flagged]
    collection = open_collection(s.chroma_path, s.collection, reset=True)
    add_chunks(collection, keep)
    tokens = [count_tokens(c.text) for c in chunks]
    report = {
        "guard": guard_on, "with_poisoned": with_poisoned, "docs": len(docs), "chunks": len(chunks),
        "indexed": len(keep), "quarantined": sorted(flagged),
        "chunk_tokens": {"min": min(tokens), "max": max(tokens)},
        "g0": {"poisoned_flagged": sum(1 for x in scans if x["poisoned"] and x["flagged"]),
               "poisoned_total": sum(1 for c in chunks if c.poisoned),
               "clean_flagged": sum(1 for x in scans if not x["poisoned"] and x["flagged"]),
               "clean_total": sum(1 for c in chunks if not c.poisoned)} if guard_on else None,
        "scans": scans,
    }
    out = PKG / "reports"
    out.mkdir(exist_ok=True)
    (out / "ingest_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def print_report(report: dict) -> None:
    """Human-readable quarantine report."""
    print(f"docs {report['docs']}, chunks {report['chunks']}, indexed {report['indexed']}, "
          f"guard {'on' if report['guard'] else 'off'}")
    if report["g0"]:
        g = report["g0"]
        print(f"G0: poisoned chunks flagged {g['poisoned_flagged']}/{g['poisoned_total']}, "
              f"clean chunks flagged {g['clean_flagged']}/{g['clean_total']}")
    for x in report["scans"]:
        if x["flagged"]:
            print(f"  quarantined {x['chunk_id']:<32} {x['attack_type'] or x['scanner_error']}"
                  f"{'' if x['poisoned'] else '  (clean doc: false positive)'}")
    missed = [x["chunk_id"] for x in report["scans"] if x["poisoned"] and not x["flagged"]]
    for m in missed:
        print(f"  missed      {m}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--guard", choices=["on", "off"], default="on")
    ap.add_argument("--no-poisoned", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    report = ingest(args.guard == "on", not args.no_poisoned)
    if args.report:
        print_report(report)
    else:
        print(f"indexed {report['indexed']} of {report['chunks']} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
