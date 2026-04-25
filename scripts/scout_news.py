#!/usr/bin/env python3
"""
Scout 2: News Scanner (Perplexity Search API)
Searches for recent financial news for each watchlist stock.

Usage:
    python scripts/scout_news.py
"""
import os
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from utils import load_env, get_watchlist, save_signals, timestamp

load_env()

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
SEARCH_URL = "https://api.perplexity.ai/search"


def search_stock_news(ticker: str, company_name: str) -> dict | None:
    """Search Perplexity for recent news about a stock.

    We prefer the Sonar chat endpoint because it accepts a structured-output
    system prompt and returns the events[] array the event reasoner consumes.
    The raw /search endpoint technically works, but only returns snippets —
    no event extraction. Fall back to /search if sonar fails (e.g. rate limit
    or model unavailable), even though that path emits zero events.
    """
    if not PERPLEXITY_API_KEY:
        print("  [ERROR] PERPLEXITY_API_KEY not set in .env")
        return None

    sonar_result = search_stock_news_sonar(ticker, company_name)
    if sonar_result is not None:
        return sonar_result

    # Fallback: /search endpoint (no structured events — just snippets).
    query = f"{ticker} {company_name} stock news latest developments earnings analyst"
    try:
        resp = requests.post(
            SEARCH_URL,
            headers={
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "max_results": 5,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"  [{ticker}] Perplexity /search error: {e}")
        return None
    except Exception as e:
        print(f"  [{ticker}] Error: {e}")
        return None


def search_stock_news_sonar(ticker: str, company_name: str) -> dict | None:
    """Fallback: Use the Sonar chat completions endpoint with web search."""
    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a financial news analyst. Return ONLY valid JSON (no markdown fences, no commentary). "
                            "Analyze the most important recent news for the given stock and return this exact structure:\n"
                            "{\n"
                            "  \"sentiment\": \"bullish\" | \"bearish\" | \"neutral\",\n"
                            "  \"confidence\": \"high\" | \"medium\" | \"low\",\n"
                            "  \"summary\": \"2-3 sentence overview of the news landscape\",\n"
                            "  \"key_events\": [\"event 1\", \"event 2\", \"event 3\"],\n"
                            "  \"catalyst_upcoming\": \"next major catalyst or null\",\n"
                            "  \"analyst_actions\": \"recent upgrades/downgrades or none\",\n"
                            "  \"events\": [\n"
                            "    {\n"
                            "      \"summary\": \"one-sentence factual description of the event\",\n"
                            "      \"type\": \"one of: ma_target, ma_acquirer, regulatory_approval, regulatory_rejection, earnings_beat_raise, earnings_miss_cut, capacity_expansion, supply_constraint, customer_win_major, customer_loss_major, product_launch, product_delay, exec_change_positive, exec_change_negative, litigation_adverse, litigation_favorable, competitive_threat, sector_tailwind, sector_headwind, buyback_large, dividend_cut\",\n"
                            "      \"direction\": \"up\" | \"down\",\n"
                            "      \"date\": \"YYYY-MM-DD or null\",\n"
                            "      \"source\": \"publication name or null\",\n"
                            "      \"url\": \"source URL or null\",\n"
                            "      \"rationale\": \"one sentence: why this event matters for the thesis\"\n"
                            "    }\n"
                            "  ],\n"
                            "  \"forward_guidance\": {\n"
                            "    \"guided_revenue_growth_y1_pct\": null,\n"
                            "    \"guided_revenue_growth_y1_source\": null,\n"
                            "    \"guided_next_q_revenue_low_usd\": null,\n"
                            "    \"guided_next_q_revenue_high_usd\": null,\n"
                            "    \"guided_next_q_revenue_source\": null,\n"
                            "    \"guided_op_margin_pct\": null,\n"
                            "    \"guided_op_margin_source\": null,\n"
                            "    \"guidance_date\": null,\n"
                            "    \"guidance_confidence\": \"high|medium|low|null\"\n"
                            "  }\n"
                            "}\n"
                            "Rules for the events array:\n"
                            " - Include only MATERIAL events from the last 90 days (customer wins, capacity moves, approvals, product launches, exec changes, M&A, guidance changes, major litigation, etc.).\n"
                            " - Skip noise: daily price moves, routine analyst price-target tweaks, generic market commentary.\n"
                            " - Pick the CLOSEST matching type from the list above. Do not invent new types.\n"
                            " - Up to 6 events maximum. Prefer quality over quantity.\n"
                            " - Each event summary must be factual (what happened), not interpretive (why it's good).\n"
                            "Rules for forward_guidance — STRICT:\n"
                            " - Fill these fields ONLY when management has made an EXPLICIT public statement (earnings call, press release, 10-Q/K, investor day). Never infer from analyst consensus, TAM growth, or past results.\n"
                            " - Every non-null numeric field REQUIRES a matching _source string with a verbatim quote identifying the speaker (e.g. CEO, CFO), the event (e.g. Q4 FY25 earnings call), and the date.\n"
                            " - guided_revenue_growth_y1_pct is full-FY revenue growth YoY (e.g. 85 for 85%), not a quarter.\n"
                            " - guided_next_q_revenue_low_usd / _high_usd are the raw guidance range in USD (e.g. 780000000, 830000000 for a $780-830M guide).\n"
                            " - guided_op_margin_pct is the midpoint of any guided operating margin range, non-GAAP or GAAP.\n"
                            " - If you cannot source a specific field with a verbatim quote, leave BOTH its numeric and _source as null. False positives are unacceptable — the downstream valuation engine trusts these."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"What are the most important recent news developments for {ticker} ({company_name})? "
                            f"Focus on: earnings, analyst ratings, product launches, partnerships, capacity/facility moves, "
                            f"management changes, regulatory actions, M&A, and macro factors affecting this stock. "
                            f"Populate the structured 'events' array with each material catalyst."
                        )
                    }
                ],
                "max_tokens": 800,
                "temperature": 0.1,
                "web_search": True,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract the response content
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

        return {
            "type": "sonar",
            "content": content,
            "citations": citations,
        }
    except Exception as e:
        print(f"  [{ticker}] Sonar fallback also failed: {e}")
        return None


def parse_search_results(ticker: str, raw_response: dict) -> dict:
    """Parse Perplexity response into a structured signal."""
    if not raw_response:
        return {
            "ticker": ticker,
            "scout": "News",
            "ai": "Perplexity",
            "signal": "neutral",
            "summary": "Could not fetch news data.",
            "timestamp": timestamp(),
            "data": {"sources": [], "raw": None},
        }

    # Handle Sonar (chat) response — Perplexity returns structured JSON with sentiment
    if raw_response.get("type") == "sonar":
        content = raw_response.get("content", "")
        citations = raw_response.get("citations", [])

        # Try to parse Perplexity's structured JSON response
        signal = "neutral"
        summary = ""
        parsed = None

        try:
            # Strip markdown fences if present
            clean = content.strip()
            clean = re.sub(r'^```(?:json)?\s*', '', clean)
            clean = re.sub(r'\s*```$', '', clean)
            parsed = json.loads(clean)

            # Use Perplexity's own sentiment judgment (much more reliable than keyword counting)
            signal = parsed.get("sentiment", "neutral").lower()
            if signal not in ("bullish", "bearish", "neutral"):
                signal = "neutral"

            # Build summary from structured fields
            summary = parsed.get("summary", "")
            key_events = parsed.get("key_events", [])
            if key_events and not summary:
                summary = ". ".join(key_events[:3])
            catalyst = parsed.get("catalyst_upcoming")
            if catalyst and catalyst != "null":
                summary += f" | Upcoming: {catalyst}"

        except (json.JSONDecodeError, AttributeError):
            # Perplexity returned prose instead of JSON — fall back to keyword analysis
            content_lower = content.lower()
            bull_words = ["upgrade", "beat", "exceed", "growth", "bullish", "outperform", "buy", "raise", "positive", "accelerat"]
            bear_words = ["downgrade", "miss", "decline", "bearish", "underperform", "sell", "cut", "negative", "slow", "warn"]
            bull_count = sum(1 for w in bull_words if w in content_lower)
            bear_count = sum(1 for w in bear_words if w in content_lower)
            if bull_count > bear_count + 1:
                signal = "bullish"
            elif bear_count > bull_count + 1:
                signal = "bearish"
            summary = content[:300].replace("\n", " ").strip()

        if not summary:
            summary = content[:300].replace("\n", " ").strip()
        if len(summary) > 300:
            summary = summary[:297] + "..."

        # Extract events array — validated against the taxonomy.
        # Unknown types are dropped rather than fabricated.
        events = []
        if parsed and isinstance(parsed.get("events"), list):
            try:
                from event_templates import ALL_TYPE_IDS
            except ImportError:
                ALL_TYPE_IDS = []
            for e in parsed["events"][:10]:
                if not isinstance(e, dict):
                    continue
                etype = (e.get("type") or "").strip()
                if ALL_TYPE_IDS and etype not in ALL_TYPE_IDS:
                    # Unknown type — skip rather than invent
                    continue
                summ = (e.get("summary") or "").strip()
                if not summ:
                    continue
                events.append({
                    "summary": summ[:280],
                    "type": etype,
                    "direction": e.get("direction") if e.get("direction") in ("up", "down") else None,
                    "date": e.get("date") or None,
                    "source": (e.get("source") or None),
                    "url": (e.get("url") or None),
                    "rationale": (e.get("rationale") or "").strip()[:280],
                    "detected_by": "News",
                })

        return {
            "ticker": ticker,
            "scout": "News",
            "ai": "Perplexity",
            "signal": signal,
            "summary": summary,
            "timestamp": timestamp(),
            "data": {
                "parsed_analysis": parsed,
                "citations": citations[:5],
                "events": events,
                "full_content": content if not parsed else None,
            },
        }

    # Handle Search API response
    results = raw_response.get("results", [])
    if not results:
        return {
            "ticker": ticker,
            "scout": "News",
            "ai": "Perplexity",
            "signal": "neutral",
            "summary": "No recent news found.",
            "timestamp": timestamp(),
            "data": {"sources": [], "raw": None},
        }

    # Compile snippets and detect sentiment
    sources = []
    all_text = ""
    for r in results[:5]:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        sources.append({"title": title, "url": url, "snippet": snippet[:200]})
        all_text += f" {title} {snippet}"

    # Simple keyword sentiment
    text_lower = all_text.lower()
    bullish_words = ["upgrade", "beat", "exceed", "growth", "bullish", "outperform", "buy", "raise", "positive"]
    bearish_words = ["downgrade", "miss", "decline", "bearish", "underperform", "sell", "cut", "negative"]

    bull_count = sum(1 for w in bullish_words if w in text_lower)
    bear_count = sum(1 for w in bearish_words if w in text_lower)

    if bull_count > bear_count + 1:
        signal = "bullish"
    elif bear_count > bull_count + 1:
        signal = "bearish"
    else:
        signal = "neutral"

    summary_parts = [s["title"] for s in sources[:3]]
    summary = " | ".join(summary_parts) if summary_parts else "No significant news."

    return {
        "ticker": ticker,
        "scout": "News",
        "ai": "Perplexity",
        "signal": signal,
        "summary": summary[:300],
        "timestamp": timestamp(),
        "data": {
            "sources": sources,
            "bull_signals": bull_count,
            "bear_signals": bear_count,
        },
    }


def main():
    print("=" * 50)
    print("SCOUT 2: NEWS SCANNER (Perplexity)")
    print("=" * 50)

    if not PERPLEXITY_API_KEY:
        print("\n  ❌ PERPLEXITY_API_KEY not set!")
        print("  Add your key to .env file:")
        print("  PERPLEXITY_API_KEY=pplx-xxxxxxxxxxxx")
        return []

    watchlist = get_watchlist()

    # Skip stocks with recent signals
    from utils import get_fresh_tickers
    fresh = get_fresh_tickers("news")
    before = len(watchlist)
    watchlist = [s for s in watchlist if s["ticker"] not in fresh]
    if fresh:
        from registries import SCOUT_CADENCE_HOURS
        hrs = SCOUT_CADENCE_HOURS.get("news", 18)
        print(f"  Skipping {before - len(watchlist)} stocks with recent signals (<{hrs}h old)")

    print(f"\nScanning news for {len(watchlist)} stocks")
    print("-" * 50)

    if not watchlist:
        print("  All stocks have recent news — nothing to do")
        return []

    def _scan_stock(stock):
        """Scan news for a single stock (called in parallel)."""
        ticker = stock["ticker"]
        name = stock["name"]
        raw = search_stock_news(ticker, name)
        result = parse_search_results(ticker, raw)
        print(f"  [{ticker}] Signal: {result['signal']} — {result['summary'][:60]}")
        time.sleep(0.5)  # Stagger Perplexity API calls slightly
        return result

    # Parallel news scanning — 3 workers to stay within Perplexity rate limits
    signals = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_scan_stock, s): s["ticker"] for s in watchlist}
        for future in as_completed(futures):
            try:
                result = future.result()
                signals.append(result)
            except Exception as e:
                ticker = futures[future]
                print(f"  [{ticker}] Error: {e}")

    save_signals("news", signals)

    print("\n" + "=" * 50)
    print("NEWS SCANNER SUMMARY")
    print("=" * 50)
    for s in signals:
        emoji = "🟢" if s["signal"] == "bullish" else ("🔴" if s["signal"] == "bearish" else "🟡")
        print(f"  {emoji} {s['ticker']:6s} | {s['summary'][:70]}")

    return signals


if __name__ == "__main__":
    main()
