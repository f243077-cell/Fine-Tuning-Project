"""Data v2 (Phase 5, the one allowed data loop): make ru_pure training rows from ru_mix training rows.

    python -m training.purify_v2 --config training/configs/purify_v2.yaml

Why: on the frozen test set every model misses ru_pure attacks (recall 0.52 to 0.68 vs 0.96 to 1.00 on en),
and there is no ru_pure synthetic training data (D38: the 14B generator garbled pure Urdu). This step is
deterministic: English words in ru_mix synthetic TRAIN rows are replaced with standard Urdu words from a fixed
dictionary (built from the most frequent English words in the training rows, not from test items). Rows are kept
only if they pass the ru_pure language check, and rows near any test item are dropped (leak check). Val is unchanged.
Output: data/processed/train_v2.jsonl and data/processed/purify_v2_report.json.
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import yaml
from pydantic import BaseModel

from training.build_dataset import RU_MARKERS, LangConfig, SimilarityIndex, language_ok, shingles, verify_test_lock
from training.jsonl import content_sha256, read_rows, write_rows
from training.schemas import DataRow, Label, Origin, Surface

REPO = Path(__file__).resolve().parents[1]

# Multi-word phrases first (longest match wins), then single words. Values are standard Roman Urdu.
PHRASES = {
    "system prompt": "nizami hidayat", "system instructions": "nizami hidayat", "system message": "nizami paigham",
    "previous instructions": "pichli hidayat", "secret word": "khufia lafz", "secret words": "khufia alfaz",
    "api keys": "khufia chabiyan", "api key": "khufia chabi", "email addresses": "barqi pate",
    "email address": "barqi pata", "for example": "masalan", "right now": "abhi", "as soon as possible": "jald az jald",
}
WORDS = {
    # instructions, rules, system
    "instructions": "hidayat", "instruction": "hidayat", "guidelines": "rehnuma usool", "guideline": "rehnuma usool",
    "rules": "qawaid", "rule": "qaida", "policy": "zabita", "policies": "zawabit", "restrictions": "pabandiyan",
    "limitations": "hudood", "limits": "hudood", "system": "nizam", "prompt": "hidayat", "mode": "halat",
    "configuration": "tarteeb", "settings": "tarteebat", "context": "siyaq", "initial": "ibtidai",
    # actors
    "assistant": "madadgar", "agent": "karinda", "user": "sarif", "users": "sarifeen", "customer": "gahak",
    "customers": "gahak", "developer": "banane wala", "admin": "muntazim", "boss": "afsar", "manager": "mudeer",
    "persona": "kirdar", "character": "kirdar",
    # verbs used with karo / kar do / karna
    "ignore": "nazar andaz", "forget": "faramosh", "follow": "pairwi", "override": "mansookh",
    "send": "rawana", "forward": "aage rawana", "share": "sanjha", "reveal": "zahir", "print": "chhaap",
    "repeat": "dobara bayan", "translate": "tarjuma", "check": "jaanch", "review": "jaiza", "confirm": "tasdeeq",
    "cancel": "mansookh", "delete": "hazf", "remove": "khatam", "update": "tabdeel", "change": "tabdeel",
    "reset": "bahal", "activate": "chalu", "disable": "band", "block": "band", "execute": "jari", "run": "jari",
    "invoke": "talab", "call": "talab", "use": "istemal", "provide": "faraham", "include": "shamil", "add": "shamil",
    "collect": "jama", "submit": "jama", "save": "mehfooz", "search": "talash", "find": "talash",
    "explain": "wazeh", "mention": "zikr", "reply": "jawab", "respond": "jawab", "answer": "jawab",
    "read": "parh", "help": "madad", "receive": "wasool", "apply": "lagu", "assume": "farz", "complete": "mukammal",
    "process": "amal", "access": "rasai", "manage": "intizam", "test": "azmaish", "approve": "manzoor",
    # objects
    "tool": "aala", "tools": "aalaat", "message": "paigham", "messages": "paighamat", "secret": "raaz",
    "secrets": "raaz", "word": "lafz", "words": "alfaz", "password": "khufia lafz", "passwords": "khufia alfaz",
    "keys": "chabiyan", "key": "chabi", "data": "maloomat", "information": "maloomat", "details": "tafseelat",
    "document": "dastavez", "documents": "dastavezat", "file": "misl", "files": "misl", "database": "zakheera",
    "account": "khata", "payment": "adaigi", "payments": "adaigiyan", "request": "darkhwast", "requests": "darkhwastein",
    "response": "jawab", "responses": "jawabat", "result": "nateeja", "results": "nataij", "summary": "khulasa",
    "report": "riport", "list": "fehrist", "question": "sawal", "questions": "sawalat", "query": "sawal",
    "text": "tehreer", "note": "yaad dasht", "notes": "yaad dashtein", "task": "kaam", "tasks": "kaam",
    "order": "hukm nama", "orders": "ahkamat", "approval": "manzoori", "permission": "ijazat",
    "confirmation": "tasdeeq", "security": "hifazat", "session": "nashist", "address": "pata", "addresses": "pate",
    "email": "barqi khat", "contact": "raabta", "link": "rabt", "code": "code",
    # adjectives, adverbs, function words
    "previous": "pichli", "last": "aakhri", "next": "agla", "current": "maujooda", "recent": "haaliya",
    "hidden": "chhupi", "secure": "mehfooz", "personal": "zaati", "important": "aham", "free": "azad",
    "unlimited": "la mehdood", "available": "dastyab", "clear": "saaf", "please": "meharbani se", "kindly": "meharbani se",
    "plz": "meharbani se", "plzz": "meharbani se", "immediately": "fauran", "now": "ab", "all": "tamam", "every": "har",
    "return": "wapsi", "guide": "rehnuma", "appointment": "mulaqat ka waqt", "appointments": "mulaqat ke auqat",
    "meeting": "ijlas", "delivery": "tarseel", "service": "khidmat", "application": "darkhwast", "support": "madad",
    "reminder": "yaad dahani", "week": "hafta", "month": "mahina", "old": "purana", "latest": "taaza",
    "numbers": "adad", "draft": "masauda", "event": "taqreeb", "visit": "daura", "study": "parhai",
    "project": "mansooba", "issue": "masla", "issues": "masail", "feature": "khasiyat", "features": "khasusiyat",
    "consider": "ghaur", "advice": "mashwara", "suggest": "tajweez", "remind": "yaad dahani", "sure": "yaqeeni",
    "date": "tareekh", "specific": "makhsoos", "employees": "mulazimeen", "real": "asal", "accounts": "khatay",
    "focus": "tawajjuh", "ask": "sawal", "successfully": "kamyabi se", "imagine": "tasawwur",
    "requirements": "zaruriyat", "safety": "hifazat", "history": "tareekh", "conversation": "guftagu",
    "chat": "guftagu", "need": "zaroorat", "summarize": "khulasa", "upcoming": "aane wala", "full": "poora",
    "exact": "bilkul", "select": "muntakhib", "ensure": "yaqeeni", "output": "nateeja", "grant": "ata",
    "default": "tayshuda", "operate": "chala", "way": "tareeqa", "through": "zariye", "answers": "jawabat",
    "received": "wasool", "stop": "band", "abort": "rok", "display": "zahir", "attach": "jor", "show": "dikha",
    "write": "likh", "tell": "bata", "give": "de", "start": "shuru", "begin": "shuru", "act": "amal",
    "the": "", "a": "", "an": "", "and": "aur", "or": "aur", "with": "ke sath", "without": "baghair", "from": "se",
    "to": "ko", "for": "ke liye", "you": "tum", "your": "tumhara", "my": "mera", "this": "yeh", "that": "woh",
}
PROTECT_RE = re.compile(r"https?://\S+|\S+@\S+|\b\w*[_\d]\w*\b|\b\w+\([^)]*\)|\"[^\"]*\"\s*:")
TOKEN_RE = re.compile(r"[A-Za-z]+")


class PurifyConfig(BaseModel):
    """Settings from training/configs/purify_v2.yaml."""
    train_path: str
    test_path: str
    out_path: str
    report_path: str
    n_injection: int
    n_hard_negative: int
    n_safe: int
    max_english_share: float = 0.15
    leak_threshold: float = 0.5
    ngram: int = 5
    seed: int = 1234


def _replace_plain(segment: str) -> str:
    """Dictionary replacement inside a segment with no protected spans."""
    for en in sorted(PHRASES, key=len, reverse=True):
        segment = re.sub(rf"(?i)\b{re.escape(en)}\b", PHRASES[en], segment)
    out = TOKEN_RE.sub(lambda m: WORDS.get(m.group(0).lower(), m.group(0)), segment)
    return re.sub(r"[ \t]{2,}", " ", out)


def purify(text: str) -> str:
    """ru_mix text with English words replaced by Urdu; URLs, emails, ids, code calls and JSON keys are kept."""
    parts, last = [], 0
    for m in PROTECT_RE.finditer(text):
        parts.append(_replace_plain(text[last:m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_replace_plain(text[last:]))
    return re.sub(r" +([,.?!:;])", r"\1", "".join(parts)).strip()


def english_vocab(rows: list[DataRow]) -> frozenset[str]:
    """English content words: frequent in en train rows, absent from human-written Roman Urdu rows and markers."""
    en = Counter(w for r in rows if r.surface == Surface.EN for w in TOKEN_RE.findall(r.text.lower()))
    ru = {w for r in rows if r.surface != Surface.EN and r.origin == Origin.EXTERNAL
          for w in TOKEN_RE.findall(r.text.lower())}
    urdu_out = {w for v in [*WORDS.values(), *PHRASES.values()] for w in v.split()}
    return frozenset(w for w, n in en.items()
                     if n >= 3 and len(w) > 2 and w not in ru and w not in RU_MARKERS and w not in urdu_out)


def english_share(text: str, vocab: frozenset[str]) -> float:
    """Share of word tokens that are English content words."""
    words = TOKEN_RE.findall(text.lower())
    return sum(w in vocab for w in words) / len(words) if words else 1.0


def candidates(rows: list[DataRow]) -> dict[str, list[DataRow]]:
    """ru_mix synthetic train rows by kind: injection, hard_negative, safe."""
    kinds: dict[str, list[DataRow]] = {"injection": [], "hard_negative": [], "safe": []}
    for r in rows:
        if r.surface != Surface.RU_MIX or r.origin != Origin.SYNTHETIC:
            continue
        kind = "injection" if r.label == Label.INJECTION else "hard_negative" if r.hard_negative else "safe"
        kinds[kind].append(r)
    return kinds


def convert(row: DataRow) -> DataRow:
    """The ru_pure version of one row (same label, type, source, flags)."""
    return row.model_copy(update={"id": f"pure-{row.id}", "text": purify(row.text), "surface": Surface.RU_PURE})


def run(cfg: PurifyConfig) -> dict:
    """Build train_v2 = train + converted rows; return the report."""
    test_path = REPO / cfg.test_path
    verify_test_lock(test_path)
    train, errors = read_rows(REPO / cfg.train_path)
    test, terrs = read_rows(test_path)
    if errors or terrs:
        raise SystemExit(f"invalid rows: {(errors + terrs)[:3]}")
    test_sets = [shingles(r.text, cfg.ngram) for r in test]
    freq = Counter(g for s in test_sets for g in s)
    index = SimilarityIndex(cfg.leak_threshold, freq)
    for s in test_sets:
        index.add(s)
    rng = random.Random(cfg.seed)
    lang = LangConfig()
    vocab = english_vocab(train)
    report = {"input_train_rows": len(train), "kept": Counter(), "dropped": Counter(), "attack_types": Counter()}
    new: list[DataRow] = []
    quota = {"injection": cfg.n_injection, "hard_negative": cfg.n_hard_negative, "safe": cfg.n_safe}
    for kind, pool in candidates(train).items():
        pool = sorted(pool, key=lambda r: r.id)
        rng.shuffle(pool)
        for r in pool:
            if report["kept"][kind] >= quota[kind]:
                break
            c = convert(r)
            if c.text == r.text:
                report["dropped"]["unchanged"] += 1
            elif not language_ok(c, lang):
                report["dropped"]["language"] += 1
            elif english_share(c.text, vocab) > cfg.max_english_share:
                report["dropped"]["too_much_english"] += 1
            elif index.best_match(shingles(c.text, cfg.ngram)) >= cfg.leak_threshold:
                report["dropped"]["test_leak"] += 1
            else:
                new.append(c)
                report["kept"][kind] += 1
                if c.attack_type:
                    report["attack_types"][str(c.attack_type)] += 1
    out = REPO / cfg.out_path
    write_rows(out, [*train, *new])
    report.update({"new_rows": len(new), "train_v2_rows": len(train) + len(new),
                   "train_v2_sha256": content_sha256(out), "train_v1_sha256": content_sha256(REPO / cfg.train_path)})
    report = json.loads(json.dumps(report))
    (REPO / cfg.report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--preview", type=int, default=0, help="print N before/after pairs and exit")
    args = ap.parse_args(argv)
    cfg = PurifyConfig.model_validate(yaml.safe_load(args.config.read_text(encoding="utf-8")))
    if args.preview:
        rows, _ = read_rows(REPO / cfg.train_path)
        pool = [r for k in candidates(rows).values() for r in k]
        for r in random.Random(cfg.seed).sample(pool, args.preview):
            print(f"[{r.target}] {r.text}\n  -> {purify(r.text)}\n")
        return 0
    print(json.dumps(run(cfg), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
