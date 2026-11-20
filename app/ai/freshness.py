"""Near-duplicate checks for quiz questions and daily posts."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

THRESHOLD = 0.6
ANGLES = ("fact", "scenario", "definition", "number", "tip")
_WORD = re.compile(r"[0-9a-zA-ZÀ-ÖØ-öø-ÿĀ-žЀ-ӿʻʼ'’-]+", re.UNICODE)


_APOS = dict.fromkeys(map(ord, "‘’‛ʼ`'´"), None)


def normalize(text: str) -> str:
    """Lowercase and drop punctuation, including Uzbek o'/g' apostrophes."""
    lowered = (text or "").casefold().translate(_APOS).replace("'", "")
    return " ".join(_WORD.findall(lowered))


def tokens(text: str) -> frozenset[str]:
    """Unique normalized words."""
    return frozenset(normalize(text).split())


def jaccard(left: str, right: str) -> float:
    """Token-set overlap, 0 to 1."""
    a, b = tokens(left), tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def ratio(left: str, right: str) -> float:
    """Character-level similarity of the normalized strings, 0 to 1."""
    a, b = normalize(left), normalize(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def similarity(left: str, right: str) -> float:
    """The higher of Jaccard and difflib ratio."""
    return max(jaccard(left, right), ratio(left, right))


def best_score(candidate: str, recent: list[str]) -> float:
    """Highest similarity against the recent list, or 0 when it is empty."""
    return max((similarity(candidate, item) for item in recent if item), default=0.0)


def is_too_similar(candidate: str, recent: list[str], threshold: float = THRESHOLD) -> bool:
    """True when the candidate matches any recent item at or above the threshold."""
    return best_score(candidate, recent) >= threshold


def pick_angle(slot: str, offset: int = 0) -> str:
    """Rotate fact/scenario/definition/number/tip from the local date slot."""
    seed = sum(map(ord, slot or "x")) + offset
    return ANGLES[seed % len(ANGLES)]


def prefer_fresh(first: str, second: str, recent: list[str]) -> bool:
    """True when the second text is a better (less similar) candidate."""
    if not is_too_similar(second, recent):
        return True
    return best_score(second, recent) < best_score(first, recent)
