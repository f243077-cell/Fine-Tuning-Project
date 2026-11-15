"""Regression check (Phase 7): with the guard off the graph makes zero guard calls and behaves exactly like a plain
RAG pipeline (retrieve -> prompt -> generate) on every golden-set question."""

import re
from pathlib import Path

import yaml

from demo_rag.graph import Deps, build_graph, build_messages, run
from demo_rag.tests.fakes import ExplodingGuard, fake_retrieve

GOLDEN = Path(__file__).resolve().parents[2] / "evals" / "golden_set.yaml"
CANARY_RE = re.compile(r"CANARY-[0-9A-F]{12}")


class EchoChat:
    """Deterministic chat: the answer is derived from the prompt, so equal prompts give equal answers."""

    def __init__(self) -> None:
        """Record prompts."""
        self.prompts: list[str] = []

    def __call__(self, messages: list[dict]) -> str:
        """Answer with a digest of the (canary-free) prompt."""
        text = CANARY_RE.sub("CANARY", "\n".join(m["content"] for m in messages))
        self.prompts.append(text)
        return f"answer {abs(hash(text)) % 10_000} [en-02-refund-policy]"


def plain_rag(question: str, chat: EchoChat, k: int = 4, budget: int = 1500) -> str:
    """The same pipeline without any guard code."""
    messages, _ = build_messages(question, fake_retrieve(question, k), "CANARY-000000000000", budget)
    return chat(messages)


def test_guard_off_is_a_plain_rag_on_the_golden_set() -> None:
    """Zero guard calls (ExplodingGuard) and identical prompts and answers for all 30 golden questions."""
    questions = [q["question"] for q in yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["questions"]]
    assert len(questions) == 30
    graph_chat, plain_chat = EchoChat(), EchoChat()
    graph = build_graph(Deps(guard=ExplodingGuard(), retrieve=fake_retrieve, chat=graph_chat))
    for q in questions:
        out = run(graph, q, guard=False)
        assert out["answer"] == plain_rag(q, plain_chat) and out["guard_events"] == []
    assert graph_chat.prompts == plain_chat.prompts
