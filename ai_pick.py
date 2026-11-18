"""Let Claude pick the most important links of the day and say why each matters."""

from __future__ import annotations

import html
import re

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
MAX_CANDIDATES = 60  # keeps the prompt small; candidates are pre-sorted by the rules score

SYSTEM = """You pick the daily news for a data scientist who works on ML and is moving into AI engineering.

From the list of new posts, choose the most important ones for that reader. Prefer:
- new models, tools or techniques people will actually use at work
- practical engineering lessons (evals, RAG, agents, inference, MLOps, data science methods)
- big industry moves that change what is possible or what it costs
Skip marketing, partnership announcements, listicles, beginner tutorials and near-duplicates
(if two posts cover the same news, keep the better one).

For each pick, write one short sentence in Croatian that says why it matters. Plain words, no hype."""


class Pick(BaseModel):
    index: int
    why: str


class Picks(BaseModel):
    picks: list[Pick]


def _clean(text: str, limit: int = 300) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def ai_pick(items: list, n: int) -> list[tuple[object, str]]:
    """Return [(item, why), ...]. Raises on any API problem so the caller can fall back."""
    candidates = items[:MAX_CANDIDATES]
    listing = "\n".join(
        f"[{i}] {it.source} | {it.title} | {_clean(it.summary)}" for i, it in enumerate(candidates)
    )

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Pick exactly {n} posts (or fewer if fewer are worth it).\n\n{listing}",
        }],
        output_format=Picks,
    )
    if response.stop_reason != "end_turn" or response.parsed_output is None:
        raise RuntimeError(f"no usable answer (stop_reason={response.stop_reason})")

    result, seen = [], set()
    for p in response.parsed_output.picks:
        if 0 <= p.index < len(candidates) and p.index not in seen:
            seen.add(p.index)
            result.append((candidates[p.index], p.why.strip()))
    if not result:
        raise RuntimeError("model returned no valid picks")
    return result[:n]
