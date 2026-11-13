"""Read and write DataRow JSONL files with line-level error reporting."""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from training.schemas import DataRow


def content_sha256(path: Path) -> str:
    """SHA-256 of the file with CRLF folded to LF, so Windows and Linux checkouts agree."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dataset_sha256(train_hash: str, val_hash: str) -> str:
    """One dataset hash from the train and val file hashes (recorded in DATA_CARD.md)."""
    return hashlib.sha256(f"{train_hash}\n{val_hash}\n".encode()).hexdigest()


def format_validation_error(err: ValidationError) -> str:
    """Turn a Pydantic error into one short readable line."""
    parts = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "row"
        parts.append(f"{loc}: {e['msg'].removeprefix('Value error, ')}")
    return "; ".join(parts)


def read_rows(path: Path) -> tuple[list[DataRow], list[str]]:
    """Parse a JSONL file; return valid rows and 'line N: problem' errors."""
    rows: list[DataRow] = []
    errors: list[str] = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rows.append(DataRow.model_validate(json.loads(line)))
            except json.JSONDecodeError as e:
                errors.append(f"line {n}: invalid JSON ({e.msg})")
            except ValidationError as e:
                errors.append(f"line {n}: {format_validation_error(e)}")
    return rows, errors


def write_rows(path: Path, rows: Iterable[DataRow]) -> int:
    """Write rows as UTF-8 JSONL with LF line endings; return the count."""
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False) + "\n")
            count += 1
    return count
