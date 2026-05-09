#!/usr/bin/env python3
"""
feed_news_to_universe.py — Module 11b feeder for news/sentiment.

Reads recent news scout signals from `signals` table and tags matching
tickers in `discovery_universe` with source="news_bullish". This complements
the 13F + insider feeders to enable 3-source cross-type convergence (Druckenmiller
buying + insiders active + bullish news = STRONG signal).

Unlike the insider scout, the news scout's `signal` field is meaningful:
distribution across 260 sampled rows was 201 bullish / 42 neutral / 17 bearish,
classified by Perplexity's parsing of recent press releases and news items.
The feeder filters to `signal=bullish` only — neutral and bearish news shouldn't
count as a discovery signal (a single bearish news row would penalize an
otherwise interesting candidate).

Two source tags supported:
  - news_bullish — bullish news signal in the recent window. Default tag.
  - news_earnings_beat — when data.parsed_analysis.events contains an
    `earnings_beat_raise` event. Stronger signal than generic bullish news.
    Counted as a separate source for convergence purposes.

LIMITATION: requires the news scout to have been run with `--source discovery`
to scan the broader universe (not just the 52-ticker watchlist). Without that,
the feeder will tag only watchlist∩discovery overlap names and miss the 13F
MEDIUM/STRONG candidates. Diagnostic prints overlap count.

Usage:
  python scripts/feed_news_to_universe.py
  python scripts/feed_news_to_universe.py --window-days 30 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env  # noqa: E402

load_env()

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

NEWS_TAG = "news_bullish"
EARNINGS_BEAT_TAG = "news_earnings_beat"


def _accumulate_source(existing: str | None, new_tag: str) -> str:
    """Append new_tag if not already present. Same pattern as 13F + insider feeders."""
    tags = [t.strip() for t in (existing or "").split(",") if t.strip()]
    if new_tag not in tags:
        tags.append(new_tag)
    return ", ".join(tags)


def _row_has_earnings_beat(data: dict) -> bool:
    """Check whether the news scout output contains an earnings_beat_raise event.
    The scout stores parsed_analysis.events as a stringified Python list (yes,
    really — the output is `str(events_list)`, not JSON). We do a substring
    check on the stringified data because parsing the repr is fragile.
    A more thorough fix would have the scout emit JSON-encoded fields; until
    then, the substring check is honest about its sloppy edge."""
    if not data:
        return False
    blob = ""
    pa = data.get("parsed_analysis")
    if isinstance(pa, str):
        blob += pa
    elif isinstance(pa, dict):
        blob += json.dumps(pa, default=str)
    elif isinstance(pa, list):
        blob += json.dumps(pa, default=str)
    events = data.get("events")
    if isinstance(events, str):
        blob += events
    elif events is not None:
        blob += json.dumps(events, default=str)
    return "earnings_beat_raise" in blob


def find_bullish_tickers(*, window_days: int) -> list[dict]:
    """Return tickers with bullish news scout signal in the recent window."""
    from supabase_helper import get_client
    sb = get_client()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    rows = sb.table("signals").select(
        "ticker,signal,data,created_at"
    ).eq("scout", "news").eq("signal", "bullish").gte("created_at", cutoff).execute().data or []

    by_ticker: dict[str, dict] = {}
    for r in rows:
        t = r["ticker"]
        cur = by_ticker.get(t)
        has_beat = _row_has_earnings_beat(r.get("data") or {})
        if cur is None:
            by_ticker[t] = {
                "ticker": t,
                "rows": 1,
                "latest_run": r.get("created_at"),
                "has_earnings_beat": has_beat,
            }
        else:
            cur["rows"] += 1
            if r.get("created_at") and (cur["latest_run"] is None or r["created_at"] > cur["latest_run"]):
                cur["latest_run"] = r["created_at"]
            cur["has_earnings_beat"] = cur["has_earnings_beat"] or has_beat
    return list(by_ticker.values())


def upsert_to_universe(active: list[dict], *, dry_run: bool = False) -> dict:
    """Tag each existing discovery_universe row with `news_bullish`, plus
    `news_earnings_beat` if the scout's parsed events flagged an earnings beat."""
    from supabase_helper import get_client
    sb = get_client()
    if not active:
        return {"checked": 0, "updated": 0, "skipped_not_in_universe": 0, "tags_added": 0}

    tickers = [a["ticker"] for a in active]
    existing = sb.table("discovery_universe").select(
        "ticker,source,status"
    ).in_("ticker", tickers).execute().data or []
    existing_by_t = {r["ticker"]: r for r in existing}

    summary = {
        "checked": len(active),
        "updated": 0,
        "skipped_not_in_universe": 0,
        "tags_added": 0,
        "earnings_beat_tags": 0,
    }
    updates_planned: list[tuple[str, str]] = []
    for a in active:
        t = a["ticker"]
        cur = existing_by_t.get(t)
        if cur is None:
            summary["skipped_not_in_universe"] += 1
            continue
        existing_src = cur.get("source") or ""
        new_src = existing_src
        added_here = 0
        if NEWS_TAG not in [s.strip() for s in new_src.split(",")]:
            new_src = _accumulate_source(new_src, NEWS_TAG)
            added_here += 1
        if a.get("has_earnings_beat") and EARNINGS_BEAT_TAG not in [s.strip() for s in new_src.split(",")]:
            new_src = _accumulate_source(new_src, EARNINGS_BEAT_TAG)
            added_here += 1
            summary["earnings_beat_tags"] += 1
        if new_src != existing_src:
            updates_planned.append((t, new_src))
            summary["tags_added"] += added_here

    if dry_run:
        summary["would_update"] = len(updates_planned)
        return summary

    for t, new_src in updates_planned:
        try:
            sb.table("discovery_universe").update({"source": new_src}).eq("ticker", t).execute()
            summary["updated"] += 1
        except Exception as e:
            print(f"  [WARN] update failed for {t}: {e}", file=sys.stderr)
    return summary


def diagnose_overlap_with_13f() -> dict:
    from supabase_helper import get_client
    sb = get_client()
    rows = sb.table("discovery_universe").select("ticker,source").like("source", "%13f_%").execute().data or []
    ticker_13f = {r["ticker"] for r in rows}
    news_rows = sb.table("signals").select("ticker").eq("scout", "news").eq("signal", "bullish").execute().data or []
    ticker_news = {r["ticker"] for r in news_rows}
    overlap = ticker_13f & ticker_news
    return {
        "13f_tagged_count": len(ticker_13f),
        "news_bullish_count": len(ticker_news),
        "overlap_count": len(overlap),
        "overlap_sample": sorted(overlap)[:10],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-days", type=int, default=30,
                        help="Look back this many days for news scout activity (default 30)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"\n=== feed_news_to_universe — window={args.window_days}d ===")
    diag = diagnose_overlap_with_13f()
    print(f"  diagnostic: 13F-tagged={diag['13f_tagged_count']}, "
          f"news-bullish={diag['news_bullish_count']}, "
          f"overlap={diag['overlap_count']}")
    if diag["overlap_sample"]:
        print(f"  overlap sample: {diag['overlap_sample']}")
    if diag["overlap_count"] == 0:
        print("  WARNING: zero overlap. Run `python scripts/scout_news.py --source "
              "discovery` first, then re-run this feeder.")

    active = find_bullish_tickers(window_days=args.window_days)
    print(f"  found {len(active)} tickers with bullish news in window "
          f"(of which {sum(1 for a in active if a.get('has_earnings_beat'))} flagged earnings beat)")
    summary = upsert_to_universe(active, dry_run=args.dry_run)
    print(f"  result: {summary}")

    if not args.dry_run and summary.get("updated", 0) > 0:
        print(f"\n  Hint: re-run convergence to see new cross-type signals:")
        print(f"  python scripts/convergence_detector.py --top 25")


if __name__ == "__main__":
    main()
