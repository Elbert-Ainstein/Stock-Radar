#!/usr/bin/env python3
"""
refresh_prices.py — fast quote-only refresh for the watchlist.

Why this exists: the dashboard reads `analysis.price_data` which only updates
when the full scout pipeline runs (~10-15 min, all scouts including expensive
ones). Stock prices go stale within hours. This script does a quote-only
update — yfinance fast_info on each watchlist ticker, then writes the new
`{price, change, change_pct, market_cap_b}` to the LATEST analysis row per
ticker. Takes ~30 seconds for a 13-ticker watchlist.

Does NOT update fundamentals, signals, theses, or anything else.
Does NOT trigger the pipeline.
Does NOT cost API tokens (yfinance is free).

Usage:
  python scripts/refresh_prices.py              # all watchlist tickers
  python scripts/refresh_prices.py SNDK LITE    # specific tickers
  python scripts/refresh_prices.py --dry-run    # show what would change

Run it whenever the prices are visibly stale. Recommended: keep it as a
manual command for now; later turn it into a 5-minute cron during market hours.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env

load_env()

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def fetch_quote(ticker: str) -> dict | None:
    """Return {price, change, change_pct, market_cap_b} or None on failure.

    Uses yfinance fast_info (lightweight) with a fall back to .info if fast_info
    is unavailable for some tickers. ~1 sec per ticker."""
    try:
        import yfinance as yf
    except ImportError:
        print("[refresh_prices] yfinance not installed: pip install yfinance --break-system-packages", file=sys.stderr)
        sys.exit(1)

    try:
        t = yf.Ticker(ticker)
        # fast_info is faster but doesn't always have all fields
        try:
            fi = t.fast_info
            price = float(fi.get("last_price") or fi.get("lastPrice") or 0)
            prev = float(fi.get("previous_close") or fi.get("previousClose") or 0)
            mcap = fi.get("market_cap") or fi.get("marketCap") or 0
        except Exception:
            info = t.info
            price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
            prev = float(info.get("previousClose") or 0)
            mcap = info.get("marketCap") or 0
        if price <= 0 or prev <= 0:
            return None
        change = price - prev
        change_pct = (change / prev * 100) if prev > 0 else 0
        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "market_cap_b": round((mcap or 0) / 1e9, 2),
        }
    except Exception as e:
        print(f"  [{ticker}] fetch failed: {e}", file=sys.stderr)
        return None


def get_watchlist_tickers() -> list[str]:
    """Read the active watchlist tickers from Supabase (discovery_universe rows
    with status='watchlisted'). Falls back to local watchlist.json if Supabase
    is unavailable."""
    from supabase_helper import get_client
    sb = get_client()
    try:
        r = sb.table("discovery_universe").select("ticker").eq("status", "watchlisted").execute()
        return [row["ticker"] for row in (r.data or [])]
    except Exception:
        from utils import get_watchlist
        return [s["ticker"] for s in get_watchlist()]


def update_price(sb, ticker: str, quote: dict, dry_run: bool = False) -> bool:
    """Update the LATEST analysis row for `ticker` with the new price_data.

    Returns True if updated, False if no analysis row found or write failed.
    """
    rows = sb.table("analysis").select("id,price_data,created_at").eq(
        "ticker", ticker
    ).order("created_at", desc=True).limit(1).execute().data or []
    if not rows:
        print(f"  [{ticker}] no analysis row to update", file=sys.stderr)
        return False
    latest = rows[0]
    new_price_data = dict(latest.get("price_data") or {})
    old_price = new_price_data.get("price")
    new_price_data.update(quote)

    if dry_run:
        print(f"  [{ticker}] DRY: ${old_price} → ${quote['price']} ({quote['change_pct']:+.2f}%)")
        return True

    try:
        sb.table("analysis").update({"price_data": new_price_data}).eq("id", latest["id"]).execute()
        print(f"  [{ticker}] ${old_price} → ${quote['price']} ({quote['change_pct']:+.2f}%) "
              f"mcap=${quote['market_cap_b']:.1f}B")
        return True
    except Exception as e:
        print(f"  [{ticker}] update failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*",
                        help="Specific tickers to refresh. Default: all watchlist names.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change; don't write.")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = get_watchlist_tickers()

    if not tickers:
        print("[refresh_prices] no tickers to refresh", file=sys.stderr)
        sys.exit(1)

    print(f"=== refresh_prices — {len(tickers)} tickers @ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} ===")

    from supabase_helper import get_client
    sb = get_client()

    summary = {"updated": 0, "no_quote": 0, "no_row": 0, "skipped": 0}
    for t in tickers:
        quote = fetch_quote(t)
        if quote is None:
            print(f"  [{t}] no quote available", file=sys.stderr)
            summary["no_quote"] += 1
            continue
        ok = update_price(sb, t, quote, dry_run=args.dry_run)
        if ok:
            summary["updated"] += 1
        else:
            summary["no_row"] += 1

    print(f"\n  result: {summary}")


if __name__ == "__main__":
    main()
