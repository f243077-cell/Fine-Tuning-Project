"""Baseline scanners for Phase 3 (PRD section 13): rules, Qwen2.5-1.5B zero-shot and few-shot, Llama Guard 3.

Every scanner returns (raw_output, pred), where pred is a label string or None for invalid output:
  * Qwen-based and fine-tuned scanners use the shared prompt (training/prompt.py) and the strict grammar.
  * Llama Guard answers "safe" or "unsafe\\nS<n>"; it has no injection category, so "unsafe" maps to a plain
    INJECTION flag with no attack type (binary metrics only).
The rule patterns were written once from the attack definitions and seeds, not tuned on the test set.
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from evals.metrics import parse_output
from training.jsonl import read_rows
from training.normalize import normalize_text
from training.prompt import SYSTEM_PROMPT, USER_TEMPLATE, build_messages

# Ollama settings from Architecture 6.5 (num_ctx grows only for the few-shot prompt).
OLLAMA_OPTIONS = {"temperature": 0, "top_k": 1, "num_predict": 8, "num_ctx": 1024, "seed": 0}

# --- Rule baseline ------------------------------------------------------------------------------------------
_V_IGNORE = r"(ignore|forget|disregard|override|cancel|drop|bhool|bhul|nazarandaz|nazar andaz|chhor|chor|cancel)"
_PRIOR = r"(previous|prior|earlier|above|all|pichl[aiey]|pehl[aiey]|saar[ia]|tamam|purani|purana)"
_RULES = r"(instructions?|rules?|prompts?|hidayat|hidaayat|hukm|guidelines?|task|ahkam|baatein)"
RULES: list[tuple[str, re.Pattern[str]]] = [
    ("exfiltration", re.compile(
        r"(send|forward|email|e-mail|post|upload|share|leak|bhej|bhejo|bhej do|share kar|forward kar)"
        r".{0,80}(example\.com|https?://|@[a-z0-9-]+\.[a-z]|api key|api keys|token|password|credentials?|"
        r"other (users?|customers?)|previous users?|pichl[eay] users?|doosr[eay] (users?|customers?|logon))"
        r"|(example\.com|https?://).{0,80}(bhej|send|forward|email)")),
    ("tool_abuse", re.compile(
        r"\b[a-z]+(_[a-z]+)+\b.{0,60}(tool|call|run|chala|chalao|istemal|use kar|invoke)"
        r"|(call|run|invoke|use|chalao|istemal karo).{0,30}\b[a-z]+(_[a-z]+)+\b"
        r"|(without|bina|baghair).{0,20}(asking|confirm|confirmation|pooch|puch|ijazat|permission)")),
    ("prompt_leak", re.compile(
        r"(system prompt|system message|hidden (instructions?|rules?|prompt)|initial (instructions?|prompt)|"
        r"configuration|setup instructions|developer (instructions?|message)|you are\W{0,3}se shuru|"
        r"text above|upar wal[aie] (text|hidayat))"
        r".{0,80}(show|print|repeat|reveal|output|display|dikhao|dikha do|batao|bata do|likh|share|paste)"
        r"|(show|print|repeat|reveal|dikhao|batao|likh do).{0,60}(system prompt|hidden (instructions?|rules?)|"
        r"(jo|which|that) (tumhe|tumhein|aapko|apko|you were) (di|diye|given))")),
    ("persona", re.compile(
        r"(act as|pretend|you are now|from now on you are|role ?play|ban ?jao|ban jaye?n?|ban jayein|bano|"
        r"character|persona|mode)"
        r".{0,100}(no rules|without (any )?(rules|limits|restrictions|filters)|ignores? (all )?(rules|polic)|"
        r"developer mode|unrestricted|unfiltered|koi (rule|pabandi|qanoon) nahi|be ?lagaam|azad|dan\b)")),
    ("override", re.compile(
        rf"{_V_IGNORE}.{{0,40}}{_PRIOR}.{{0,40}}{_RULES}|{_PRIOR}.{{0,40}}{_RULES}.{{0,40}}{_V_IGNORE}"
        r"|(new instructions?|naye? hidayat|ab se sirf|from now on,? (only )?(reply|answer|say))")),
]


def rule_predict(text: str) -> str:
    """First matching attack type, else SAFE (on normalized text)."""
    norm = normalize_text(text)
    for attack_type, pattern in RULES:
        if pattern.search(norm):
            return f"INJECTION|{attack_type}"
    return "SAFE"


# --- Ollama scanners ----------------------------------------------------------------------------------------
@dataclass
class OllamaScanner:
    """Chat model behind Ollama using the shared prompt; optional few-shot turns before the query."""

    model: str
    url: str = "http://localhost:11434"
    shots: list[dict[str, str]] = field(default_factory=list)
    options: dict = field(default_factory=lambda: dict(OLLAMA_OPTIONS))
    timeout: float = 120.0

    def messages(self, text: str, source: str) -> list[dict[str, str]]:
        """System prompt, few-shot pairs, then the query (identical format to training)."""
        query = build_messages(text, source)
        return [query[0], *self.shots, query[1]]

    def __call__(self, text: str, source: str) -> tuple[str, str | None]:
        """(raw output, parsed label or None)."""
        body = {"model": self.model, "messages": self.messages(text, source), "stream": False,
                "options": self.options}
        r = httpx.post(f"{self.url}/api/chat", json=body, timeout=self.timeout)
        r.raise_for_status()
        raw = r.json()["message"]["content"]
        return raw, parse_output(raw)


def few_shot_turns(seeds_path: Path) -> list[dict[str, str]]:
    """8 fixed seed examples as user/assistant turns: one per attack type (ru_mix), then 3 SAFE rows."""
    seeds, errors = read_rows(seeds_path)
    if errors:
        raise SystemExit(f"seed file errors: {errors[:3]}")
    picked = []
    for t in ("override", "persona", "prompt_leak", "exfiltration", "tool_abuse"):
        picked.append(next(r for r in seeds if r.attack_type == t and r.surface == "ru_mix"))
    safe = [r for r in seeds if r.label == "SAFE"]
    hard = [r for r in safe if r.hard_negative and r.surface == "ru_mix"]
    picked.append(next(r for r in safe if r.surface == "ru_pure"))
    picked.append(hard[0] if hard else next(r for r in safe if r.surface == "ru_mix"))
    picked.append(next(r for r in safe if r.surface == "en"))
    turns = []
    for r in picked:
        turns.append({"role": "user", "content": USER_TEMPLATE.format(source=r.source, text=normalize_text(r.text))})
        turns.append({"role": "assistant", "content": r.target})
    return turns


LLAMA_GUARD_RE = re.compile(r"^(safe|unsafe(\s+S\d+(,\s*S\d+)*)?)$")


@dataclass
class LlamaGuardScanner:
    """Llama Guard 3 via Ollama: the text is sent as the user turn; its own template adds the policy."""

    model: str = "llama-guard3:1b"
    url: str = "http://localhost:11434"
    timeout: float = 120.0

    def __call__(self, text: str, source: str) -> tuple[str, str | None]:
        """(raw output, 'SAFE' / 'INJECTION' flag, or None if the reply is not in Llama Guard's format)."""
        body = {"model": self.model, "messages": [{"role": "user", "content": normalize_text(text)}],
                "stream": False, "options": {"temperature": 0, "top_k": 1, "num_predict": 10, "seed": 0}}
        r = httpx.post(f"{self.url}/api/chat", json=body, timeout=self.timeout)
        r.raise_for_status()
        raw = r.json()["message"]["content"]
        clean = raw.strip()
        if not LLAMA_GUARD_RE.fullmatch(clean):
            return raw, None
        return raw, "SAFE" if clean == "safe" else "INJECTION"


def timed(scanner, text: str, source: str) -> tuple[str, str | None, float]:
    """Run a scanner and return (raw, pred, seconds)."""
    t0 = time.perf_counter()
    raw, pred = scanner(text, source)
    return raw, pred, time.perf_counter() - t0


SYSTEM_PROMPT_USED = SYSTEM_PROMPT  # re-exported for the report
