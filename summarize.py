"""One- or two-sentence summary for a post, without an LLM.

Uses the feed's own summary when it has a real one; otherwise reads the page's
meta description (the blurb sites write for link previews).
"""

from __future__ import annotations

import html
import re

import requests

MAX_LEN = 240
HEADERS = {"User-Agent": "ml-news-bot/1.0 (+rss reader)"}


def _clean(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _shorten(text: str) -> str:
    """Cut to whole sentences that fit in MAX_LEN, or to a word boundary with an ellipsis."""
    if len(text) <= MAX_LEN:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for s in sentences:
        if len(out) + len(s) + 1 > MAX_LEN:
            break
        out = f"{out} {s}".strip()
    if out:
        return out
    return text[:MAX_LEN].rsplit(" ", 1)[0] + "…"


def _meta_description(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return ""
    head = resp.text[:200_000]
    for prop in ("og:description", "description", "twitter:description"):
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]+content=["\']([^"\']+)', head, re.I
        ) or re.search(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{prop}["\']', head, re.I
        )
        if m:
            return _clean(m.group(1))
    return ""


def _useful(text: str, title: str) -> bool:
    if len(text) < 40 or "Article URL:" in text:  # hnrss puts only links/points in the summary
        return False
    return text.lower()[:60] != title.lower()[:60]  # summary that just repeats the title


def summarize(title: str, link: str, feed_summary: str) -> str:
    text = _clean(feed_summary)
    if text.lower().startswith(title.lower()):  # some feeds start the body with the title
        text = text[len(title):].lstrip(" :.-")
    if not _useful(text, title):
        text = _meta_description(link)
    return _shorten(text) if _useful(text, title) else ""
