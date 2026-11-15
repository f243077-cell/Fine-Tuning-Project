"""Token-based chunking with tiktoken and corpus loading."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import tiktoken

MIN_TOKENS, MAX_TOKENS, OVERLAP_TOKENS = 300, 800, 50
ENCODING = "cl100k_base"


@lru_cache(maxsize=1)
def encoder() -> tiktoken.Encoding:
    """The tiktoken encoding used for chunk sizes and the prompt budget."""
    return tiktoken.get_encoding(ENCODING)


def count_tokens(text: str) -> int:
    """Number of tokens in text."""
    return len(encoder().encode(text))


@dataclass(frozen=True)
class Doc:
    """One corpus document."""

    doc_id: str
    title: str
    text: str
    lang: str
    poisoned: bool


@dataclass(frozen=True)
class Chunk:
    """One chunk of a document."""

    chunk_id: str
    doc_id: str
    title: str
    text: str
    lang: str
    poisoned: bool


def load_docs(folder: str | Path, poisoned: bool = False) -> list[Doc]:
    """Markdown files in a folder; the first '# ' line is the title and the file stem is the doc id."""
    docs = []
    for p in sorted(Path(folder).glob("*.md")):
        raw = p.read_text(encoding="utf-8").strip()
        lines = raw.splitlines()
        title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else p.stem
        body = "\n".join(lines[1:]).strip() if lines and lines[0].startswith("#") else raw
        lang = "ru" if p.stem.startswith(("ru-", "p-ru-")) else "en"
        docs.append(Doc(doc_id=p.stem, title=title, text=body, lang=lang, poisoned=poisoned))
    return docs


def chunk_doc(doc: Doc, max_tokens: int = MAX_TOKENS, target: int = MIN_TOKENS + 200,
              overlap: int = OVERLAP_TOKENS) -> list[Chunk]:
    """One chunk when the doc fits in max_tokens; else windows of `target` tokens with `overlap`."""
    enc = encoder()
    ids = enc.encode(doc.text)
    if len(ids) <= max_tokens:
        pieces = [doc.text]
    else:
        step = target - overlap
        pieces = [enc.decode(ids[i:i + target]) for i in range(0, max(len(ids) - overlap, 1), step)]
    return [Chunk(chunk_id=f"{doc.doc_id}#{i}", doc_id=doc.doc_id, title=doc.title, text=t, lang=doc.lang,
                  poisoned=doc.poisoned) for i, t in enumerate(pieces)]
