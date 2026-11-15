"""Gateway core (G5, Architecture.md section 11): allowlisted read-only tools, argument validation, timeouts,
result-size caps, and a guard scan of every tool result (source tool_output) with redaction of flagged results.

The MCP server (gateway/server.py) only wraps `Gateway.call`. Nothing here imports the guard or demo_rag;
the guard is reached over HTTP through client/, and search_docs opens the demo_rag Chroma index by path.
"""

import concurrent.futures
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("gateway")

HERE = Path(__file__).resolve().parent
REDACTED = "[REDACTED: possible prompt injection ({attack_type})]"
MAX_RESULT_CHARS = 4000
TIMEOUT_SECONDS = 60.0

class SearchArgs(BaseModel):
    """search_docs arguments."""

    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=3, ge=1, le=8)

class ScanArgs(BaseModel):
    """scan_text arguments."""

    text: str = Field(min_length=1, max_length=12000)
    source: Literal["user_input", "retrieved_chunk", "tool_output"] = "tool_output"

class NoteArgs(BaseModel):
    """get_note arguments."""

    id: str = Field(pattern=r"^[a-z0-9-]{1,32}$")

class ToolRefused(Exception):
    """The call is not allowed (unknown tool or invalid arguments)."""

@dataclass
class ToolSpec:
    """One allowlisted read-only tool."""

    args: type[BaseModel]
    fn: Callable[[Any], str]
    scan_result: bool = True
    description: str = ""

def read_note(note_id: str, notes_dir: Path = HERE / "notes") -> str:
    """Demo note text; notes are attacker-controllable by design."""
    path = notes_dir / f"{note_id}.txt"
    if not path.is_file():
        return f"No note with id {note_id}."
    return path.read_text(encoding="utf-8").strip()

def chroma_search(path: str, collection: str) -> Callable[[SearchArgs], str]:
    """search_docs over the demo_rag Chroma index (opened lazily, read-only use)."""
    state: dict[str, Any] = {}

    def search(a: SearchArgs) -> str:
        if "col" not in state:
            import chromadb  # local import: only needed when the tool is used
            state["col"] = chromadb.PersistentClient(path=path).get_collection(collection)
        res = state["col"].query(query_texts=[a.query], n_results=a.k)
        hits = [{"doc_id": m["doc_id"], "title": m["title"], "text": t}
                for t, m in zip(res["documents"][0], res["metadatas"][0])]
        return json.dumps(hits, ensure_ascii=False)
    return search

@dataclass
class Gateway:
    """Dispatches allowlisted tool calls and guards their results."""

    guard: Any  # ruguard_client.GuardClient (or a fake with .scan)
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    timeout: float = TIMEOUT_SECONDS
    max_chars: int = MAX_RESULT_CHARS

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run one tool: refuse unknown tools and bad arguments, cap size, scan and redact the result."""
        spec = self.tools.get(name)
        if spec is None:
            logger.warning("refused non-allowlisted tool %r", name)
            raise ToolRefused(f"tool {name!r} is not allowlisted")
        try:
            args = spec.args.model_validate(arguments)
        except ValidationError as exc:
            raise ToolRefused(f"invalid arguments for {name}: {exc.errors()[0]['msg']}") from exc
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            try:
                text = pool.submit(spec.fn, args).result(timeout=self.timeout)
            except concurrent.futures.TimeoutError as exc:
                raise ToolRefused(f"tool {name} timed out after {self.timeout} s") from exc
        truncated = len(text) > self.max_chars
        text = text[: self.max_chars]
        out: dict[str, Any] = {"tool": name, "result": text, "truncated": truncated, "redacted": False,
                               "verdict": None, "attack_type": None}
        if spec.scan_result:
            res = self.guard.scan(text, "tool_output")
            out["verdict"], out["attack_type"] = res.verdict, res.attack_type
            if res.flagged:
                out["result"] = REDACTED.format(attack_type=res.attack_type or res.scanner_error or "unknown")
                out["redacted"] = True
        return out

def default_gateway(guard: Any) -> Gateway:
    """The three allowlisted tools: search_docs, scan_text, get_note."""
    chroma_path = os.environ.get("CHROMA_PATH", str(HERE.parent / "demo_rag" / "chroma"))
    collection = os.environ.get("CHROMA_COLLECTION", "noorbagh")

    def scan_text(a: ScanArgs) -> str:
        r = guard.scan(a.text, a.source)
        return json.dumps({"verdict": r.verdict, "attack_type": r.attack_type, "action": r.action})

    return Gateway(guard=guard, tools={
        "search_docs": ToolSpec(SearchArgs, chroma_search(chroma_path, collection),
                                description="Search the Noorbagh help documents (read-only)."),
        "scan_text": ToolSpec(ScanArgs, scan_text, scan_result=False,
                              description="Scan a text for prompt injection with RU-Guard."),
        "get_note": ToolSpec(NoteArgs, lambda a: read_note(a.id),
                             description="Read a demo note by id (notes may contain untrusted text)."),
    })
