"""Chroma vector store with Chroma's built-in default embedding function (no extra dependency)."""

from pathlib import Path

import chromadb

from demo_rag.chunking import Chunk


def open_collection(path: str, name: str, reset: bool = False):  # type: ignore[no-untyped-def]
    """Persistent collection (default embedding function); reset drops it first."""
    Path(path).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=path)
    if reset:
        try:
            client.delete_collection(name)
        except Exception:  # noqa: BLE001 (chromadb raises different types across versions when it is missing)
            pass
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def add_chunks(collection, chunks: list[Chunk]) -> None:  # type: ignore[no-untyped-def]
    """Embed and store chunks with their metadata."""
    if not chunks:
        return
    collection.add(ids=[c.chunk_id for c in chunks], documents=[c.text for c in chunks],
                   metadatas=[{"doc_id": c.doc_id, "title": c.title, "lang": c.lang, "poisoned": c.poisoned}
                              for c in chunks])


def make_retriever(collection):  # type: ignore[no-untyped-def]
    """Retriever(question, k) -> chunk dicts in rank order."""
    def retrieve(question: str, k: int) -> list[dict]:
        res = collection.query(query_texts=[question], n_results=k)
        out = []
        for cid, text, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                         res["distances"][0]):
            out.append({"chunk_id": cid, "doc_id": meta["doc_id"], "title": meta["title"], "text": text,
                        "lang": meta["lang"], "distance": float(dist)})
        return out
    return retrieve
