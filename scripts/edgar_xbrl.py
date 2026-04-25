#!/usr/bin/env python3
"""
edgar_xbrl.py — Point-in-time financial data from SEC EDGAR XBRL.

Provides a DataProvider-compatible interface for fetching financial data
directly from SEC filings (10-K, 10-Q) via the EDGAR XBRL API.

Advantages over yfinance/EODHD:
  - Point-in-time: no look-ahead bias (filing date is the knowledge date)
  - Free, no API key required
  - Audited/authoritative numbers (directly from SEC filings)
  - Includes filing dates for proper backtesting alignment

EDGAR XBRL API endpoints:
  - Company facts: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
  - Company concept: https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json

Usage:
    from edgar_xbrl import EdgarProvider
    provider = EdgarProvider()
    data = provider.fetch("AAPL")
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore

# SEC requires a User-Agent header identifying the requester
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "StockRadar/1.0 (asyanurpekel@gmail.com)",
)

# Rate limiting: SEC allows 10 requests/second
_last_request_time = 0.0
_MIN_REQUEST_INTERVAL = 0.12  # 120ms between requests


# CIK lookup cache
_CIK_CACHE: dict[str, str] = {}
_CIK_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "cik_cache.json"


def _rate_limit():
    """Enforce SEC rate limit."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _load_cik_cache():
    """Load CIK cache from disk."""
    global _CIK_CACHE
    if _CIK_CACHE_FILE.exists():
        try:
            _CIK_CACHE = json.loads(_CIK_CACHE_FILE.read_text())
        except Exception:
            _CIK_CACHE = {}


def _save_cik_cache():
    """Save CIK cache to disk."""
    _CIK_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CIK_CACHE_FILE.write_text(json.dumps(_CIK_CACHE, indent=2))


def _load_ticker_map() -> dict[str, str]:
    """Load the full ticker→CIK map from SEC's company_tickers.json.

    This is cached in-memory after the first call.  The file is ~2 MB and
    contains every ticker that has ever filed with the SEC.
    """
    global _TICKER_MAP
    if _TICKER_MAP is not None:
        return _TICKER_MAP

    if not requests:
        return {}

    _rate_limit()
    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            _TICKER_MAP = {
                v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                for v in data.values()
            }
            return _TICKER_MAP
    except Exception as e:
        print(f"  [edgar] Failed to load company_tickers.json: {e}")

    _TICKER_MAP = {}
    return _TICKER_MAP


_TICKER_MAP: dict[str, str] | None = None


def lookup_cik(ticker: str) -> str | None:
    """Look up the CIK number for a ticker symbol via EDGAR.

    Uses the modern company_tickers.json endpoint (the old browse-edgar
    CGI is deprecated).  Results are cached to disk for speed.

    Returns zero-padded 10-digit CIK string, or None if not found.
    """
    if not requests:
        return None

    ticker = ticker.upper()
    _load_cik_cache()
    if ticker in _CIK_CACHE:
        return _CIK_CACHE[ticker]

    # Look up in the full SEC ticker map
    ticker_map = _load_ticker_map()
    cik = ticker_map.get(ticker)
    if cik:
        _CIK_CACHE[ticker] = cik
        _save_cik_cache()
        return cik

    print(f"  [edgar] Ticker {ticker} not found in SEC company_tickers.json")
    return None


def fetch_company_facts(cik: str) -> dict | None:
    """Fetch all XBRL facts for a company from EDGAR.

    Returns the full company facts JSON, which contains all reported
    financial data across all filings, tagged by concept.
    """
    if not requests:
        return None

    _rate_limit()
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        print(f"  [edgar] Company facts returned {resp.status_code} for CIK {cik}")
    except Exception as e:
        print(f"  [edgar] Company facts fetch failed for CIK {cik}: {e}")
    return None


def extract_quarterly_data(
    facts: dict,
    concept: str = "Revenues",
    taxonomy: str = "us-gaap",
) -> list[dict]:
    """Extract quarterly point-in-time data for a concept.

    Returns chronologically sorted list of:
      {
        "period": "2025-Q1",
        "value": 12345678.0,
        "filed": "2025-04-30",  # filing date (point-in-time)
        "form": "10-Q",
        "start": "2025-01-01",
        "end": "2025-03-31",
      }

    The `filed` date is critical for backtesting — it's when the market
    first learned this information.
    """
    try:
        units = facts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {})
    except (AttributeError, TypeError):
        return []

    # Find the right unit (usually USD for financials)
    unit_data = units.get("USD") or units.get("USD/shares") or units.get("shares") or []
    if not unit_data:
        # Try the first available unit
        for u in units.values():
            unit_data = u
            break

    # Filter for quarterly filings (10-Q) with specific end dates
    quarterly = []
    for item in unit_data:
        form = item.get("form", "")
        if form not in ("10-Q", "10-K"):
            continue
        start = item.get("start")
        end = item.get("end")
        filed = item.get("filed")
        val = item.get("val")

        if not (start and end and filed and val is not None):
            continue

        # Calculate period length to filter for quarters (~90 days)
        try:
            d_start = datetime.strptime(start, "%Y-%m-%d")
            d_end = datetime.strptime(end, "%Y-%m-%d")
            days = (d_end - d_start).days
        except ValueError:
            continue

        if 60 <= days <= 100:
            # Quarterly
            quarter = (d_end.month - 1) // 3 + 1
            quarterly.append({
                "period": f"{d_end.year}-Q{quarter}",
                "value": float(val),
                "filed": filed,
                "form": form,
                "start": start,
                "end": end,
            })

    # Sort chronologically
    quarterly.sort(key=lambda x: x["end"])

    # Deduplicate (keep latest filing per period)
    seen: dict[str, dict] = {}
    for q in quarterly:
        key = q["period"]
        if key not in seen or q["filed"] > seen[key]["filed"]:
            seen[key] = q
    return list(seen.values())


# Key XBRL concepts for financial data extraction
REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]

INCOME_CONCEPTS = {
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "ebitda": [
        "OperatingIncomeLoss",  # EBITDA not directly reported; we add D&A
    ],
}

BALANCE_SHEET_CONCEPTS = {
    "total_assets": ["Assets"],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "total_debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
}


def fetch_point_in_time(ticker: str) -> dict | None:
    """Fetch point-in-time financial data for a ticker from SEC EDGAR.

    Returns a dict with quarterly time series, each entry tagged with
    the filing date (when the market first learned this data).

    This is the primary interface for backtesting-safe financial data.
    """
    cik = lookup_cik(ticker)
    if not cik:
        print(f"  [edgar] No CIK found for {ticker}")
        return None

    facts = fetch_company_facts(cik)
    if not facts:
        return None

    result: dict[str, Any] = {
        "ticker": ticker,
        "cik": cik,
        "entity_name": facts.get("entityName", ""),
        "revenue_quarterly": [],
        "income_quarterly": {},
        "balance_sheet": {},
        "filing_dates": [],  # all filing dates for alignment
    }

    # Extract revenue — pick the concept with the most recent filing
    # (companies migrate between XBRL concepts over time, e.g. "Revenues"
    # → "RevenueFromContractWithCustomerExcludingAssessedTax")
    best_rev, best_rev_end = [], ""
    for concept in REVENUE_CONCEPTS:
        data = extract_quarterly_data(facts, concept)
        if data:
            latest_end = max(d["end"] for d in data)
            if latest_end > best_rev_end:
                best_rev, best_rev_end = data, latest_end
    result["revenue_quarterly"] = best_rev

    # Extract income items — same "most recent" logic
    for key, concepts in INCOME_CONCEPTS.items():
        best, best_end = [], ""
        for concept in concepts:
            data = extract_quarterly_data(facts, concept)
            if data:
                latest_end = max(d["end"] for d in data)
                if latest_end > best_end:
                    best, best_end = data, latest_end
        if best:
            result["income_quarterly"][key] = best

    # Extract balance sheet items
    for key, concepts in BALANCE_SHEET_CONCEPTS.items():
        best, best_end = [], ""
        for concept in concepts:
            data = extract_quarterly_data(facts, concept)
            if data:
                latest_end = max(d["end"] for d in data)
                if latest_end > best_end:
                    best, best_end = data, latest_end
        if best:
            result["balance_sheet"][key] = best

    # Collect all filing dates
    all_dates = set()
    for q in result["revenue_quarterly"]:
        all_dates.add(q["filed"])
    result["filing_dates"] = sorted(all_dates)

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch EDGAR XBRL data")
    parser.add_argument("ticker", help="Stock ticker (e.g., AAPL)")
    args = parser.parse_args()

    data = fetch_point_in_time(args.ticker)
    if data:
        print(f"\n{data['entity_name']} (CIK: {data['cik']})")
        print(f"Revenue quarters: {len(data['revenue_quarterly'])}")
        if data["revenue_quarterly"]:
            latest = data["revenue_quarterly"][-1]
            print(f"Latest: {latest['period']} = ${latest['value']/1e9:.2f}B (filed {latest['filed']})")
        print(f"Filing dates: {len(data['filing_dates'])}")
    else:
        print(f"No data found for {args.ticker}")
