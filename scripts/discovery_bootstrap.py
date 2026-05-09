#!/usr/bin/env python3
"""
discovery_bootstrap.py - Seed discovery_universe with the existing watchlist.

Reads active watchlist from Supabase `stocks` table, fetches market cap +
currency via yfinance, FX-normalizes to USD with hard-fail, and upserts each
ticker into discovery_universe with status='watchlisted' and source='watchlist_seed'.

watchlisted rows are excluded from cheap-scan demotion (they have full theses
already). They participate in the universe so the discovery UI can show
"already in watchlist" alongside discovered candidates.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env  # noqa: E402
load_env()

import yfinance as yf  # noqa: E402

from scout_discovery import detect_market  # noqa: E402
from discovery_ingest import get_fx_to_usd  # noqa: E402


def load_active_watchlist() -> list[dict]:
    from supabase_helper import get_client
    sb = get_client()
    resp = sb.table("stocks").select("ticker,name,sector,active").execute()
    rows = resp.data or []
    return [r for r in rows if r.get("active", True) != False]


def upsert_universe_row(row: dict) -> bool:
    from supabase_helper import get_client
    sb = get_client()
    try:
        sb.table("discovery_universe").upsert(
            row, on_conflict="ticker"
        ).execute()
        return True
    except Exception as e:
        print(f"  [DB] upsert failed for {row['ticker']}: {e}")
        return False


def main() -> int:
    watchlist = load_active_watchlist()
    if not watchlist:
        print("ERROR: no active watchlist tickers found", file=sys.stderr)
        return 1

    print("=" * 60)
    print(f"  BOOTSTRAP - {len(watchlist)} active watchlist tickers")
    print("=" * 60)
    print()

    fx_cache: dict[str, float] = {"USD": 1.0}
    written = 0
    fx_failures = 0

    for entry in watchlist:
        ticker = entry["ticker"]
        market = detect_market(ticker)
        sys.stdout.write(f"  [{ticker:<10}] ({market}) ")
        sys.stdout.flush()

        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as e:
            print(f"yfinance error: {e}")
            continue

        mc_local = info.get("marketCap")
        if not mc_local:
            print("no marketCap from yfinance, skipping")
            continue

        currency = (info.get("currency") or "USD").upper()
        try:
            rate = get_fx_to_usd(currency, ticker)
        except RuntimeError as e:
            print(f"FX fail: {e}")
            fx_failures += 1
            continue

        mc_usd = float(mc_local) * rate

        row = {
            "ticker": ticker,
            "market": market,
            "company_name": info.get("longName") or info.get("shortName") or entry.get("name") or ticker,
            "sector": info.get("sector") or entry.get("sector") or None,
            "source": "watchlist_seed",
            "status": "watchlisted",
            "market_cap_usd": round(mc_usd, 2),
            "currency": currency,
        }

        if upsert_universe_row(row):
            written += 1
            print(f"OK  ${mc_usd/1e9:.1f}B  {row['company_name'][:35]}")
        else:
            print("DB write failed")

    print()
    print("-" * 60)
    print(f"  written: {written}/{len(watchlist)}")
    print(f"  fx fails: {fx_failures}")
    print("-" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
