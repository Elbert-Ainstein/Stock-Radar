#!/usr/bin/env python3
"""
Scout 4: Quant Screener
Uses Yahoo Finance (free) as primary source, Alpha Vantage as fallback.
Runs against the watchlist + optionally screens for new candidates.

Usage:
    python scripts/scout_quant.py              # scan watchlist only
    python scripts/scout_quant.py --screen     # also screen for new candidates
"""
import sys
import os
import json
import time as _time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf
import pandas as pd
from utils import get_watchlist, get_screen_filters, save_signals, timestamp, load_env

# Load .env using absolute-path helper (works regardless of CWD)
load_env()

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]  # seconds between retries
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")


def _fetch_info_with_retry(ticker: str) -> dict | None:
    """Fetch yfinance info with retry on transient errors (HTTP 500, timeout, etc.)."""
    for attempt in range(MAX_RETRIES):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if info and "marketCap" in info:
                return info
            if attempt < MAX_RETRIES - 1:
                print(f"  [{ticker}] No data on attempt {attempt + 1}, retrying in {RETRY_DELAYS[attempt]}s...")
                _time.sleep(RETRY_DELAYS[attempt])
            else:
                print(f"  [{ticker}] No data after {MAX_RETRIES} attempts, skipping")
                return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  [{ticker}] Error on attempt {attempt + 1}: {e} — retrying in {RETRY_DELAYS[attempt]}s...")
                _time.sleep(RETRY_DELAYS[attempt])
            else:
                print(f"  [{ticker}] Failed after {MAX_RETRIES} attempts: {e}")
                return None
    return None


def _fetch_alpha_vantage(ticker: str) -> dict | None:
    """Fallback: fetch key data from Alpha Vantage when yfinance fails.
    Maps Alpha Vantage fields to the same shape as yfinance info dict."""
    if not ALPHA_VANTAGE_KEY:
        return None

    print(f"  [{ticker}] Trying Alpha Vantage fallback...")
    try:
        # Global Quote — price data
        quote_url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={ALPHA_VANTAGE_KEY}"
        quote_resp = requests.get(quote_url, timeout=15)
        quote_data = quote_resp.json()
        gq = quote_data.get("Global Quote", {})
        if not gq:
            print(f"  [{ticker}] Alpha Vantage: no quote data")
            return None

        price = float(gq.get("05. price", 0))
        prev_close = float(gq.get("08. previous close", 0))
        if price <= 0:
            print(f"  [{ticker}] Alpha Vantage: invalid price")
            return None

        # Company Overview — fundamentals
        _time.sleep(0.5)  # respect rate limit
        overview_url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={ALPHA_VANTAGE_KEY}"
        overview_resp = requests.get(overview_url, timeout=15)
        ov = overview_resp.json()

        def safe_float(val, default=0):
            try:
                v = float(val)
                return v if v == v else default  # NaN check
            except (TypeError, ValueError):
                return default

        # Map to yfinance-compatible dict
        info = {
            "currentPrice": price,
            "previousClose": prev_close,
            "marketCap": safe_float(ov.get("MarketCapitalization", 0)),
            "revenueGrowth": safe_float(ov.get("QuarterlyRevenueGrowthYOY", 0)),
            "earningsGrowth": safe_float(ov.get("QuarterlyEarningsGrowthYOY", 0)),
            "grossMargins": safe_float(ov.get("GrossProfitTTM", 0)) / max(safe_float(ov.get("RevenueTTM", 1)), 1),
            "operatingMargins": safe_float(ov.get("OperatingMarginTTM", 0)),
            "profitMargins": safe_float(ov.get("ProfitMargin", 0)),
            "trailingPE": safe_float(ov.get("TrailingPE", 0)),
            "forwardPE": safe_float(ov.get("ForwardPE", 0)),
            "priceToSalesTrailing12Months": safe_float(ov.get("PriceToSalesRatioTTM", 0)),
            "pegRatio": safe_float(ov.get("PEGRatio", 0)),
            "averageVolume": safe_float(ov.get("AverageVolume", 0)),
            "fiftyTwoWeekHigh": safe_float(ov.get("52WeekHigh", 0)),
            "fiftyTwoWeekLow": safe_float(ov.get("52WeekLow", 0)),
            "beta": safe_float(ov.get("Beta", 0)),
            "shortPercentOfFloat": safe_float(ov.get("ShortPercentFloat", 0)),
            "heldPercentInsiders": safe_float(ov.get("PercentInsiders", 0)) / 100 if safe_float(ov.get("PercentInsiders", 0)) > 0 else 0,
            "heldPercentInstitutions": safe_float(ov.get("PercentInstitutions", 0)) / 100 if safe_float(ov.get("PercentInstitutions", 0)) > 0 else 0,
            "freeCashflow": 0,  # not directly available in overview
            "_source": "alpha_vantage",
        }
        print(f"  [{ticker}] Alpha Vantage: got price ${price:.2f}, mktcap ${info['marketCap']/1e9:.1f}B")
        return info

    except Exception as e:
        print(f"  [{ticker}] Alpha Vantage fallback failed: {e}")
        return None


def analyze_stock(ticker: str) -> dict | None:
    """Pull fundamental + price data for a single ticker."""
    try:
        info = _fetch_info_with_retry(ticker)
        # If yfinance failed, try Alpha Vantage
        if not info:
            info = _fetch_alpha_vantage(ticker)
        if not info:
            return None

        # Price data
        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        prev_close = info.get("previousClose", price)
        change = price - prev_close if price and prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        # Market cap
        market_cap = info.get("marketCap", 0)
        market_cap_b = market_cap / 1e9

        # Growth metrics
        revenue_growth = info.get("revenueGrowth", 0) or 0  # decimal, e.g. 0.28 = 28%
        earnings_growth = info.get("earningsGrowth", 0) or 0

        # Profitability
        gross_margin = info.get("grossMargins", 0) or 0
        operating_margin = info.get("operatingMargins", 0) or 0
        profit_margin = info.get("profitMargins", 0) or 0

        # Valuation
        pe_ratio = info.get("trailingPE", 0) or 0
        forward_pe = info.get("forwardPE", 0) or 0
        ps_ratio = info.get("priceToSalesTrailing12Months", 0) or 0
        peg_ratio = info.get("pegRatio", 0) or 0

        # Revenue (TTM) — direct from yfinance, not derived from market cap / P/S
        total_revenue = info.get("totalRevenue", 0) or 0  # TTM revenue in dollars
        shares_outstanding = info.get("sharesOutstanding", 0) or 0

        # Other
        avg_volume = info.get("averageVolume", 0) or 0
        fifty_two_high = info.get("fiftyTwoWeekHigh", 0) or 0
        fifty_two_low = info.get("fiftyTwoWeekLow", 0) or 0
        beta = info.get("beta", 0) or 0
        short_pct = info.get("shortPercentOfFloat", 0) or 0
        insider_pct = info.get("heldPercentInsiders", 0) or 0
        inst_pct = info.get("heldPercentInstitutions", 0) or 0
        free_cash_flow = info.get("freeCashflow", 0) or 0

        # Relative strength: how far from 52-week high
        distance_from_high = ((fifty_two_high - price) / fifty_two_high * 100) if fifty_two_high else 0

        # ─── Scoring ───
        # Revenue growth score (0-10)
        rev_score = min(10, max(0, revenue_growth * 100 / 5))  # 50%+ growth = 10

        # Margin score (0-10)
        margin_score = min(10, max(0, gross_margin * 10 + operating_margin * 5))

        # Valuation score (0-10) — lower PEG is better.
        # Loss-making companies are capped at neutral: a tiny positive
        # forward_pe on a money-losing company shouldn't produce a "cheap!"
        # signal. yfinance returns None for trailing PE when EPS ≤ 0, so
        # we detect loss-making via operating margin + trailing PE.
        currently_losing = (
            (pe_ratio is not None and pe_ratio < 0)
            or (operating_margin is not None and operating_margin < -0.05)  # <-5% op margin
            or (profit_margin is not None and profit_margin < -0.05)
        )
        if peg_ratio and peg_ratio > 0 and not currently_losing:
            val_score = min(10, max(0, 10 - peg_ratio * 3))
        elif forward_pe and forward_pe > 0 and not currently_losing:
            val_score = min(10, max(0, 10 - forward_pe / 10))
        elif forward_pe and forward_pe > 0 and currently_losing:
            # Positive forward PE but negative trailing → company projected
            # to turn profitable. Cap at neutral-leaning (max 6).
            val_score = min(6, max(0, 8 - forward_pe / 10))
        elif ps_ratio and ps_ratio > 0:
            # No earnings to price — fall back to P/S (growth/speculative stocks)
            # Generous for high-growth: P/S of 5 → 7.5, P/S of 20 → 0
            val_score = min(10, max(0, 10 - ps_ratio / 2))
        else:
            val_score = 5  # no data, neutral

        # Relative strength score (0-10) — closer to 52w high is better
        rs_score = min(10, max(0, 10 - distance_from_high / 5))

        # Composite quant score
        quant_score = round(
            rev_score * 0.35 +
            margin_score * 0.25 +
            val_score * 0.20 +
            rs_score * 0.20
        , 1)

        # Determine signal
        if quant_score >= 7:
            signal = "bullish"
        elif quant_score >= 4:
            signal = "neutral"
        else:
            signal = "bearish"

        # Summary
        parts = []
        if revenue_growth:
            parts.append(f"Revenue growth {revenue_growth*100:.0f}% YoY")
        if gross_margin:
            parts.append(f"gross margin {gross_margin*100:.0f}%")
        if forward_pe:
            parts.append(f"fwd PE {forward_pe:.1f}")
        if distance_from_high < 10:
            parts.append(f"near 52w high ({distance_from_high:.0f}% off)")
        elif distance_from_high > 30:
            parts.append(f"{distance_from_high:.0f}% off 52w high")
        summary = ". ".join(parts) + "." if parts else "Limited data available."

        return {
            "ticker": ticker,
            "scout": "Quant",
            "ai": "Claude",
            "signal": signal,
            "summary": summary,
            "timestamp": timestamp(),
            "data": {
                "price": round(price, 2) if price else 0,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "market_cap_b": round(market_cap_b, 2),
                "revenue_growth_pct": round(revenue_growth * 100, 1) if revenue_growth else 0,
                "earnings_growth_pct": round(earnings_growth * 100, 1) if earnings_growth else 0,
                "gross_margin_pct": round(gross_margin * 100, 1) if gross_margin else 0,
                "operating_margin_pct": round(operating_margin * 100, 1) if operating_margin else 0,
                "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
                "forward_pe": round(forward_pe, 1) if forward_pe else None,
                "ps_ratio": round(ps_ratio, 1) if ps_ratio else None,
                "peg_ratio": round(peg_ratio, 2) if peg_ratio else None,
                "avg_volume": avg_volume,
                "fifty_two_high": round(fifty_two_high, 2),
                "fifty_two_low": round(fifty_two_low, 2),
                "distance_from_high_pct": round(distance_from_high, 1),
                "beta": round(beta, 2) if beta else None,
                "short_pct": round(short_pct * 100, 1) if short_pct else 0,
                "insider_pct": round(insider_pct * 100, 1) if insider_pct else 0,
                "institutional_pct": round(inst_pct * 100, 1) if inst_pct else 0,
                "free_cash_flow": free_cash_flow,
                "ttm_revenue": round(total_revenue / 1e9, 3) if total_revenue else 0,
                "shares_outstanding_m": round(shares_outstanding / 1e6) if shares_outstanding else 0,
            },
            "scores": {
                "revenue_growth": round(rev_score, 1),
                "margins": round(margin_score, 1),
                "valuation": round(val_score, 1),
                "relative_strength": round(rs_score, 1),
                "composite": quant_score,
            },
        }
    except Exception as e:
        print(f"  [{ticker}] Error: {e}")
        return None


def main():
    print("=" * 50)
    print("SCOUT 4: QUANT SCREENER")
    print("=" * 50)

    watchlist = get_watchlist()

    # Skip stocks with recent signals — cadence from registries.SCOUT_CADENCE_HOURS
    from utils import get_fresh_tickers
    fresh = get_fresh_tickers("quant")
    watchlist = [s for s in watchlist if s["ticker"] not in fresh]
    tickers = [s["ticker"] for s in watchlist]
    if fresh:
        from registries import SCOUT_CADENCE_HOURS
        hrs = SCOUT_CADENCE_HOURS.get("quant", 12)
        print(f"  Skipping {len(fresh)} stocks with recent signals (<{hrs}h old)")

    print(f"\nScanning {len(tickers)} watchlist stocks: {', '.join(tickers)}")
    print("-" * 50)

    if not tickers:
        print("  All stocks have recent quant data — nothing to do")
        return

    signals = []

    # Parallel stock analysis — yfinance calls are I/O bound (HTTP),
    # so 6 workers cuts wall-clock time dramatically for 50 stocks.
    def _analyze(t):
        result = analyze_stock(t)
        if result:
            score = result["scores"]["composite"]
            sig = result["signal"]
            print(f"  [{t}] Score: {score}/10 | Signal: {sig}")
        return result

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_analyze, t): t for t in tickers}
        for future in as_completed(futures):
            result = future.result()
            if result:
                signals.append(result)

    # Sort by composite score descending
    signals.sort(key=lambda x: x["scores"]["composite"], reverse=True)

    save_signals("quant", signals)

    # Print summary
    print("\n" + "=" * 50)
    print("QUANT SCREENER SUMMARY")
    print("=" * 50)
    for s in signals:
        emoji = "🟢" if s["signal"] == "bullish" else ("🔴" if s["signal"] == "bearish" else "🟡")
        print(f"  {emoji} {s['ticker']:6s} Score: {s['scores']['composite']:4.1f}  |  {s['summary'][:70]}")

    return signals


if __name__ == "__main__":
    main()
