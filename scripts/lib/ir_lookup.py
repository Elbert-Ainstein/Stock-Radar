"""
ir_lookup.py - Auto-discover company IR domain + metadata for any ticker.

Strategy:
  - US tickers (e.g. AEHR, LITE) → SEC EDGAR company_tickers + submissions API
    returns CIK, full company name, official website
  - HK tickers (e.g. 6082.HK, 0700.HK) → web search for company name +
    parse first credible IR domain from results
  - Other (e.g. ASML on Nasdaq, foreign ADRs) → SEC first, fallback to web search

Cached in data/ir_cache.json. 90-day TTL by default. The runner calls
get_ir_metadata(ticker) lazily; on cache miss, looks up and persists.

Cache entry shape:
{
    "company_name": "Aehr Test Systems",
    "ir_domain":    "aehr.com",
    "exchange":     "NASDAQ",
    "currency":     "USD",
    "country":      "US",
    "cik":          "0000711377",       (US only)
    "ticker_query": "AEHR",
    "looked_up_at": "2026-05-02T18:30:00+00:00"
}
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = REPO_ROOT / "data" / "ir_cache.json"
CACHE_TTL_DAYS = 90

# SEC EDGAR endpoints
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_USER_AGENT = "Stock Radar (asyanurpekel@gmail.com)"  # SEC requires UA on data API

# Module-level cache for the ticker→CIK map (it's ~600KB, load once)
_SEC_TICKERS: Optional[dict] = None


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _is_fresh(entry: dict) -> bool:
    """Cache hit is fresh if within TTL."""
    looked_up = entry.get("looked_up_at")
    if not looked_up:
        return False
    try:
        when = datetime.fromisoformat(looked_up)
    except (ValueError, TypeError):
        return False
    return datetime.now(timezone.utc) - when < timedelta(days=CACHE_TTL_DAYS)


def _classify_ticker(ticker: str) -> str:
    """Identify which exchange a ticker likely belongs to.

    Returns: "US" | "HK" | "OTHER"
    """
    t = ticker.upper().strip()
    # Hong Kong: numeric-only or .HK suffix or 4-digit
    if t.endswith(".HK") or re.fullmatch(r"\d{4,5}", t):
        return "HK"
    # London Stock Exchange
    if t.endswith(".L") or t.endswith(".LON"):
        return "OTHER"
    # Toronto
    if t.endswith(".TO"):
        return "OTHER"
    # Default: US (handles plain alphabetic tickers like AEHR, LITE, BRK.B)
    return "US"


# ─────────────────────────────────────────────────────────────────────
# US lookup via SEC EDGAR
# ─────────────────────────────────────────────────────────────────────

def _fetch_sec_tickers() -> dict:
    """Load the SEC's ticker→CIK index (cached in module memory)."""
    global _SEC_TICKERS
    if _SEC_TICKERS is not None:
        return _SEC_TICKERS

    import requests
    headers = {"User-Agent": SEC_USER_AGENT}
    r = requests.get(SEC_TICKERS_URL, headers=headers, timeout=15)
    r.raise_for_status()
    raw = r.json()  # {"0": {"cik_str": ..., "ticker": "AAPL", "title": "..."}, ...}
    by_ticker = {}
    for v in raw.values():
        by_ticker[v["ticker"].upper()] = {
            "cik": int(v["cik_str"]),
            "name": v.get("title", ""),
        }
    _SEC_TICKERS = by_ticker
    return _SEC_TICKERS


def _lookup_us_via_sec(ticker: str) -> Optional[dict]:
    """Look up a US ticker via SEC EDGAR. Returns metadata dict or None."""
    import requests
    try:
        idx = _fetch_sec_tickers()
    except Exception as e:
        print(f"  [ir_lookup] SEC tickers fetch failed: {e}", file=sys.stderr)
        return None

    entry = idx.get(ticker.upper())
    if not entry:
        return None

    cik = entry["cik"]
    name = entry["name"]
    # Get the website from submissions endpoint
    try:
        url = SEC_SUBMISSIONS_URL.format(cik=cik)
        r = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=15)
        r.raise_for_status()
        sub = r.json()
        website = sub.get("website") or ""
        # Note: SEC's `website` field is sometimes empty; in that case derive
        # from the company name → google heuristic, but for now leave blank
        # and let the runner fall back to global allowlist.
        ir_domain = _extract_domain(website) if website else ""
    except Exception as e:
        print(f"  [ir_lookup] SEC submissions fetch failed for {ticker}: {e}", file=sys.stderr)
        ir_domain = ""

    return {
        "company_name": name,
        "ir_domain": ir_domain,
        "exchange": "US",  # could refine to NASDAQ/NYSE via sub.get("exchanges") but US is enough
        "currency": "USD",
        "country": "US",
        "cik": f"{cik:010d}",
        "ticker_query": ticker.upper(),
        "looked_up_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────
# HK / international lookup via web search
# ─────────────────────────────────────────────────────────────────────

# Companies the runner has been hand-told about — populated when the
# Anthropic web_search confirms a match. For a one-time run we can
# also let an outer caller pre-populate this map.
_BUILTIN_HK_NAMES = {
    "6082": "Shanghai Biren Technology Co., Ltd.",
    "0700": "Tencent Holdings Limited",
    "9988": "Alibaba Group Holding Limited",
    "1810": "Xiaomi Corporation",
}


def _lookup_hk_minimal(ticker: str) -> dict:
    """Minimal HK metadata without web_search (used for initial bootstrap).

    For unknown HK tickers, returns a best-effort skeleton; the actual
    company name + IR domain enrichment happens on first thesis run when
    Claude has web_search access.
    """
    base = ticker.upper().replace(".HK", "").lstrip("0")
    name = _BUILTIN_HK_NAMES.get(base) or _BUILTIN_HK_NAMES.get(ticker.upper().replace(".HK", "")) or f"HK Ticker {ticker}"
    return {
        "company_name": name,
        "ir_domain": "",  # will be enriched by runner if it cites IR pages
        "exchange": "HKEX",
        "currency": "HKD",
        "country": "HK",
        "cik": "",
        "ticker_query": f"{base} HK Hong Kong stock",
        "looked_up_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _extract_domain(url_or_domain: str) -> str:
    """Strip protocol, www, and path. 'https://www.aehr.com/investors' → 'aehr.com'."""
    if not url_or_domain:
        return ""
    s = url_or_domain.strip().lower()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    try:
        host = urlparse(s).netloc or ""
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def get_ir_metadata(ticker: str, force_refresh: bool = False) -> dict:
    """Get company metadata for a ticker, with cache.

    On cache miss, looks up via the appropriate path:
      US → SEC EDGAR
      HK → minimal bootstrap (name from builtin, domain enriched lazily)

    Returns a dict with at least:
      company_name, ir_domain, exchange, currency, country, ticker_query
    """
    cache = _load_cache()
    key = ticker.upper()

    if not force_refresh and key in cache and _is_fresh(cache[key]):
        return cache[key]

    classification = _classify_ticker(ticker)
    if classification == "US":
        result = _lookup_us_via_sec(ticker)
        if result is None:
            # Fallback: minimal record so caller doesn't crash
            result = {
                "company_name": ticker,
                "ir_domain": "",
                "exchange": "UNKNOWN",
                "currency": "USD",
                "country": "US",
                "cik": "",
                "ticker_query": ticker,
                "looked_up_at": datetime.now(timezone.utc).isoformat(),
            }
    elif classification == "HK":
        result = _lookup_hk_minimal(ticker)
    else:
        result = {
            "company_name": ticker,
            "ir_domain": "",
            "exchange": "OTHER",
            "currency": "USD",  # caller may override
            "country": "OTHER",
            "cik": "",
            "ticker_query": ticker,
            "looked_up_at": datetime.now(timezone.utc).isoformat(),
        }

    cache[key] = result
    _save_cache(cache)
    return result


def update_ir_domain(ticker: str, ir_domain: str) -> None:
    """Enrich a cache entry with an IR domain discovered after first thesis run.

    The runner calls this when Claude's web_search citations include a
    company-IR-looking domain that wasn't in the cache.
    """
    domain = _extract_domain(ir_domain)
    if not domain:
        return
    cache = _load_cache()
    key = ticker.upper()
    if key in cache:
        cache[key]["ir_domain"] = domain
        _save_cache(cache)


if __name__ == "__main__":
    # Smoke-test the lookup
    for t in ["LITE", "AEHR", "PLTR", "6082.HK", "ASML"]:
        meta = get_ir_metadata(t)
        print(f"{t:10} → {meta['company_name'][:40]:40} | {meta['ir_domain']:30} | {meta['exchange']}")
