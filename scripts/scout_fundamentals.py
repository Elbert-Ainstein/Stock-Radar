#!/usr/bin/env python3
"""
Scout 7: Business Fundamentals Deep Dive (Perplexity research → Claude analysis)

Two-stage architecture:
  1. RESEARCH: Perplexity gathers current business intelligence (web search)
  2. ANALYSIS: Claude performs deep structured reasoning

Parallelized: all Perplexity queries for a stock run concurrently,
and multiple stocks are processed in parallel.

Usage:
    python scripts/scout_fundamentals.py                 # all watchlist
    python scripts/scout_fundamentals.py --ticker LITE   # specific stock
"""
import os
import json
import re
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import load_env, get_watchlist, save_signals, timestamp

load_env()

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

REQUEST_TIMEOUT = 20  # Shorter timeout — don't let one slow request block everything

# ─── Perplexity research queries ───
RESEARCH_QUERIES = [
    {
        "id": "moat",
        "query": "{ticker} {name} competitive advantage moat barriers to entry switching costs network effects",
        "focus": "What gives this company a durable competitive advantage? What are the barriers to entry?"
    },
    {
        "id": "revenue",
        "query": "{ticker} {name} revenue breakdown segments products services geography customers",
        "focus": "Break down revenue by product/service, geography, and major customers. Customer concentration?"
    },
    {
        "id": "tam",
        "query": "{ticker} {name} total addressable market size market share growth opportunity",
        "focus": "How large is the TAM? Current market share? How fast is the market growing?"
    },
    {
        "id": "management",
        "query": "{ticker} {name} CEO management team insider ownership track record capital allocation",
        "focus": "Who leads the company? Track record? Insider ownership? Capital allocation history?"
    },
    {
        "id": "competition",
        "query": "{ticker} {name} competitors market position vs peers comparison strengths weaknesses",
        "focus": "Main competitors? How does the company compare on growth, margins, market position?"
    },
    {
        "id": "risks",
        "query": "{ticker} {name} risk factors regulatory supply chain customer concentration threats",
        "focus": "Biggest risks? Regulatory, concentration, macro sensitivity, technology disruption?"
    },
    {
        "id": "guidance",
        "query": "{ticker} {name} management guidance revenue outlook next fiscal year operating margin earnings call forecast",
        "focus": "What has management EXPLICITLY guided for next year's revenue growth, next quarter's revenue range, and operating margin? Include verbatim quotes with the date of the guidance and the source (earnings call, investor day, press release, 10-Q/10-K). Distinguish management guidance from analyst consensus. If no recent guidance exists, say so explicitly."
    },
]


def _perplexity_single_query(ticker: str, name: str, sector: str, rq: dict) -> tuple[str, dict]:
    """Run a single Perplexity research query. Returns (area_id, result_dict)."""
    area_id = rq["id"]
    query_text = rq["query"].format(ticker=ticker, name=name)
    focus = rq["focus"]

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
                            "You are an equity research analyst. Provide factual, data-rich responses "
                            "with specific numbers, percentages, and dollar amounts. No disclaimers."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"For {ticker} ({name}, {sector} sector):\n\n"
                            f"{focus}\n\n"
                            f"Include specific numbers and recent data points. Facts only."
                        ),
                    },
                ],
                "max_tokens": 800,
                "temperature": 0.1,
                "web_search": True,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])
        return area_id, {"content": content, "citations": citations[:5] if citations else []}

    except Exception as e:
        print(f"    [{ticker}/{area_id}] Perplexity error: {e}")
        return area_id, {"content": "", "citations": []}


def perplexity_research(ticker: str, name: str, sector: str) -> dict:
    """Stage 1: Run all Perplexity queries in parallel for one stock."""
    if not PERPLEXITY_API_KEY:
        print(f"  [{ticker}] PERPLEXITY_API_KEY not set")
        return {}

    research = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_perplexity_single_query, ticker, name, sector, rq): rq["id"]
            for rq in RESEARCH_QUERIES
        }
        for future in as_completed(futures):
            area_id, result = future.result()
            research[area_id] = result
            if result["content"]:
                print(f"    [{ticker}] {area_id}: OK ({len(result['content'])} chars)")

    return research


# ─── Claude analysis prompt ───
ANALYSIS_PROMPT = """You are a senior equity research analyst writing a deep-dive business assessment.

COMPANY: {ticker} ({name}), {sector} sector

RESEARCH DATA:
{research_text}

Based on this research, produce a structured JSON analysis. Return ONLY valid JSON — no markdown fences, no commentary.

{{
  "moat_analysis": {{
    "moat_type": "wide|narrow|none",
    "moat_sources": ["source1", "source2"],
    "moat_durability": "strengthening|stable|weakening",
    "moat_summary": "2-3 sentence assessment",
    "moat_score": 8
  }},
  "revenue_analysis": {{
    "total_revenue": "$X.XB",
    "revenue_breakdown": [
      {{"segment": "name", "pct_of_total": 45, "growth_rate": "XX%", "trend": "accelerating|stable|decelerating"}}
    ],
    "customer_concentration": "high|moderate|low",
    "recurring_revenue_pct": 40,
    "revenue_quality_score": 7
  }},
  "tam_analysis": {{
    "tam_size": "$XXB",
    "current_market_share_pct": 5,
    "market_growth_rate": "XX% CAGR",
    "share_trajectory": "gaining|stable|losing",
    "tam_score": 8
  }},
  "management_analysis": {{
    "ceo_name": "Name",
    "insider_ownership_pct": 3,
    "management_track_record": "strong|mixed|weak",
    "capital_allocation_quality": "excellent|good|fair|poor",
    "management_score": 7
  }},
  "unit_economics": {{
    "gross_margin_pct": 45,
    "operating_margin_pct": 20,
    "roic_pct": 15,
    "fcf_margin_pct": 18,
    "unit_economics_score": 7
  }},
  "competitive_position": {{
    "market_position": "leader|challenger|niche|emerging",
    "top_competitors": ["comp1", "comp2"],
    "competitive_score": 7
  }},
  "risk_assessment": {{
    "key_risks": [
      {{"risk": "description", "severity": "high|medium|low", "likelihood": "high|medium|low"}}
    ],
    "risk_score": 6
  }},
  "overall": {{
    "business_quality_score": 7.5,
    "signal": "bullish|neutral|bearish",
    "one_line_thesis": "One sentence thesis",
    "bull_case": "2-3 sentences",
    "bear_case": "2-3 sentences",
    "key_monitoring_points": ["point1", "point2", "point3"]
  }},
  "forward_guidance": {{
    "comment": "Structured management guidance — ONLY fill these when the research text contains EXPLICIT management statements (earnings call, press release, 10-Q, 10-K, investor day). Do NOT infer. Do NOT use analyst estimates or TAM growth. If management did not provide the guidance, leave the numeric field null and set the corresponding _source to null. Every non-null numeric MUST be backed by a verbatim quote in _source.",
    "guided_revenue_growth_y1_pct": null,
    "guided_revenue_growth_y1_source": null,
    "guided_revenue_range_usd_y1_low": null,
    "guided_revenue_range_usd_y1_high": null,
    "guided_revenue_range_source": null,
    "guided_op_margin_pct": null,
    "guided_op_margin_source": null,
    "guided_gross_margin_pct": null,
    "guided_gross_margin_source": null,
    "guidance_period": null,
    "guidance_date": null,
    "guidance_confidence": "high|medium|low|null"
  }}
}}

All scores are 1-10. Be specific with numbers. Use null if data is unavailable.

CRITICAL — forward_guidance rules:
- guided_revenue_growth_y1_pct must be a number (e.g. 85 for 85%) that came from a management statement about next fiscal year or full-year revenue growth. NOT a quarter-specific guide. NOT analyst consensus. NOT TAM growth. NOT past results.
- Every numeric field needs a matching _source string containing a verbatim quote from the research (e.g. "management guided FY2026 revenue growth of 80-90% at the Q1 earnings call on 2026-02-05"). If you cannot produce a verbatim source quote, leave BOTH the numeric and _source null.
- guided_op_margin_pct must be a non-GAAP or GAAP operating margin expressly guided by management. Use the midpoint if a range is given.
- guidance_confidence: "high" if multiple sources confirm and date is within last 90 days; "medium" if one reputable source and date is within last 180 days; "low" otherwise.
- When in doubt, leave fields null. False positives are MUCH worse than false negatives here — the downstream valuation engine will trust these numbers."""


def analyze_with_claude(research: dict, ticker: str, name: str, sector: str) -> dict:
    """Stage 2: Send research to Claude for deep analysis."""
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not set"}

    research_text = ""
    for area_id, data in research.items():
        research_text += f"\n=== {area_id.upper()} ===\n{data.get('content', 'No data')}\n"

    prompt = ANALYSIS_PROMPT.format(
        ticker=ticker, name=name, sector=sector, research_text=research_text
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-6",
                "max_tokens": 4000,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [{}])[0].get("text", "")

        clean = content.strip()
        clean = re.sub(r'^```(?:json)?\s*', '', clean)
        clean = re.sub(r'\s*```$', '', clean)
        return json.loads(clean)

    except json.JSONDecodeError as e:
        print(f"  [{ticker}] Claude returned non-JSON: {e}")
        return {"error": "Failed to parse Claude response"}
    except Exception as e:
        print(f"  [{ticker}] Claude API error: {e}")
        return {"error": str(e)}


def analyze_stock(ticker: str, name: str, sector: str) -> dict:
    """Full two-stage analysis for a single stock."""
    print(f"\n  --- FUNDAMENTALS: {ticker} ({name}) ---")

    # Stage 1: Perplexity research (parallelized per query)
    print(f"  [{ticker}] Stage 1: Perplexity research (6 queries parallel)...")
    start = time.time()
    research = perplexity_research(ticker, name, sector)
    research_time = time.time() - start
    print(f"  [{ticker}] Research done in {research_time:.1f}s")

    if not any(r.get("content") for r in research.values()):
        print(f"  [{ticker}] No research data gathered — skipping analysis")
        return {
            "ticker": ticker,
            "scout": "Fundamentals",
            "ai": "None",
            "signal": "neutral",
            "summary": "Could not gather business research data.",
            "timestamp": timestamp(),
            "data": {},
        }

    # Stage 2: Claude analysis
    if not ANTHROPIC_API_KEY:
        print(f"  [{ticker}] No ANTHROPIC_API_KEY — returning raw research only")
        return {
            "ticker": ticker,
            "scout": "Fundamentals",
            "ai": "Perplexity",
            "signal": "neutral",
            "summary": "Research gathered but no Claude key for deep analysis.",
            "timestamp": timestamp(),
            "data": {"research": {k: v.get("content", "")[:500] for k, v in research.items()}},
        }

    print(f"  [{ticker}] Stage 2: Claude analysis...")
    analysis = analyze_with_claude(research, ticker, name, sector)

    if "error" in analysis:
        print(f"  [{ticker}] Analysis failed: {analysis['error']}")
        return {
            "ticker": ticker,
            "scout": "Fundamentals",
            "ai": "Failed",
            "signal": "neutral",
            "summary": f"Analysis failed: {analysis['error'][:100]}",
            "timestamp": timestamp(),
            "data": {"research": {k: v.get("content", "")[:500] for k, v in research.items()}},
        }

    # Extract signal and summary
    overall = analysis.get("overall", {})
    signal = overall.get("signal", "neutral")
    if signal not in ("bullish", "bearish", "neutral"):
        signal = "neutral"

    bq_score = overall.get("business_quality_score", 5)
    thesis = overall.get("one_line_thesis", "")
    moat_type = analysis.get("moat_analysis", {}).get("moat_type", "unknown")
    moat_score = analysis.get("moat_analysis", {}).get("moat_score", 0)

    summary = f"[BQ:{bq_score}/10 Moat:{moat_type}] {thesis}"[:300]

    print(f"  [{ticker}] BQ: {bq_score}/10 | Moat: {moat_type} ({moat_score}/10) | {signal}")

    return {
        "ticker": ticker,
        "scout": "Fundamentals",
        "ai": "Claude",
        "signal": signal,
        "summary": summary,
        "timestamp": timestamp(),
        "data": {
            "analysis": analysis,
            "citations": {k: v.get("citations", []) for k, v in research.items()},
        },
    }


def _process_stock_wrapper(stock: dict) -> dict:
    """Wrapper for parallel stock processing."""
    return analyze_stock(stock["ticker"], stock["name"], stock.get("sector", "Unknown"))


def main():
    print("=" * 50)
    print("SCOUT 7: BUSINESS FUNDAMENTALS (Perplexity + Claude)")
    print("=" * 50)

    if not PERPLEXITY_API_KEY:
        print("\n  PERPLEXITY_API_KEY not set — cannot run fundamentals scout")
        return []

    if not ANTHROPIC_API_KEY:
        print("\n  ANTHROPIC_API_KEY not set — will return raw research only")

    print(f"\n  Research: Perplexity Sonar (parallel)")
    print(f"  Analysis: {'Claude Sonnet' if ANTHROPIC_API_KEY else 'None (no key)'}")

    # Check for --ticker flag
    specific_ticker = None
    for i, arg in enumerate(sys.argv):
        if arg == "--ticker" and i + 1 < len(sys.argv):
            specific_ticker = sys.argv[i + 1].upper()

    watchlist = get_watchlist()
    if specific_ticker:
        watchlist = [s for s in watchlist if s["ticker"] == specific_ticker]
        if not watchlist:
            print(f"\n  Ticker {specific_ticker} not found in watchlist")
            return []

    # Skip stocks with recent signals (avoid redundant Perplexity + Claude calls)
    from utils import get_fresh_tickers
    fresh = get_fresh_tickers("fundamentals")
    before = len(watchlist)
    watchlist = [s for s in watchlist if s["ticker"] not in fresh]
    if fresh:
        from registries import SCOUT_CADENCE_HOURS
        hrs = SCOUT_CADENCE_HOURS.get("fundamentals", 48)
        print(f"  Skipping {before - len(watchlist)} stocks with recent signals (<{hrs}h old)")

    print(f"  Analyzing {len(watchlist)} stocks (2 at a time)")
    print("-" * 50)

    if not watchlist:
        print("  All stocks have recent fundamentals — nothing to do")
        return []

    start = time.time()
    signals = []

    # Process 2 stocks at a time to stay within API rate limits
    # Each stock's Perplexity queries are already parallelized internally
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_process_stock_wrapper, s): s["ticker"] for s in watchlist}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                signals.append(result)
                emoji = "+" if result["signal"] == "bullish" else ("-" if result["signal"] == "bearish" else "=")
                bq = result.get("data", {}).get("analysis", {}).get("overall", {}).get("business_quality_score", "?")
                print(f"  [{emoji}] {ticker:6s} | BQ:{bq}/10 | {result['summary'][:60]}")
            except Exception as e:
                print(f"  [!] {ticker}: failed — {e}")

    save_signals("fundamentals", signals)

    elapsed = time.time() - start
    print(f"\n  Fundamentals scout done in {elapsed:.1f}s ({len(signals)} stocks)")
    return signals


if __name__ == "__main__":
    main()
