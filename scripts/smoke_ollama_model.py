"""Phase 4 acceptance check: a registered ru-guard model returns a valid label on 20 val prompts.

    python scripts/smoke_ollama_model.py --model ru-guard-0.5b
    python scripts/smoke_ollama_model.py --model ru-guard-0.5b:q8_0 --tokenizer Qwen/Qwen2.5-0.5B-Instruct

It uses val rows (never the test set), sends the shared prompt over /api/chat, and checks:
(1) every output matches the label grammar; (2) Ollama's prompt_eval_count equals the token count of
training/prompt.py render_prompt(), which shows the Modelfile template renders the training prompt.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from training.jsonl import read_rows  # noqa: E402
from training.prompt import build_messages, render_prompt  # noqa: E402
from training.val_metrics import parse_label, stratified_subset, val_metrics  # noqa: E402

OPTIONS = {"temperature": 0, "top_k": 1, "num_predict": 8, "num_ctx": 1024, "seed": 0}  # as evals/baselines.py


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--val", type=Path, default=REPO / "data" / "processed" / "val.jsonl")
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--tokenizer", default=None, help="HF tokenizer for the live template check (optional)")
    args = ap.parse_args(argv)

    rows, errors = read_rows(args.val)
    if errors:
        print(f"{len(errors)} invalid val rows", file=sys.stderr)
        return 1
    sample = stratified_subset(rows, args.n, seed=1234)[: args.n]
    tok = None
    if args.tokenizer:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(args.tokenizer)
    raws, mismatches = [], 0
    for r in sample:
        resp = httpx.post(f"{args.url}/api/chat", timeout=120, json={
            "model": args.model, "messages": build_messages(r.text, str(r.source)), "stream": False,
            "options": OPTIONS})
        resp.raise_for_status()
        body = resp.json()
        raws.append(body["message"]["content"])
        if tok is not None:
            expected = len(tok(render_prompt(r.text, str(r.source)), add_special_tokens=False)["input_ids"])
            mismatches += body.get("prompt_eval_count") != expected
    invalid = [raw for raw in raws if parse_label(raw) is None]
    summary = {"model": args.model, "n": len(sample), "invalid": len(invalid), "invalid_examples": invalid[:5],
               "template_token_mismatches": mismatches if tok is not None else "not checked",
               "val_metrics_on_sample": val_metrics([r.target for r in sample], raws)}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not invalid and not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
