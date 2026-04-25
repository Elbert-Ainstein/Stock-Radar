#!/usr/bin/env python3
"""
Scout 6: Insider & Institutional Tracker
Pulls Form 4 insider transactions from SEC EDGAR (free, public).

Usage:
    python scripts/scout_insider.py
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from utils import get_watchlist, save_signals, timestamp

# SEC EDGAR requires a User-Agent header identifying you
SEC_HEADERS = {
    "User-Agent": "StockRadar/1.0 (stock-radar-agent@example.com)",
    "Accept": "application/json",
}

# CIK lookup cache
CIK_CACHE = {}


def get_cik(ticker: str) -> str | None:
    """Look up SEC CIK number for a ticker."""
    if ticker in CIK_CACHE:
        return CIK_CACHE[ticker]

    try:
        url = "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom&startdt=2024-01-01&forms=4".format(ticker)
        # Use the company tickers JSON endpoint instead
        url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=&CIK={}&type=4&dateb=&owner=include&count=10&search_text=&action=getcompany&output=atom".format(ticker)

        # Better approach: use the full company tickers file
        tickers_url = "https://www.sec.gov/files/company_tickers.json"
        resp = requests.get(tickers_url, headers=SEC_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                CIK_CACHE[ticker] = cik
                return cik
        return None
    except Exception as e:
        print(f"  [{ticker}] CIK lookup error: {e}")
        return None


def get_insider_transactions(cik: str, ticker: str) -> list[dict]:
    """Pull recent insider transactions from EDGAR."""
    try:
        # Get recent filings for this CIK
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        company_name = data.get("name", ticker)
        recent = data.get("filings", {}).get("recent", {})

        if not recent:
            return []

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        descriptions = recent.get("primaryDocDescription", [])
        accession_numbers = recent.get("accessionNumber", [])

        transactions = []
        for i, form in enumerate(forms):
            if form in ("4", "4/A") and i < 20:  # Only Form 4s, last 20 filings
                filing_date = dates[i] if i < len(dates) else ""
                desc = descriptions[i] if i < len(descriptions) else ""

                transactions.append({
                    "form": form,
                    "filing_date": filing_date,
                    "description": desc or "Insider transaction",
                    "accession": accession_numbers[i] if i < len(accession_numbers) else "",
                })

        return transactions

    except Exception as e:
        print(f"  [{ticker}] EDGAR error: {e}")
        return []


def _classify_transaction(description: str) -> str:
    """Classify a Form 4 description into 'buy' / 'sell' / 'unknown'.

    Form 4 descriptions vary but common keywords:
      - Buys:  "purchase", "acquisition", "bought", "acquired"
      - Sells: "sale", "sold", "disposition", "10b5-1"  (10b5-1 plans are
               almost always pre-scheduled SELL programs in practice)
      - Grants / options: neutral — often compensation, not open-market buys
    """
    if not description:
        return "unknown"
    d = description.lower()
    # Order matters: "acquired pursuant to plan" is usually RSU grants, not buys
    if any(w in d for w in ["sale", "sold", "disposition", "disposed", "10b5-1", "sell"]):
        return "sell"
    if any(w in d for w in ["grant", "award", "rsu", "option exercise", "exercised", "stock award"]):
        return "neutral"
    if any(w in d for w in ["purchase", "bought", "open market", "acquired"]):
        return "buy"
    return "unknown"


def analyze_insider_activity(ticker: str, transactions: list[dict]) -> dict:
    """Analyze insider transactions and generate a signal.

    Key fix: direction-aware classification. Previously, 5+ transactions
    (regardless of buy/sell) defaulted to "bullish", which mis-scored any
    stock with routine executive selling as a positive signal.
    """
    if not transactions:
        return {
            "ticker": ticker,
            "scout": "Insider",
            "ai": "Script",
            "signal": "neutral",
            "summary": "No recent Form 4 filings found in EDGAR.",
            "timestamp": timestamp(),
            "data": {"transactions": [], "transaction_count": 0, "buys": 0, "sells": 0},
        }

    # Last 10 most recent filings
    recent = transactions[:10]
    count = len(recent)

    # Classify each
    buys = 0
    sells = 0
    for t in recent:
        kind = _classify_transaction(t.get("description", ""))
        t["kind"] = kind
        if kind == "buy":
            buys += 1
        elif kind == "sell":
            sells += 1

    net = buys - sells

    # Signal logic based on direction, not just count
    if buys >= 2 and sells == 0:
        signal = "bullish"
        summary = f"{buys} insider buy(s), 0 sells — insiders adding to positions."
    elif net >= 2:
        signal = "bullish"
        summary = f"{buys} buys vs {sells} sells — net insider buying."
    elif sells >= 3 and buys == 0:
        signal = "bearish"
        summary = f"{sells} insider sell(s), 0 buys — insiders trimming positions."
    elif net <= -3:
        signal = "bearish"
        summary = f"{buys} buys vs {sells} sells — net insider selling."
    elif count >= 2:
        signal = "neutral"
        summary = (
            f"{count} insider transactions ({buys} buys, {sells} sells, "
            f"{count - buys - sells} grants/other) — mixed activity."
        )
    elif count == 1:
        signal = "neutral"
        summary = f"1 insider transaction found: {recent[0]['description']} on {recent[0]['filing_date']}."
    else:
        signal = "neutral"
        summary = "No recent insider transactions."

    return {
        "ticker": ticker,
        "scout": "Insider",
        "ai": "Script",
        "signal": signal,
        "summary": summary,
        "timestamp": timestamp(),
        "data": {
            "transactions": recent[:5],  # Keep top 5 for display
            "transaction_count": count,
            "buys": buys,
            "sells": sells,
        },
    }


def main():
    print("=" * 50)
    print("SCOUT 6: INSIDER TRACKER")
    print("=" * 50)

    watchlist = get_watchlist()

    # Skip stocks with recent signals
    from utils import get_fresh_tickers
    fresh = get_fresh_tickers("insider")
    watchlist = [s for s in watchlist if s["ticker"] not in fresh]
    tickers = [s["ticker"] for s in watchlist]
    if fresh:
        from registries import SCOUT_CADENCE_HOURS
        hrs = SCOUT_CADENCE_HOURS.get("insider", 20)
        print(f"  Skipping {len(fresh)} stocks with recent signals (<{hrs}h old)")

    print(f"\nScanning {len(tickers)} stocks for insider activity: {', '.join(tickers)}")
    print("-" * 50)

    if not tickers:
        print("  All stocks have recent insider data — nothing to do")
        return

    def _process_ticker(ticker):
        """Process a single ticker for insider activity (called in parallel)."""
        cik = get_cik(ticker)
        if not cik:
            print(f"  [{ticker}] Could not find CIK, skipping")
            return {
                "ticker": ticker,
                "scout": "Insider",
                "ai": "Script",
                "signal": "neutral",
                "summary": "Could not find SEC CIK for this ticker.",
                "timestamp": timestamp(),
                "data": {"transactions": [], "transaction_count": 0},
            }

        print(f"  [{ticker}] CIK: {cik}")
        time.sleep(0.15)  # Be nice to SEC servers

        transactions = get_insider_transactions(cik, ticker)
        print(f"  [{ticker}] Found {len(transactions)} Form 4 filings")

        result = analyze_insider_activity(ticker, transactions)
        print(f"  [{ticker}] Signal: {result['signal']} — {result['summary'][:70]}")
        return result

    # Parallel processing — SEC EDGAR is I/O bound.
    # 4 workers keeps us polite to SEC servers while still speeding things up.
    signals = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_process_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            try:
                result = future.result()
                signals.append(result)
            except Exception as e:
                ticker = futures[future]
                print(f"  [{ticker}] Error: {e}")

    save_signals("insider", signals)

    print("\n" + "=" * 50)
    print("INSIDER TRACKER SUMMARY")
    print("=" * 50)
    for s in signals:
        emoji = "🟢" if s["signal"] == "bullish" else ("🔴" if s["signal"] == "bearish" else "🟡")
        print(f"  {emoji} {s['ticker']:6s} | {s['summary'][:70]}")

    return signals


if __name__ == "__main__":
    main()
