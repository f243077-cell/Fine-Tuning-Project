"""Shared text normalizer: the single source of truth for training, evaluation, and serving."""

import re
import unicodedata

_REPEAT_RE = re.compile(r"(\D)\1{2,}")
_WS_RE = re.compile(r"\s+")
_LEET_WORD_RE = re.compile(r"[a-z0-9@]*[a-z][a-z0-9@]*")
_LEET_MAP = str.maketrans({"0": "o", "1": "i", "3": "e", "@": "a"})
_KEEP_WS = {"\t", "\n", "\r", "\v", "\f"}


def _strip_controls(text: str) -> str:
    """Remove zero-width, bidi-control, and other control characters (keep whitespace)."""
    return "".join(
        ch for ch in text
        if ch in _KEEP_WS or unicodedata.category(ch) not in ("Cc", "Cf")
    )


def _lower_latin(text: str) -> str:
    """Lowercase Latin letters only; other scripts are left unchanged."""
    return "".join(
        ch.lower() if "LATIN" in unicodedata.name(ch, "") else ch for ch in text
    )


def _leet_fold(text: str) -> str:
    """Fold 0 1 3 @ to o i e a inside words that contain at least one letter."""
    return _LEET_WORD_RE.sub(lambda m: m.group(0).translate(_LEET_MAP), text)


def normalize_text(text: str, leet_fold: bool = False) -> str:
    """Apply the six normalization rules from Architecture.md section 6.1."""
    text = unicodedata.normalize("NFKC", text)
    text = _strip_controls(text)
    text = _lower_latin(text)
    text = _REPEAT_RE.sub(r"\1\1", text)
    text = _WS_RE.sub(" ", text).strip()
    if leet_fold:
        text = _leet_fold(text)
    return text
