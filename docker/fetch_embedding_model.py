"""Download Chroma's default embedding model (all-MiniLM-L6-v2 ONNX) with resume and retries, then verify it.

Chroma's own downloader gives up on slow links (read timeout). This script writes the archive to the path Chroma
expects (~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx.tar.gz); Chroma checks the SHA-256 and extracts it.
"""

import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
SHA256 = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"
DEST = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2" / "onnx.tar.gz"


def sha256(path: Path) -> str:
    """Hex SHA-256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(attempts: int = 30) -> None:
    """Resume the download until the file is complete and its hash matches."""
    DEST.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        if DEST.exists() and sha256(DEST) == SHA256:
            print(f"ok {DEST}")
            return
        have = DEST.stat().st_size if DEST.exists() else 0
        req = urllib.request.Request(URL, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r, DEST.open("ab" if r.status == 206 else "wb") as f:
                while block := r.read(1 << 16):
                    f.write(block)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"attempt {attempt}: {exc}; resuming", file=sys.stderr)
            time.sleep(3)
        if DEST.exists() and DEST.stat().st_size > 0 and sha256(DEST) != SHA256 and attempt % 10 == 0:
            DEST.unlink()  # a corrupt partial file: start over
    raise SystemExit("could not download the embedding model")


if __name__ == "__main__":
    fetch()
