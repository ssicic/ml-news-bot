"""Fetch new DS / ML / AI engineering posts from RSS feeds and send a digest to Telegram.

Usage:
    python bot.py            # fetch, send to Telegram, update state
    python bot.py --dry-run  # fetch and print the digest, send nothing, keep state as is
"""

from __future__ import annotations

import argparse
import calendar
import html
import json
import os
import re
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "sources.toml"
STATE_PATH = ROOT / "state" / "seen.json"

TELEGRAM_LIMIT = 4096
USER_AGENT = "ml-news-bot/1.0 (+rss reader)"


@dataclass
class Item:
    source: str
    category: str
    title: str
    link: str
    published: float  # unix timestamp, 0 if unknown
    score: float = 0.0
    summary: str = ""


def load_config() -> dict:
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def load_state() -> dict[str, float]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict[str, float], keep_days: int) -> None:
    cutoff = time.time() - keep_days * 86400
    pruned = {k: v for k, v in state.items() if v >= cutoff}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(pruned, indent=0, sort_keys=True))


def entry_time(entry) -> float:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return float(calendar.timegm(t))
    return 0.0


def matches(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = text.lower()
    return any(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in keywords)


def fetch_source(src: dict, global_keywords: list[str]) -> tuple[str, list[Item], str | None]:
    name = src["name"]
    try:
        resp = requests.get(src["url"], headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:  # network errors should not kill the whole run
        return name, [], str(exc)

    # Broad feeds (HN, TDS...) get filtered by keywords; niche feeds pass through.
    keywords = global_keywords if src.get("filter", False) else []
    keywords = src.get("keywords", keywords)

    items = []
    for entry in feed.entries[: src.get("max_items", 30)]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        if src.get("exclude") and re.search(src["exclude"], title):
            continue
        summary = entry.get("summary", "")
        if not matches(f"{title} {summary}", keywords):
            continue
        # Score = how much you trust the source, plus a bonus for HN points.
        score = float(src.get("weight", 1))
        points = re.search(r"Points:\s*(\d+)", summary)
        if points:
            score += min(int(points.group(1)) / 400, 1.0)
        items.append(Item(name, src.get("category", "Ostalo"), title, link, entry_time(entry), score, summary))
    return name, items, None


def fetch_all(config: dict) -> tuple[list[Item], dict[str, str]]:
    sources = config["sources"]
    keywords = config.get("settings", {}).get("keywords", [])
    items: list[Item] = []
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, src_items, err in pool.map(lambda s: fetch_source(s, keywords), sources):
            if err:
                errors[name] = err
            items.extend(src_items)
    return items, errors


def pick_new(items: list[Item], state: dict[str, float], max_age_days: int) -> list[Item]:
    now = time.time()
    cutoff = now - max_age_days * 86400
    seen_now: set[str] = set()
    fresh = []
    for it in items:
        if it.link in state or it.link in seen_now:
            continue
        if it.published and it.published < cutoff:
            continue
        seen_now.add(it.link)
        fresh.append(it)
    fresh.sort(key=lambda i: i.published, reverse=True)
    return fresh


def build_top_message(picks: list[tuple[Item, str]]) -> str:
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y.")
    lines = [f"<b>📰 Top {len(picks)} iz DS / ML / AI — {today}</b>"]
    for n, (it, why) in enumerate(picks, 1):
        lines.append("")
        lines.append(f'{n}. <a href="{html.escape(it.link, quote=True)}">{html.escape(it.title)}</a>')
        lines.append(f"<i>{html.escape(it.source)}</i>")
        if why:
            lines.append(html.escape(why))
    return "\n".join(lines)


def choose_top(
    items: list[Item], n: int, all_items: list[Item], sources: list[dict]
) -> list[tuple[Item, str]]:
    """AI picks when an API key is set; otherwise (or if the AI call fails) rank.py picks."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from ai_pick import ai_pick

            ranked = sorted(items, key=lambda i: (i.score, i.published), reverse=True)
            return ai_pick(ranked, n)
        except Exception as exc:
            print(f"[warn] AI pick failed, using rules instead: {exc}", file=sys.stderr)
    from rank import rank_top

    weights = {s["name"]: s.get("weight", 1) for s in sources}
    caps = {s["name"]: s.get("top_cap", 1) for s in sources}
    return rank_top(items, all_items, n, weights, caps)


def build_messages(items: list[Item], per_source_cap: int) -> list[str]:
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y.")
    header = f"<b>📰 DS / ML / AI vijesti — {today}</b>\n"

    by_cat: dict[str, dict[str, list[Item]]] = {}
    for it in items:
        by_cat.setdefault(it.category, {}).setdefault(it.source, []).append(it)

    blocks = []
    for cat in sorted(by_cat):
        lines = [f"\n<b>{html.escape(cat)}</b>"]
        for source, src_items in sorted(by_cat[cat].items()):
            lines.append(f"<i>{html.escape(source)}</i>")
            for it in src_items[:per_source_cap]:
                lines.append(f'• <a href="{html.escape(it.link, quote=True)}">{html.escape(it.title)}</a>')
            extra = len(src_items) - per_source_cap
            if extra > 0:
                lines.append(f"  … i još {extra}")
        blocks.append("\n".join(lines))

    # Split into Telegram-sized messages on block / line boundaries.
    messages, current = [], header
    for block in blocks:
        for line in block.split("\n"):
            if len(current) + len(line) + 1 > TELEGRAM_LIMIT - 50:
                messages.append(current)
                current = ""
            current += line + "\n"
    if current.strip():
        messages.append(current)
    return messages


def send_telegram(token: str, chat_id: str, text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"Telegram error {resp.status_code}: {resp.text}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print digest, don't send or save state")
    args = parser.parse_args()

    config = load_config()
    settings = config.get("settings", {})
    state = load_state()
    first_run = not state

    items, errors = fetch_all(config)
    for name, err in errors.items():
        print(f"[warn] {name}: {err}", file=sys.stderr)

    # First run: only look back 1 day so you don't get a flood of old posts.
    max_age = 1 if first_run else settings.get("max_age_days", 3)
    new_items = pick_new(items, state, max_age)
    print(f"fetched {len(items)} items, {len(new_items)} new, {len(errors)} source errors")

    if new_items:
        top_n = settings.get("top_n", 0)
        if top_n:
            messages = [build_top_message(choose_top(new_items, top_n, items, config["sources"]))]
        else:
            messages = build_messages(new_items, settings.get("per_source_cap", 5))
        if args.dry_run:
            for m in messages:
                print("-" * 40)
                print(m)
        else:
            token = os.environ["TELEGRAM_BOT_TOKEN"]
            chat_id = os.environ["TELEGRAM_CHAT_ID"]
            for m in messages:
                send_telegram(token, chat_id, m)
                time.sleep(1)

    if not args.dry_run:
        now = time.time()
        # Mark everything we fetched as seen (including old/filtered ones) so they never resurface.
        for it in items:
            state.setdefault(it.link, now)
        save_state(state, settings.get("keep_state_days", 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
