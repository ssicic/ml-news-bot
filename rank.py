"""Pick the most important posts of the day without an LLM.

Signals, strongest first:
1. Coverage - how many different sources wrote about the same story today.
   Stories are grouped by shared distinctive title words (e.g. "gpt-6.2", "astra").
2. Source weight from sources.toml, plus Hacker News points.
3. Title words: launches / releases / open-source get a bonus,
   partnerships / webinars / listicles / salaries get a penalty.
One post per story and one per source in the final list.
"""

from __future__ import annotations

import re
from collections import Counter

STOPWORDS = set("""
a an and are as at be by can for from has have how i in into is it its of on or our that the
their this to we what when why with you your vs via new now more than about over using use
just still not all any one two three get got gets make makes made way ways
ai ml llm llms model models data learning machine deep science engineering engineer
agent agents agentic system systems tool tools part guide introduction build building
""".split())

BOOST = {
    r"\b(introducing|announcing|launch(es|ed)?|release[sd]?|unveil|now available)\b": 1.0,
    r"\b(open[- ]?source|open[- ]?weights?|paper|benchmark|eval(s|uation)?)\b": 0.7,
    r"\b(inference|training|fine[- ]?tun\w*|rag|retrieval|coding agents?|efficien\w*|"
    r"researchers?|\d+x (faster|cheaper|more))\b": 0.5,
}
PENALTY = {
    r"\b(partner(s|ship)?|webinar|event|customers?|case study|hiring|salar(y|ies)|podcast)\b": -1.5,
    r"^\s*(top )?\d+\s+(ways|tips|things|tools|reasons|mistakes|libraries)\b": -1.0,
    r"\b(beginner'?s?|cheat ?sheet|for dummies)\b": -0.8,
}

COVERAGE_BONUS = 1.5  # per extra source covering the same story


def _tokens(title: str) -> set[str]:
    title = re.sub(r"[‐-―]", "-", title.lower())  # unicode dashes -> "-"
    words = re.findall(r"[a-z0-9][a-z0-9.\-]*[a-z0-9]", title)
    return {w for w in words if w not in STOPWORDS and not w.isdigit() and len(w) > 2}


def _clusters(items: list, all_items: list) -> list[int]:
    """Union-find over items that share distinctive title words. Returns a cluster id per item."""
    df = Counter(t for it in all_items for t in _tokens(it.title))
    rare = [{t for t in _tokens(it.title) if df[t] <= 8} for it in items]

    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            shared = rare[i] & rare[j]
            # one versioned name (gpt-6.2, llama-5) is enough; otherwise need two shared words
            if any(re.search(r"\d", t) for t in shared) or len(shared) >= 2:
                parent[find(i)] = find(j)
    return [find(i) for i in range(len(items))]


def _title_score(title: str, weight: float = 1.0) -> float:
    """Bonus words count less on low-weight sources (an AWS 'Announcing' is not an OpenAI one)."""
    s = 0.0
    for pattern, value in BOOST.items():
        if re.search(pattern, title, re.IGNORECASE):
            s += value * min(weight, 1.0)
    for pattern, value in PENALTY.items():
        if re.search(pattern, title, re.IGNORECASE):
            s += value
    return s


def rank_top(
    items: list, all_items: list, n: int, weights: dict[str, float] | None = None,
    caps: dict[str, int] | None = None,
) -> list[tuple[object, str]]:
    """Return [(item, note), ...] for the n best stories. note names other sources that covered it.

    weights: source -> weight from sources.toml; caps: source -> max posts in the top list (default 1).
    """
    weights = weights or {}
    caps = caps or {}
    if not items:
        return []
    cluster_of = _clusters(items, all_items)
    sources_in = {}
    for it, c in zip(items, cluster_of):
        sources_in.setdefault(c, set()).add(it.source)

    def score(idx: int) -> float:
        it = items[idx]
        coverage = len(sources_in[cluster_of[idx]])
        title_bonus = _title_score(it.title, weights.get(it.source, 1.0))
        return it.score + COVERAGE_BONUS * (coverage - 1) + title_bonus

    order = sorted(range(len(items)), key=lambda i: (score(i), items[i].published), reverse=True)
    top, used_clusters, per_source = [], set(), Counter()
    for i in order:
        it, c = items[i], cluster_of[i]
        if c in used_clusters or per_source[it.source] >= caps.get(it.source, 1):
            continue
        used_clusters.add(c)
        per_source[it.source] += 1
        others = sorted(sources_in[c] - {it.source})
        note = f"Also covered by: {', '.join(others)}" if others else ""
        top.append((it, note))
        if len(top) == n:
            break
    return top
