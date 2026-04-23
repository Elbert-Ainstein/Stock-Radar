#!/usr/bin/env python3
"""
Scout 5: Earnings Calls & SEC Filings (Claude or OpenAI)
Processes earnings call transcripts and SEC filings for watchlist stocks.

This scout runs ON-DEMAND (not daily) — triggered when new earnings come in.
It uses either Claude (Anthropic) or ChatGPT (OpenAI) for deep document analysis.

ARCHITECTURE:
┌──────────────────────────────────────────────────────────────┐
│  1. TRIGGER: Earnings calendar check (daily)                 │
│     - Check if any watchlist stock reported earnings today    │
│     - If yes → proceed. If no → skip.                        │
│                                                              │
│  2. FETCH: Pull transcript + filing                          │
│     - Earnings transcript from SEC EDGAR (8-K filings)       │
│     - Or from free sources (Financial Modeling Prep API)      │
│     - 10-K / 10-Q from SEC EDGAR                            │
│                                                              │
│  3. ANALYZE: Send to Claude or OpenAI                        │
│     - Extract: forward guidance, management tone, key metrics │
│     - Compare to prior quarter language                       │
│     - Flag: accounting changes, risk factor updates           │
│                                                              │
│  4. OUTPUT: Structured signal                                │
│     - Signal: bullish/neutral/bearish                        │
│     - Thesis update recommendation                           │
│     - Key quotes from management                             │
└──────────────────────────────────────────────────────────────┘

STATUS: Structure only — implementation requires:
  - ANTHROPIC_API_KEY or OPENAI_API_KEY in .env
  - Earnings transcript source (Financial Modeling Prep API is free tier)

Usage:
    python scripts/scout_filings.py                    # check all watchlist
    python scripts/scout_filings.py --ticker LITE      # specific stock
"""
import os
import json
import time
import requests
from utils import load_env, get_watchlist, save_signals, timestamp

load_env()

# Choose AI backend: Claude preferred, OpenAI as fallback
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def fetch_earnings_transcript(ticker: str) -> str | None:
    """
    Fetch the most recent earnings call transcript.

    OPTIONS (pick one):
    1. Financial Modeling Prep API (free tier: 250 req/day)
       https://financialmodelingprep.com/api/v3/earning_call_transcript/{ticker}
    2. SEC EDGAR 8-K filings (free, but need to parse)
    3. Seeking Alpha (requires scraping, fragile)
    """
    # TODO: Implement transcript fetching
    # For now, return None to signal "no transcript available"
    print(f"  [{ticker}] Transcript fetching not yet implemented")
    print(f"  [{ticker}] Will use: Financial Modeling Prep API or SEC EDGAR 8-K")
    return None


def analyze_with_claude(transcript: str, ticker: str) -> dict:
    """
    Send transcript to Claude for deep analysis.

    Claude excels at:
    - Long document comprehension (200K context window)
    - Nuanced language analysis (management tone shifts)
    - Structured extraction (key metrics, guidance)
    - Comparing language across quarters
    """
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not set"}

    prompt = f"""Analyze this earnings call transcript for {ticker}. Return JSON:
{{
  "forward_guidance": "summary of forward guidance",
  "guidance_change": "raised / lowered / maintained / unclear",
  "management_tone": "confident / cautious / defensive / optimistic",
  "tone_vs_prior": "more_confident / less_confident / similar / unknown",
  "key_metrics": [
    {{"metric": "revenue", "value": "...", "vs_estimate": "beat/miss/inline"}},
    ...
  ],
  "red_flags": ["list any concerns"],
  "positive_signals": ["list positive takeaways"],
  "key_quotes": ["important direct quotes from management"],
  "sentiment": "bullish / bearish / neutral",
  "thesis_impact": "strengthens / weakens / neutral — and why"
}}

TRANSCRIPT:
{transcript[:50000]}"""

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
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["content"][0]["text"]
        return json.loads(content)
    except Exception as e:
        print(f"  [{ticker}] Claude error: {e}")
        return {"error": str(e)}


def analyze_with_openai(transcript: str, ticker: str) -> dict:
    """
    Send transcript to ChatGPT for analysis.

    ChatGPT excels at:
    - Fast processing of long documents
    - Good at structured extraction
    - Slightly cheaper than Claude for this use case
    """
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY not set"}

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are a financial analyst. Return only valid JSON."},
                    {"role": "user", "content": f"Analyze this earnings call for {ticker}. Extract guidance, tone, metrics, red flags. Return JSON.\n\n{transcript[:50000]}"},
                ],
                "max_tokens": 2000,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"  [{ticker}] OpenAI error: {e}")
        return {"error": str(e)}


def main():
    print("=" * 50)
    print("SCOUT 5: EARNINGS & FILINGS (Claude/OpenAI)")
    print("=" * 50)

    backend = "none"
    if ANTHROPIC_API_KEY:
        backend = "claude"
        print(f"\n  Using: Claude (Anthropic API)")
    elif OPENAI_API_KEY:
        backend = "openai"
        print(f"\n  Using: ChatGPT (OpenAI API)")
    else:
        print("\n  ⚠️ No AI API key set (ANTHROPIC_API_KEY or OPENAI_API_KEY)")
        print("  This scout needs one of these to analyze transcripts.")
        print("  Structure is ready — add a key to .env to activate.")
        return []

    watchlist = get_watchlist()
    signals = []

    for stock in watchlist:
        ticker = stock["ticker"]
        print(f"\n  Checking {ticker} for earnings data...")

        transcript = fetch_earnings_transcript(ticker)
        if not transcript:
            signals.append({
                "ticker": ticker,
                "scout": "Filings",
                "ai": "Claude" if backend == "claude" else "ChatGPT",
                "signal": "neutral",
                "summary": "No recent earnings transcript available. Will activate during earnings season.",
                "timestamp": timestamp(),
                "data": {"status": "awaiting_transcript"},
            })
            continue

        print(f"  [{ticker}] Analyzing transcript ({len(transcript)} chars)...")
        if backend == "claude":
            analysis = analyze_with_claude(transcript, ticker)
        else:
            analysis = analyze_with_openai(transcript, ticker)

        sentiment = analysis.get("sentiment", "neutral")
        guidance = analysis.get("guidance_change", "unknown")
        tone = analysis.get("management_tone", "unknown")

        summary = f"Guidance: {guidance}. Tone: {tone}. {analysis.get('thesis_impact', 'No thesis impact assessment.')}"

        signals.append({
            "ticker": ticker,
            "scout": "Filings",
            "ai": "Claude" if backend == "claude" else "ChatGPT",
            "signal": sentiment,
            "summary": summary[:300],
            "timestamp": timestamp(),
            "data": {"analysis": analysis},
        })

    save_signals("filings", signals)
    return signals


if __name__ == "__main__":
    main()
