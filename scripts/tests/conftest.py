"""Shared fixtures for script tests: tiny CSV and JSONL builders."""

import csv
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.csv_to_jsonl import COLUMNS


@pytest.fixture
def write_csv(tmp_path: Path) -> Callable[[list[dict], str], Path]:
    """Write CSV rows (missing columns filled with '') and return the path."""
    def _write(rows: list[dict], name: str = "in.csv") -> Path:
        p = tmp_path / name
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in COLUMNS})
        return p
    return _write


@pytest.fixture
def write_jsonl(tmp_path: Path) -> Callable[[list[dict], str], Path]:
    """Write raw dict rows to JSONL and return the path."""
    def _write(rows: list[dict], name: str = "rows.jsonl") -> Path:
        p = tmp_path / name
        with p.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return p
    return _write
