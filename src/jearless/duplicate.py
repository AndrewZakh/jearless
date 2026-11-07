"""The duplicate guard (task tooling/10): cheap keyword overlap with mini-IDF.

Simple means by charter: tokenize, weight each word by its scarcity across the
registry's own summaries, score with weighted Jaccard corrected by containment.
No stemming frameworks, no edit distance — a duplicate is the same words in a
different order, and reordering is not the enemy.
"""

import re
from dataclasses import dataclass

from jearless import registry

_STOPWORDS = frozenset(
    [
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
        "has", "have", "in", "into", "is", "it", "its", "of", "on", "or",
        "the", "this", "to", "with", "you", "your",
    ]
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(summary: str) -> list[str]:
    """Lowercase alphanumeric runs minus stopwords; a naive plural strip.

    The strip misses branch/branches-class pairs — acceptable for a guard:
    it is a net, not a wall, and misses cost nothing while false alarms cost
    a confirmation each.
    """
    words: list[str] = []
    for raw in _WORD_RE.findall(summary.lower()):
        if raw in _STOPWORDS:
            continue
        if len(raw) > 3 and raw.endswith("s") and not raw.endswith("ss"):
            raw = raw[:-1]  # tasks → task; class stays class
        words.append(raw)
    return words


def _weights(summaries: list[str]) -> dict[str, float]:
    """Mini-IDF: a word occurring in many summaries weighs almost nothing.

    This is the whole defense against domain noise: "task" and "registry" are
    in half of our summaries and must not trigger matches on their own.
    """
    df: dict[str, int] = {}
    for summary in summaries:
        for word in set(tokenize(summary)):
            df[word] = df.get(word, 0) + 1
    return {word: 1.0 / n for word, n in df.items()}


@dataclass(frozen=True)
class Match:
    task: registry.Task
    score: float  # 0..1


def _score(new: set[str], old: set[str], weights: dict[str, float]) -> float:
    def weight(word: str) -> float:
        return weights.get(word, 1.0)  # an unseen word is maximally informative

    union = new | old
    if not union:
        return 0.0
    shared = new & old
    jaccard = sum(weight(w) for w in shared) / sum(weight(w) for w in union)
    denom = min(sum(weight(w) for w in new), sum(weight(w) for w in old))
    containment = sum(weight(w) for w in shared) / denom if denom else 0.0
    # containment guards the common duplicate: a short summary inside a long one
    return max(jaccard, containment)


def find_similar(
    reg: registry.Registry, summary: str, threshold: float, limit: int = 3
) -> list[Match]:
    """Existing tasks whose summaries overlap above the threshold, best first."""
    new = set(tokenize(summary))
    weights = _weights([t.summary for t in reg.all()])
    matches: list[Match] = []
    for task in reg.all():
        score = _score(new, set(tokenize(task.summary)), weights)
        if score >= threshold:
            matches.append(Match(task, score))
    return sorted(matches, key=lambda m: m.score, reverse=True)[:limit]
