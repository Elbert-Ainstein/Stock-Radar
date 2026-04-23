#!/usr/bin/env python3
"""
Discovery Scanner — 3-Stage Universe Expansion for 10x Candidates

Stage 1: WIDE NET (Free)
  - Static universe.txt (~430 tickers)
  - Dynamic Finviz screener (high-growth filters → adds fresh tickers)
  - Yahoo Finance screener (revenue growth + margin filters)
  - Dedup + merge → ~500-800 unique tickers

Stage 2: QUANT FILTER (Free)
  - yfinance fundamentals scan on all Stage 1 tickers
  - 10x-focused scoring: revenue growth, margins, TAM proxy, valuation
  - Hard filters: market cap $500M-$100B, revenue growth >15%, gross margin >30%
  - Output: top ~50-80 candidates scored and ranked

Stage 3: AI VALIDATION (Paid — only top ~10-15)
  - Perplexity research: TAM, competitive position, catalysts
  - Claude synthesis: generate thesis, kill condition, criteria, target range
  - Only runs on stocks scoring above the AI threshold
  - Output: fully formed watchlist-ready candidates

Usage:
    python scripts/scout_discovery.py                # full 3-stage scan
    python scripts/scout_discovery.py --quick         # Stage 1+2 only (no AI)
    python scripts/scout_discovery.py --stage1-only   # just refresh the universe
    python scripts/scout_discovery.py --ai-top N      # validate top N (default 10)
"""
from __future__ import annotations

import sys
import os
import json
import time
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yfinance as yf

from utils import load_env, get_watchlist
load_env()

# ─── Paths ───
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROGRESS_FILE = DATA_DIR / ".discovery-progress"
UNIVERSE_FILE = Path(__file__).resolve().parent / "data" / "universe.txt"
OUTPUT_FILE = DATA_DIR / "discovery_latest.json"

# ─── Thresholds ───
# Stage 2: hard filters for 10x potential
MIN_MARKET_CAP_B = 0.5       # $500M minimum
MAX_MARKET_CAP_B = 100        # $100B maximum (above this, hard to 10x)
MIN_REVENUE_GROWTH = 0.15     # 15% YoY minimum
MIN_GROSS_MARGIN = 0.30       # 30% minimum gross margin
CANDIDATE_SCORE_THRESHOLD = 5.0  # minimum 10x score to be a candidate

# Stage 3: AI validation
AI_SCORE_THRESHOLD = 7.0       # minimum score to warrant AI deep-dive
DEFAULT_AI_TOP_N = 10          # validate top N candidates with AI

# API keys
PERPLEXITY_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ═══════════════════════════════════════════════════════════════
# STAGE 1: WIDE NET — Collect tickers from multiple sources
# ═══════════════════════════════════════════════════════════════

def load_static_universe() -> set[str]:
    """Load tickers from universe.txt (hand-curated list)."""
    tickers = set()
    if not UNIVERSE_FILE.exists():
        print("  [!] universe.txt not found")
        return tickers
    with open(UNIVERSE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tickers.add(line.upper())
    print(f"  [static] {len(tickers)} tickers from universe.txt")
    return tickers


def scrape_finviz_screener() -> set[str]:
    """Scrape Finviz screener for high-growth stocks.

    Filters: Market cap $300M-$100B, revenue growth >15%, EPS growth >15%
    Returns up to ~200 tickers. Free, no API key needed.
    """
    tickers = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Finviz screener URL with growth filters
    # fa_salesqoq_o15 = quarterly revenue growth >15%
    # fa_epsqoq_o15 = quarterly EPS growth >15%
    # cap_smallover = market cap > $300M
    # cap_largeover is excluded (>$200B) by omitting it
    screens = [
        # High revenue growth + positive margins
        "v=111&f=fa_salesqoq_o15,fa_grossmargin_o30,cap_smallover&ft=4",
        # High EPS growth + reasonable valuation
        "v=111&f=fa_epsqoq_o15,fa_peg_u2,cap_smallover&ft=4",
        # Recent IPOs with strong growth (under 3 years)
        "v=111&f=ipo_more3,fa_salesqoq_o25,cap_smallover&ft=4",
    ]

    for screen_url in screens:
        try:
            url = f"https://finviz.com/screener.ashx?{screen_url}"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue

            # Extract tickers from the HTML table
            # Finviz uses <a class="screener-link-primary" href="quote.ashx?t=TICKER">
            matches = re.findall(
                r'href="quote\.ashx\?t=([A-Z]{1,5})(?:&|")',
                resp.text
            )
            for m in matches:
                if 1 <= len(m) <= 5:
                    tickers.add(m.upper())

            time.sleep(1)  # respect rate limit
        except Exception as e:
            print(f"  [finviz] Screen failed: {e}")

    print(f"  [finviz] {len(tickers)} tickers from screener")
    return tickers


def fetch_yahoo_screener() -> set[str]:
    """Use yfinance's built-in screener for high-growth US stocks.

    This queries Yahoo Finance's screener API for growth stocks.
    Free, no API key needed.
    """
    tickers = set()

    # Use predefined Yahoo Finance screener queries via yfinance
    try:
        # Aggressive growth screener — top revenue growers
        screener_queries = [
            "aggressive_small_caps",
            "small_cap_gainers",
            "undervalued_growth_stocks",
            "growth_technology_stocks",
        ]

        for query in screener_queries:
            try:
                sc = yf.Screener()
                sc.set_predefined_body(query)
                result = sc.response
                # Extract quotes from response
                quotes = result.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                for q in quotes:
                    symbol = q.get("symbol", "")
                    if symbol and 1 <= len(symbol) <= 5 and symbol.isalpha():
                        tickers.add(symbol.upper())
            except Exception:
                pass
            time.sleep(0.5)

    except Exception as e:
        print(f"  [yahoo] Screener failed: {e}")

    print(f"  [yahoo] {len(tickers)} tickers from screener")
    return tickers


def stage1_collect_universe(watchlist_tickers: set[str]) -> list[str]:
    """Stage 1: Collect tickers from all sources, dedup, exclude watchlist."""
    print("\n" + "─" * 50)
    print("  STAGE 1: WIDE NET — Collecting tickers")
    print("─" * 50)

    all_tickers: set[str] = set()

    # Source 1: Static universe
    all_tickers |= load_static_universe()

    # Source 2: Finviz screener (dynamic, growth-filtered)
    try:
        finviz = scrape_finviz_screener()
        all_tickers |= finviz
    except Exception as e:
        print(f"  [finviz] Failed: {e}")

    # Source 3: Yahoo Finance screener
    try:
        yahoo = fetch_yahoo_screener()
        all_tickers |= yahoo
    except Exception as e:
        print(f"  [yahoo] Failed: {e}")

    # Exclude watchlist stocks (already tracked)
    before = len(all_tickers)
    all_tickers -= watchlist_tickers
    excluded = before - len(all_tickers)
    if excluded:
        print(f"  Excluded {excluded} stocks already on watchlist")

    # Remove ETFs and common non-stock tickers
    etf_suffixes = {"X", "Q"}  # crude filter
    cleaned = set()
    for t in all_tickers:
        # Skip anything with dots (BRK.B → BRK-B handled elsewhere), numbers, or >5 chars
        if "." in t or len(t) > 5:
            continue
        cleaned.add(t)

    universe = sorted(cleaned)
    print(f"\n  Stage 1 result: {len(universe)} unique tickers to scan")
    return universe


# ═══════════════════════════════════════════════════════════════
# STAGE 2: QUANT FILTER — Score all tickers on 10x potential
# ═══════════════════════════════════════════════════════════════

def _fetch_stock_data(ticker: str) -> dict | None:
    """Fetch fundamentals from yfinance for a single ticker. Fast path."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info or "marketCap" not in info:
            return None

        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        if not price or price <= 0:
            return None

        market_cap = info.get("marketCap", 0) or 0
        market_cap_b = market_cap / 1e9

        # Hard filters — skip early to save time
        if market_cap_b < MIN_MARKET_CAP_B or market_cap_b > MAX_MARKET_CAP_B:
            return None

        revenue_growth = info.get("revenueGrowth", 0) or 0
        if revenue_growth < MIN_REVENUE_GROWTH:
            return None

        gross_margin = info.get("grossMargins", 0) or 0
        if gross_margin < MIN_GROSS_MARGIN:
            return None

        # Passed hard filters — collect full data
        prev_close = info.get("previousClose", price) or price
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        earnings_growth = info.get("earningsGrowth", 0) or 0
        operating_margin = info.get("operatingMargins", 0) or 0
        profit_margin = info.get("profitMargins", 0) or 0
        pe_ratio = info.get("trailingPE", 0) or 0
        forward_pe = info.get("forwardPE", 0) or 0
        ps_ratio = info.get("priceToSalesTrailing12Months", 0) or 0
        peg_ratio = info.get("pegRatio", 0) or 0
        fifty_two_high = info.get("fiftyTwoWeekHigh", 0) or 0
        beta = info.get("beta", 0) or 0
        short_pct = info.get("shortPercentOfFloat", 0) or 0
        free_cash_flow = info.get("freeCashflow", 0) or 0

        distance_from_high = ((fifty_two_high - price) / fifty_two_high * 100) if fifty_two_high else 0

        # HQ location for globe visualization
        hq_city = info.get("city", "")
        hq_state = info.get("state", "")
        hq_country = info.get("country", "")

        return {
            "ticker": ticker,
            "name": info.get("shortName") or info.get("longName") or ticker,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "hq_city": hq_city,
            "hq_state": hq_state,
            "hq_country": hq_country,
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "market_cap_b": round(market_cap_b, 2),
            "revenue_growth_pct": round(revenue_growth * 100, 1),
            "earnings_growth_pct": round(earnings_growth * 100, 1),
            "gross_margin_pct": round(gross_margin * 100, 1),
            "operating_margin_pct": round(operating_margin * 100, 1),
            "profit_margin_pct": round(profit_margin * 100, 1),
            "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
            "forward_pe": round(forward_pe, 1) if forward_pe else None,
            "ps_ratio": round(ps_ratio, 1) if ps_ratio else None,
            "peg_ratio": round(peg_ratio, 2) if peg_ratio else None,
            "distance_from_high_pct": round(distance_from_high, 1),
            "beta": round(beta, 2) if beta else None,
            "short_pct": round(short_pct * 100, 1) if short_pct else 0,
            "free_cash_flow": free_cash_flow,
        }

    except Exception:
        return None


# ─── Sector/Industry classification for scoring ───
# Secular growth sectors get a bonus; cyclical/commodity sectors get penalized.
# Key insight: gold miners can have 100% revenue growth driven purely by
# commodity price, but that's not the structural TAM expansion a 10x needs.

# Sector multipliers applied to the final composite score.
# 1.0 = neutral, >1 = boost, <1 = penalize.
SECTOR_MULTIPLIER: dict[str, float] = {
    # BOOST — structural growth, expanding TAMs
    "Technology": 1.15,
    "Communication Services": 1.05,
    "Healthcare": 1.05,

    # NEUTRAL — case-by-case
    "Consumer Cyclical": 1.0,
    "Consumer Defensive": 0.95,
    "Industrials": 1.0,
    "Financial Services": 0.95,

    # PENALIZE — cyclical/commodity-driven growth
    "Basic Materials": 0.70,   # gold, silver, mining, chemicals
    "Energy": 0.75,            # oil & gas, exploration
    "Utilities": 0.70,         # regulated, hard to 10x
    "Real Estate": 0.75,       # REITs, limited upside
}

# Industry-level overrides (more granular than sector).
# These override the sector multiplier when matched.
INDUSTRY_BOOST: dict[str, float] = {
    # Semiconductors & equipment — the 10x sweet spot
    "Semiconductors": 1.25,
    "Semiconductor Equipment & Materials": 1.25,
    # AI / cloud
    "Software - Infrastructure": 1.20,
    "Software - Application": 1.15,
    "Information Technology Services": 1.10,
    "Electronic Components": 1.15,
    "Scientific & Technical Instruments": 1.15,
    "Computer Hardware": 1.10,
    # Biotech / medtech
    "Biotechnology": 1.10,
    "Medical Devices": 1.10,
    "Drug Manufacturers - Specialty & Generic": 1.05,
    # Fintech
    "Software - Financial": 1.10,
    "Financial Data & Stock Exchanges": 1.05,
    # Clean energy (structural, not commodity)
    "Solar": 1.10,
    "Specialty Industrial Machinery": 1.05,
    # Penalize specific cyclical industries harder
    "Gold": 0.55,
    "Silver": 0.55,
    "Other Precious Metals & Mining": 0.55,
    "Copper": 0.60,
    "Steel": 0.65,
    "Aluminum": 0.65,
    "Coking Coal": 0.55,
    "Thermal Coal": 0.50,
    "Oil & Gas E&P": 0.65,
    "Oil & Gas Integrated": 0.70,
    "Oil & Gas Midstream": 0.70,
    "Uranium": 0.65,
    "Agricultural Inputs": 0.75,
    "Lumber & Wood Production": 0.70,
    "REIT - Diversified": 0.70,
    "REIT - Residential": 0.70,
    "Closed-End Fund - Equity": 0.50,   # not an operating company
    "Closed-End Fund - Debt": 0.40,
    "Asset Management": 0.80,
    "Shell Companies": 0.30,
    "Tobacco": 0.60,
}


def _get_sector_multiplier(sector: str, industry: str) -> float:
    """Return the sector/industry multiplier for scoring.
    Industry overrides sector when available."""
    if industry and industry in INDUSTRY_BOOST:
        return INDUSTRY_BOOST[industry]
    if sector and sector in SECTOR_MULTIPLIER:
        return SECTOR_MULTIPLIER[sector]
    return 1.0  # unknown → neutral


def _score_10x_potential(data: dict) -> dict:
    """Score a stock's 10x potential on 0-10 scale.

    Factors weighted for multi-bagger potential:
    - Revenue growth (30%): the main engine for 10x
    - Gross margin (15%): unit economics / moat signal
    - Operating leverage (15%): improving margins = explosive earnings
    - Market cap headroom (15%): smaller = more room to grow
    - Sector quality (10%): secular vs cyclical growth
    - Relative strength (8%): institutional momentum
    - Valuation reasonableness (7%): not absurdly expensive
    """
    # Revenue growth score (0-10): 15% = 3, 30% = 6, 50% = 8.5, 100%+ = 10
    rev_g = data["revenue_growth_pct"]
    rev_score = min(10, max(0, rev_g / 5))  # linear: 50% → 10

    # Gross margin score (0-10): 30% = 3, 50% = 6, 70% = 8, 90% = 10
    gm = data["gross_margin_pct"]
    gm_score = min(10, max(0, (gm - 20) / 7))  # 20% → 0, 90% → 10

    # Operating leverage score (0-10): improving op margin is key for 10x
    op_m = data["operating_margin_pct"]
    if op_m > 25:
        op_score = 9 + min(1, (op_m - 25) / 25)  # already excellent
    elif op_m > 0:
        op_score = 5 + op_m / 5  # positive and growing → good
    elif op_m > -15:
        # Negative but improving — still has potential if revenue is growing fast
        op_score = 3 + (op_m + 15) / 5 + (rev_g / 50)  # bonus for high growth
        op_score = max(2, min(7, op_score))
    else:
        op_score = max(0, 2 + op_m / 10)  # deeply negative

    # Market cap headroom (0-10): smaller cap = more room
    mcap = data["market_cap_b"]
    if mcap < 2:
        cap_score = 10   # micro-cap: huge upside
    elif mcap < 5:
        cap_score = 9    # small-cap: excellent
    elif mcap < 15:
        cap_score = 7.5  # mid-cap: solid
    elif mcap < 30:
        cap_score = 5.5  # upper-mid: harder to 10x
    elif mcap < 60:
        cap_score = 3.5  # large-cap: difficult
    else:
        cap_score = 2    # mega-cap: very hard to 10x

    # Sector quality score (0-10): secular growth vs cyclical/commodity
    sector = data.get("sector", "")
    industry = data.get("industry", "")
    sec_mult = _get_sector_multiplier(sector, industry)
    # Map multiplier to 0-10 score: 0.50 → 2, 0.75 → 5, 1.0 → 7, 1.25 → 10
    sector_score = min(10, max(0, (sec_mult - 0.40) * 11.76))  # 0.40→0, 1.25→10

    # Relative strength score (0-10): closer to 52w high = momentum
    dfh = data["distance_from_high_pct"]
    rs_score = min(10, max(0, 10 - dfh / 5))

    # Valuation score (0-10): not absurdly expensive given growth
    peg = data.get("peg_ratio") or 0
    fpe = data.get("forward_pe") or 0
    ps = data.get("ps_ratio") or 0

    if peg and 0 < peg < 5:
        val_score = min(10, max(0, 10 - peg * 2))  # PEG 0.5 → 9, PEG 2 → 6, PEG 5 → 0
    elif fpe and fpe > 0:
        val_score = min(10, max(0, 10 - fpe / 10))  # fPE 20 → 8, fPE 50 → 5
    elif ps and ps > 0:
        val_score = min(10, max(0, 10 - ps / 3))  # PS 3 → 9, PS 15 → 5, PS 30 → 0
    else:
        val_score = 5  # no data

    # Composite 10x score — sector-aware
    raw_composite = (
        rev_score * 0.30 +
        gm_score * 0.15 +
        op_score * 0.15 +
        cap_score * 0.15 +
        sector_score * 0.10 +
        rs_score * 0.08 +
        val_score * 0.07
    )

    # Apply sector multiplier as a final adjustment (compounds with the sector_score factor)
    # This ensures gold miners can't score 9+ just from revenue growth
    composite = round(max(0, min(10, raw_composite * sec_mult)), 1)

    return {
        "composite": composite,
        "revenue_growth": round(rev_score, 1),
        "gross_margin": round(gm_score, 1),
        "operating_leverage": round(op_score, 1),
        "market_cap_headroom": round(cap_score, 1),
        "sector_quality": round(sector_score, 1),
        "relative_strength": round(rs_score, 1),
        "valuation": round(val_score, 1),
        "sector_multiplier": round(sec_mult, 2),
    }


def _generate_signal_summary(data: dict, scores: dict) -> tuple[str, str]:
    """Generate signal direction and summary text."""
    composite = scores["composite"]
    if composite >= 7:
        signal = "bullish"
    elif composite >= 4.5:
        signal = "neutral"
    else:
        signal = "bearish"

    parts = []
    if data["revenue_growth_pct"] > 30:
        parts.append(f"Revenue growth {data['revenue_growth_pct']:.0f}% YoY")
    elif data["revenue_growth_pct"] > 0:
        parts.append(f"Revenue growth {data['revenue_growth_pct']:.0f}%")
    if data["gross_margin_pct"] > 60:
        parts.append(f"strong gross margin {data['gross_margin_pct']:.0f}%")
    if data["operating_margin_pct"] > 20:
        parts.append(f"op margin {data['operating_margin_pct']:.0f}%")
    elif data["operating_margin_pct"] < 0:
        parts.append(f"op margin {data['operating_margin_pct']:.0f}% (pre-profit)")
    if data["market_cap_b"] < 5:
        parts.append(f"small cap ${data['market_cap_b']:.1f}B")
    elif data["market_cap_b"] < 15:
        parts.append(f"mid cap ${data['market_cap_b']:.1f}B")

    summary = ". ".join(parts[:4]) + "." if parts else "Growth stock with 10x potential."
    return signal, summary


def stage2_quant_filter(universe: list[str]) -> list[dict]:
    """Stage 2: Scan universe with yfinance, score on 10x potential, filter."""
    print("\n" + "─" * 50)
    print("  STAGE 2: QUANT FILTER — Scoring 10x potential")
    print("─" * 50)
    print(f"  Scanning {len(universe)} tickers (hard filters: mktcap ${MIN_MARKET_CAP_B}-{MAX_MARKET_CAP_B}B, rev growth >{MIN_REVENUE_GROWTH*100:.0f}%, GM >{MIN_GROSS_MARGIN*100:.0f}%)")

    candidates = []
    scanned = 0
    passed_filters = 0

    # Parallel scan with thread pool (yfinance is I/O bound)
    batch_size = 5  # small batches to avoid rate limits
    for i in range(0, len(universe), batch_size):
        batch = universe[i:i + batch_size]

        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {executor.submit(_fetch_stock_data, t): t for t in batch}
            for future in as_completed(futures):
                ticker = futures[future]
                scanned += 1
                try:
                    data = future.result()
                    if data:
                        passed_filters += 1
                        scores = _score_10x_potential(data)
                        signal, summary = _generate_signal_summary(data, scores)

                        candidates.append({
                            "ticker": data["ticker"],
                            "data": data,
                            "scores": scores,
                            "signal": signal,
                            "summary": summary,
                        })
                except Exception:
                    pass

        # Progress
        pct = round(scanned / len(universe) * 100)
        _write_progress("scanning", f"Scanned {scanned}/{len(universe)} ({passed_filters} passed filters)", scanned, len(universe))
        if scanned % 50 == 0:
            print(f"  Progress: {scanned}/{len(universe)} scanned, {passed_filters} passed filters ({pct}%)")

        time.sleep(0.2)  # rate limit buffer

    # Sort by 10x score and filter
    candidates.sort(key=lambda x: x["scores"]["composite"], reverse=True)
    quality_candidates = [c for c in candidates if c["scores"]["composite"] >= CANDIDATE_SCORE_THRESHOLD]

    print(f"\n  Stage 2 result: {passed_filters} passed hard filters, {len(quality_candidates)} scored above {CANDIDATE_SCORE_THRESHOLD}")

    # Tag top candidates
    for i, c in enumerate(quality_candidates):
        c["_rank"] = i + 1
        c["_stage"] = "shortlist" if c["scores"]["composite"] >= AI_SCORE_THRESHOLD else "candidate"

    return quality_candidates


# ═══════════════════════════════════════════════════════════════
# STAGE 3: AI VALIDATION — Deep research on top candidates
# ═══════════════════════════════════════════════════════════════

def _perplexity_research(ticker: str, name: str, sector: str) -> str:
    """Use Perplexity to research a stock's 10x potential."""
    if not PERPLEXITY_KEY:
        return ""

    prompt = f"""Research {ticker} ({name}) in the {sector} sector for 10x investment potential.
Focus on:
1. Total addressable market (TAM) size and growth rate
2. Competitive moat and differentiation
3. Revenue growth trajectory and acceleration/deceleration
4. Key upcoming catalysts (product launches, contracts, regulatory)
5. Major risks and potential thesis killers

Be specific with numbers and recent data. Keep response under 400 words."""

    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {PERPLEXITY_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600,
                "temperature": 0.1,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        print(f"  [{ticker}] Perplexity research failed: {e}")
        return ""


def _claude_synthesize(ticker: str, name: str, sector: str,
                       quant_data: dict, research: str) -> dict | None:
    """Use Claude to generate thesis, kill condition, and criteria."""
    if not ANTHROPIC_KEY:
        return None

    prompt = f"""You are a 10x stock analyst evaluating {ticker} ({name}) in {sector}.

QUANT DATA:
- Price: ${quant_data.get('price', '?')}
- Market cap: ${quant_data.get('market_cap_b', '?'):.1f}B
- Revenue growth: {quant_data.get('revenue_growth_pct', '?')}% YoY
- Gross margin: {quant_data.get('gross_margin_pct', '?')}%
- Operating margin: {quant_data.get('operating_margin_pct', '?')}%
- Forward PE: {quant_data.get('forward_pe', 'N/A')}
- P/S: {quant_data.get('ps_ratio', 'N/A')}

RESEARCH:
{research or 'No additional research available.'}

TASK: Evaluate this stock's 10x potential and provide:

1. **thesis**: 2-3 sentence investment thesis for why this could 10x
2. **kill_condition**: A specific, falsifiable condition that would break this thesis. MUST include: (a) a named counterparty, contract, product line, or regulatory body specific to THIS company, (b) a concrete numeric threshold or binary event, and (c) a timeframe. Examples: "LITE loses its next major defense contract renewal (>$50M)" or "Management dilutes more than 15% at next raise within 12 months". NEVER use generic conditions like "revenue growth falls below X%" — those are not thesis-breaking, they are sector-wide noise.
3. **catalysts**: List of 3-5 upcoming catalysts that could drive the stock higher
4. **target_price_range**: Rough 3-year price range {{low, base, high}} for 10x potential
5. **confidence**: 0.0-1.0 how confident you are this is a real 10x candidate
6. **sector_for_watchlist**: Best sector label for this stock
7. **tags**: 3-5 relevant tags (e.g. ["AI", "semiconductors", "high-growth"])

Respond with ONLY valid JSON (no markdown fences):
{{
  "thesis": "...",
  "kill_condition": "...",
  "catalysts": ["...", "..."],
  "target_price_range": {{"low": 0, "base": 0, "high": 0}},
  "confidence": 0.0,
  "sector_for_watchlist": "...",
  "tags": ["...", "..."]
}}"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-6",
                "max_tokens": 800,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [{}])[0].get("text", "")

        # Clean markdown fences if present
        clean = re.sub(r'^```(?:json)?\s*', '', content.strip())
        clean = re.sub(r'\s*```$', '', clean)
        return json.loads(clean)

    except Exception as e:
        print(f"  [{ticker}] Claude synthesis failed: {e}")
        return None


def stage3_ai_validate(candidates: list[dict], top_n: int = DEFAULT_AI_TOP_N) -> list[dict]:
    """Stage 3: Deep AI validation of top candidates."""
    print("\n" + "─" * 50)
    print(f"  STAGE 3: AI VALIDATION — Top {top_n} candidates")
    print("─" * 50)

    if not PERPLEXITY_KEY and not ANTHROPIC_KEY:
        print("  [!] No API keys set — skipping AI validation")
        print("  Set PERPLEXITY_API_KEY and/or ANTHROPIC_API_KEY in .env")
        return candidates

    top = candidates[:top_n]
    validated = []

    for i, c in enumerate(top):
        ticker = c["ticker"]
        data = c["data"]
        name = data.get("name", ticker)
        sector = data.get("sector", "")

        print(f"\n  [{i+1}/{len(top)}] Researching {ticker} ({name})...")
        _write_progress(
            "ai_validation",
            f"AI validating {ticker} ({i+1}/{len(top)})",
            i + 1,
            len(top),
        )

        # Step 1: Perplexity research (if available)
        research = ""
        if PERPLEXITY_KEY:
            research = _perplexity_research(ticker, name, sector)
            if research:
                print(f"    Research: {len(research)} chars")
            time.sleep(1)  # rate limit

        # Step 2: Claude synthesis (if available)
        ai_data = None
        if ANTHROPIC_KEY:
            ai_data = _claude_synthesize(ticker, name, sector, data, research)
            if ai_data:
                conf = ai_data.get("confidence", 0)
                print(f"    Confidence: {conf:.0%} | Thesis: {ai_data.get('thesis', '')[:80]}...")
            time.sleep(1)

        # Enrich candidate with AI data
        c["research"] = research[:2000] if research else ""
        c["ai_validation"] = ai_data
        c["_stage"] = "validated"

        if ai_data:
            c["ai_confidence"] = ai_data.get("confidence", 0)
            c["thesis"] = ai_data.get("thesis", "")
            c["kill_condition"] = ai_data.get("kill_condition", "")
            c["catalysts"] = ai_data.get("catalysts", [])
            c["target_range"] = ai_data.get("target_price_range", {})
            c["tags"] = ai_data.get("tags", [])
            c["sector_label"] = ai_data.get("sector_for_watchlist", sector)

        validated.append(c)

    # Sort validated by AI confidence (if available), then score
    validated.sort(key=lambda x: (x.get("ai_confidence", 0), x["scores"]["composite"]), reverse=True)

    print(f"\n  Stage 3 result: {len(validated)} stocks validated")
    return validated


# ═══════════════════════════════════════════════════════════════
# SAVE + MAIN
# ═══════════════════════════════════════════════════════════════

def _write_progress(stage: str, message: str, current: int, total: int):
    """Write discovery scan progress for dashboard polling."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    progress = {
        "stage": stage,
        "message": message,
        "current": current,
        "total": total,
        "percent": round((current / total) * 100) if total > 0 else 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        PROGRESS_FILE.write_text(json.dumps(progress), encoding="utf-8")
    except Exception:
        pass


def _clear_progress():
    try:
        PROGRESS_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def save_to_supabase(candidates: list[dict], run_id: str) -> bool:
    """Save discovery candidates to Supabase."""
    try:
        from supabase_helper import get_client
        sb = get_client()

        rows = []
        for c in candidates:
            data = c.get("data", {})
            scores = c.get("scores", {})
            rows.append({
                "ticker": c["ticker"],
                "name": data.get("name", ""),
                "sector": data.get("sector", ""),
                "price": data.get("price", 0),
                "change_pct": data.get("change_pct", 0),
                "market_cap_b": data.get("market_cap_b", 0),
                "revenue_growth_pct": data.get("revenue_growth_pct", 0),
                "earnings_growth_pct": data.get("earnings_growth_pct", 0),
                "gross_margin_pct": data.get("gross_margin_pct", 0),
                "operating_margin_pct": data.get("operating_margin_pct", 0),
                "forward_pe": data.get("forward_pe"),
                "ps_ratio": data.get("ps_ratio"),
                "peg_ratio": data.get("peg_ratio"),
                "distance_from_high_pct": data.get("distance_from_high_pct", 0),
                "beta": data.get("beta"),
                "short_pct": data.get("short_pct", 0),
                "quant_score": scores.get("composite", 0),
                "scores": scores,
                "signal": c.get("signal", "neutral"),
                "summary": c.get("summary", ""),
                "stage": c.get("_stage", "candidate"),
                "rank": c.get("_rank"),
                "run_id": run_id,
                # AI-enriched fields (nullable — stripped if columns don't exist)
                "ai_confidence": c.get("ai_confidence"),
                "thesis": c.get("thesis"),
                "kill_condition": c.get("kill_condition"),
                "catalysts": c.get("catalysts", []),
                "target_range": c.get("target_range", {}),
                "tags": c.get("tags", []),
                "research": (c.get("research") or "")[:2000],
                "industry": data.get("industry", ""),
                "hq_city": data.get("hq_city", ""),
                "hq_state": data.get("hq_state", ""),
                "hq_country": data.get("hq_country", ""),
            })

        # Batch insert
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            sb.table("discovery_candidates").insert(batch).execute()

        print(f"  [DB] Saved {len(rows)} candidates to Supabase (run: {run_id})")
        return True
    except Exception as e:
        print(f"  [DB] Supabase save failed: {e}")
        return False


def save_to_json(candidates: list[dict], run_id: str):
    """Fallback: save to local JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "run_id": run_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_candidates": len(candidates),
        "candidates": candidates,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"  [FILE] Saved {len(candidates)} candidates to {OUTPUT_FILE}")


def main():
    quick_mode = "--quick" in sys.argv
    stage1_only = "--stage1-only" in sys.argv

    # Parse --ai-top N
    ai_top_n = DEFAULT_AI_TOP_N
    if "--ai-top" in sys.argv:
        idx = sys.argv.index("--ai-top")
        if idx + 1 < len(sys.argv):
            try:
                ai_top_n = int(sys.argv[idx + 1])
            except ValueError:
                pass

    print("=" * 60)
    print("  STOCK RADAR — UNIVERSE EXPANSION SCANNER")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(f"  Mode: {'Stage 1 only' if stage1_only else 'Quick (no AI)' if quick_mode else f'Full 3-stage (AI top {ai_top_n})'}")
    print("=" * 60)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_disc_" + uuid.uuid4().hex[:4]
    start = time.time()

    # Get watchlist tickers to exclude
    try:
        watchlist_tickers = {s["ticker"] for s in get_watchlist()}
    except Exception:
        watchlist_tickers = set()

    # ── Stage 1: Collect universe ──
    _write_progress("stage1", "Collecting tickers from screeners...", 0, 1)
    universe = stage1_collect_universe(watchlist_tickers)

    if stage1_only:
        print(f"\n  Stage 1 complete: {len(universe)} tickers collected")
        _clear_progress()
        return universe

    if not universe:
        print("\n  No tickers to scan!")
        _clear_progress()
        return []

    # ── Stage 2: Quant filter ──
    candidates = stage2_quant_filter(universe)

    if not candidates:
        print("\n  No candidates passed filters!")
        _clear_progress()
        return []

    # Print Stage 2 leaderboard
    print(f"\n  TOP 20 CANDIDATES (10x Score):")
    print(f"  {'#':<4} {'Ticker':<7} {'Score':<6} {'RevG%':<7} {'GM%':<6} {'MktCap':<8} {'Signal':<8}")
    print(f"  {'─'*4} {'─'*7} {'─'*6} {'─'*7} {'─'*6} {'─'*8} {'─'*8}")
    for c in candidates[:20]:
        d = c["data"]
        s = c["scores"]
        mcap = f"${d['market_cap_b']:.1f}B"
        print(f"  {c['_rank']:<4} {c['ticker']:<7} {s['composite']:<6.1f} {d['revenue_growth_pct']:<7.0f} {d['gross_margin_pct']:<6.0f} {mcap:<8} {c['signal']:<8}")

    # ── Stage 3: AI validation (unless quick mode) ──
    if not quick_mode and (PERPLEXITY_KEY or ANTHROPIC_KEY):
        ai_candidates = [c for c in candidates if c["scores"]["composite"] >= AI_SCORE_THRESHOLD]
        actual_top_n = min(ai_top_n, len(ai_candidates))
        if actual_top_n > 0:
            validated = stage3_ai_validate(ai_candidates, actual_top_n)
            # Replace the AI-validated entries in the main list
            validated_tickers = {v["ticker"] for v in validated}
            candidates = [c for c in candidates if c["ticker"] not in validated_tickers]
            candidates = validated + candidates
            # Re-sort
            candidates.sort(key=lambda x: (
                x.get("ai_confidence", 0) * 10 + x["scores"]["composite"]
            ), reverse=True)
            # Re-rank
            for i, c in enumerate(candidates):
                c["_rank"] = i + 1
    elif not quick_mode:
        print("\n  [!] Skipping AI validation — no API keys set")

    # ── Save results ──
    _write_progress("saving", "Saving results...", 1, 1)

    if not save_to_supabase(candidates, run_id):
        save_to_json(candidates, run_id)
    save_to_json(candidates, run_id)  # always save JSON backup

    elapsed = time.time() - start
    shortlist_count = sum(1 for c in candidates if c.get("_stage") in ("shortlist", "validated"))
    validated_count = sum(1 for c in candidates if c.get("_stage") == "validated")

    _write_progress("complete",
        f"Done — {len(candidates)} candidates, {shortlist_count} shortlisted, {validated_count} AI-validated",
        1, 1)

    print(f"\n{'='*60}")
    print(f"  DISCOVERY COMPLETE")
    print(f"  Scanned: {len(universe)} | Candidates: {len(candidates)} | Shortlist: {shortlist_count} | AI-validated: {validated_count}")
    print(f"  Time: {elapsed:.0f}s | Run: {run_id}")
    print(f"{'='*60}")

    time.sleep(2)
    _clear_progress()

    return candidates


if __name__ == "__main__":
    main()
