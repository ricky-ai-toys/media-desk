"""Shared keyword helpers for agenda/topic matching (framing + coverage)."""
import re

_STOP = {"the", "and", "for", "are", "will", "of", "to", "in", "on", "how",
         "you", "its", "can", "all", "one", "new", "was", "but", "not", "out",
         "has", "why", "what", "week", "china", "market", "markets", "from",
         "with", "their", "this", "that", "more", "after", "about"}


def kw(text: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower())
            if w not in _STOP}


def overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
