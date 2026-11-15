"""SQLite audit log and quarantine (Architecture.md section 9).

audit_log stores a keyed hash (HMAC-SHA256 with AUDIT_SALT) and the length of each text, never the text.
quarantine stores flagged retrieved chunks after PII masking.
"""

import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("guard.audit")

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, request_id TEXT NOT NULL,
  source TEXT NOT NULL, text_hmac TEXT NOT NULL, text_len INTEGER NOT NULL,
  verdict TEXT NOT NULL, attack_type TEXT, action TEXT NOT NULL,
  model TEXT NOT NULL, latency_ms INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS quarantine (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, doc_id TEXT, chunk_id TEXT,
  masked_text TEXT NOT NULL, attack_type TEXT, reviewed INTEGER NOT NULL DEFAULT 0);
"""


@dataclass(frozen=True)
class AuditRow:
    """One audit_log row (no raw text)."""

    request_id: str
    source: str
    text_hmac: str
    text_len: int
    verdict: str
    attack_type: str | None
    action: str
    model: str
    latency_ms: int


def text_hmac(text: str, salt: str) -> str:
    """Keyed hash of the text (hex)."""
    return hmac.new(salt.encode(), text.encode(), hashlib.sha256).hexdigest()


def _now() -> str:
    """UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class AuditStore:
    """Thread-safe SQLite writer for audit and quarantine rows."""

    def __init__(self, db_path: str, salt: str) -> None:
        """Open (and create) the database; an empty salt is replaced by a random one for this process."""
        if not salt:
            logger.warning("AUDIT_SALT is not set: using a random salt, so hashes change on every restart")
            salt = secrets.token_hex(32)
        self.salt = salt
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._db.commit()

    def hash(self, text: str) -> str:
        """Keyed hash with this store's salt."""
        return text_hmac(text, self.salt)

    def log(self, row: AuditRow) -> None:
        """Insert one audit row."""
        with self._lock:
            self._db.execute(
                "INSERT INTO audit_log (ts, request_id, source, text_hmac, text_len, verdict, attack_type, action,"
                " model, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), row.request_id, row.source, row.text_hmac, row.text_len, row.verdict, row.attack_type,
                 row.action, row.model, row.latency_ms))
            self._db.commit()

    def quarantine(self, masked_text: str, attack_type: str | None, doc_id: str | None, chunk_id: str | None) -> None:
        """Insert one quarantine row; the text must already be PII-masked."""
        with self._lock:
            self._db.execute(
                "INSERT INTO quarantine (ts, doc_id, chunk_id, masked_text, attack_type) VALUES (?, ?, ?, ?, ?)",
                (_now(), doc_id, chunk_id, masked_text, attack_type))
            self._db.commit()

    def stats(self) -> dict:
        """Counts by verdict, source, source x verdict, action, and the quarantine size."""
        with self._lock:
            rows = self._db.execute(
                "SELECT source, verdict, action, COUNT(*) FROM audit_log GROUP BY source, verdict, action").fetchall()
            quarantined = self._db.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
        out: dict = {"total": 0, "by_verdict": {}, "by_source": {}, "by_source_verdict": {}, "by_action": {},
                     "quarantined": quarantined}
        for source, verdict, action, n in rows:
            out["total"] += n
            out["by_verdict"][verdict] = out["by_verdict"].get(verdict, 0) + n
            out["by_source"][source] = out["by_source"].get(source, 0) + n
            out["by_action"][action] = out["by_action"].get(action, 0) + n
            sv = out["by_source_verdict"].setdefault(source, {})
            sv[verdict] = sv.get(verdict, 0) + n
        return out

    def fetch_all(self, table: str) -> list[tuple]:
        """Every row of a table (tests and inspection)."""
        if table not in ("audit_log", "quarantine"):
            raise ValueError(table)
        with self._lock:
            return self._db.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 (fixed names)

    def close(self) -> None:
        """Close the connection."""
        with self._lock:
            self._db.close()
