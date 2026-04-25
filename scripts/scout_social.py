#!/usr/bin/env python3
"""
Scout 3: Social Sentiment (Reddit + StockTwits — free, no API keys)
Monitors Reddit and StockTwits for stock mentions and sentiment.

Uses public JSON endpoints (no OAuth needed).
Parallelized for speed — all tickers fetched concurrently.

Usage:
    python scripts/scout_social.py
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from utils import get_watchlist, save_signals, timestamp

HEADERS = {
    "User-Agent": "StockRadar/1.0 (stock-radar-agent)",
}

# Only the two most relevant subreddits — WSB and stocks cover 90% of signal
SUBREDDITS = ["wallstreetbets", "stocks"]

# Shorter timeout — don't let one slow request hold up the pipeline
REQUEST_TIMEOUT = 6


def search_reddit(ticker: str, subreddit: str = "stocks") -> list[dict]:
    """Search a subreddit for mentions of a ticker."""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": ticker,
            "sort": "new",
            "t": "week",
            "limit": 5,
            "restrict_sr": "true",
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        posts = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            posts.append({
                "title": post.get("title", ""),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "subreddit": subreddit,
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "created_utc": post.get("created_utc", 0),
                "selftext_preview": (post.get("selftext", "") or "")[:200],
            })
        return posts
    except Exception as e:
        print(f"    Reddit r/{subreddit} error for {ticker}: {e}")
        return []


def get_stocktwits_sentiment(ticker: str) -> dict | None:
    """Get StockTwits sentiment for a ticker."""
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        messages = data.get("messages", [])

        bullish = 0
        bearish = 0
        for msg in messages[:20]:
            sentiment = msg.get("entities", {}).get("sentiment", {})
            if sentiment:
                if sentiment.get("basic") == "Bullish":
                    bullish += 1
                elif sentiment.get("basic") == "Bearish":
                    bearish += 1

        return {
            "message_count": len(messages),
            "bullish_count": bullish,
            "bearish_count": bearish,
        }
    except Exception as e:
        print(f"    StockTwits error for {ticker}: {e}")
        return None


def analyze_social(ticker: str, reddit_posts: list[dict], stocktwits: dict | None) -> dict:
    """Aggregate social data into a signal."""
    total_posts = len(reddit_posts)
    total_engagement = sum(p["score"] + p["num_comments"] for p in reddit_posts)
    high_engagement_posts = [p for p in reddit_posts if p["score"] > 50 or p["num_comments"] > 20]

    all_titles = " ".join(p["title"].lower() for p in reddit_posts)
    bull_words = ["buy", "bullish", "moon", "rocket", "long", "undervalued", "growth", "beat", "upgrade"]
    bear_words = ["sell", "bearish", "crash", "overvalued", "short", "dump", "decline", "avoid"]

    reddit_bull = sum(1 for w in bull_words if w in all_titles)
    reddit_bear = sum(1 for w in bear_words if w in all_titles)

    st_bull = stocktwits.get("bullish_count", 0) if stocktwits else 0
    st_bear = stocktwits.get("bearish_count", 0) if stocktwits else 0
    st_total = stocktwits.get("message_count", 0) if stocktwits else 0

    total_bull = reddit_bull + st_bull
    total_bear = reddit_bear + st_bear

    if total_bull > total_bear + 2:
        signal = "bullish"
    elif total_bear > total_bull + 2:
        signal = "bearish"
    else:
        signal = "neutral"

    parts = []
    if total_posts > 0:
        parts.append(f"Reddit: {total_posts} posts (engagement: {total_engagement})")
    else:
        parts.append("Reddit: No recent posts found")
    if stocktwits:
        parts.append(f"StockTwits: {st_bull} bullish / {st_bear} bearish of {st_total}")
    if high_engagement_posts:
        top = high_engagement_posts[0]
        parts.append(f"Top: \"{top['title'][:60]}\" ({top['score']}↑)")

    return {
        "ticker": ticker,
        "scout": "Social",
        "ai": "Script",
        "signal": signal,
        "summary": ". ".join(parts)[:300],
        "timestamp": timestamp(),
        "data": {
            "reddit_posts": total_posts,
            "reddit_engagement": total_engagement,
            "reddit_bull_signals": reddit_bull,
            "reddit_bear_signals": reddit_bear,
            "stocktwits_bullish": st_bull,
            "stocktwits_bearish": st_bear,
            "stocktwits_total": st_total,
            "high_engagement_posts": [
                {"title": p["title"][:80], "score": p["score"], "comments": p["num_comments"], "url": p["url"]}
                for p in high_engagement_posts[:3]
            ],
        },
    }


def fetch_all_for_ticker(ticker: str) -> dict:
    """Fetch Reddit + StockTwits for a single ticker (called in parallel)."""
    all_posts = []
    for sub in SUBREDDITS:
        all_posts.extend(search_reddit(ticker, sub))

    # Deduplicate by URL
    seen = set()
    unique = []
    for p in all_posts:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)

    stocktwits = get_stocktwits_sentiment(ticker)
    return analyze_social(ticker, unique, stocktwits)


def main():
    print("=" * 50)
    print("SCOUT 3: SOCIAL SENTIMENT (Reddit + StockTwits)")
    print("=" * 50)

    watchlist = get_watchlist()

    # Skip stocks with recent signals
    from utils import get_fresh_tickers
    fresh = get_fresh_tickers("social")
    watchlist = [s for s in watchlist if s["ticker"] not in fresh]
    if fresh:
        from registries import SCOUT_CADENCE_HOURS
        hrs = SCOUT_CADENCE_HOURS.get("social", 20)
        print(f"  Skipping {len(fresh)} stocks with recent signals (<{hrs}h old)")

    tickers = [s["ticker"] for s in watchlist]
    print(f"\n  Scanning {len(tickers)} stocks across r/{', r/'.join(SUBREDDITS)} + StockTwits")
    print(f"  Running in parallel (max 4 workers)...")
    print("-" * 50)

    start = time.time()
    signals = []

    # Fetch all tickers in parallel — 4 workers keeps us under Reddit rate limits
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_all_for_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                signals.append(result)
                emoji = "🟢" if result["signal"] == "bullish" else ("🔴" if result["signal"] == "bearish" else "🟡")
                reddit_n = result["data"]["reddit_posts"]
                st_n = result["data"]["stocktwits_total"]
                print(f"  {emoji} {ticker:6s} | {result['signal']:8s} | {reddit_n} reddit, {st_n} stocktwits")
            except Exception as e:
                print(f"  ⚠ {ticker}: failed — {e}")

    save_signals("social", signals)

    elapsed = time.time() - start
    print(f"\n  Social scout done in {elapsed:.1f}s ({len(signals)} stocks)")
    return signals


if __name__ == "__main__":
    main()
