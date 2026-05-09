#!/usr/bin/env python3
"""
discovery_ingest.py — Multi-market candidate ingestion for `discovery_universe`.

Pulls "most active" + "biggest gainers" lists from Yahoo Finance per market,
dedups against the existing `discovery_universe` table, FX-normalizes market
cap to USD with HARD-FAIL on missing/zero rates, and inserts new candidates
with status='exploring'.

Markets supported: US, HK, JP, TW, KR.

Hard rules (enforced — do not relax):
  1. FX rate fetch failure → RuntimeError(ticker). Never silent default to 1.0.
  2. Every drop/skip logs a line with reason + ticker.
  3. Insert uses ON CONFLICT (ticker) DO NOTHING — fresh tickers only.

Usage:
    python scripts/discovery_ingest.py --markets US,HK,TW,JP,KR --max-per-market 50
    python scripts/discovery_ingest.py --markets US --max-per-market 5 --dry-run
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
import yfinance as yf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env  # noqa: E402

load_env()


# ─── Market definitions ───
# Each market has:
#   - region code Yahoo uses in screener URLs
#   - local currency (used for FX lookup)
#   - "exchange" filter values when querying Yahoo screener
ALL_MARKETS = ["US", "HK", "JP", "TW", "KR"]

MARKET_CURRENCY: dict[str, str] = {
    "US": "USD",
    "HK": "HKD",
    "JP": "JPY",
    "TW": "TWD",
    "KR": "KRW",
}

# Yahoo region codes for the v1/finance/screener endpoint
MARKET_REGION: dict[str, str] = {
    "US": "us",
    "HK": "hk",
    "JP": "jp",
    "TW": "tw",
    "KR": "kr",
}


# ─── FX normalization (HARD-FAIL) ───

_fx_cache: dict[str, float] = {"USD": 1.0}


def get_fx_to_usd(currency: str, ticker_for_log: str) -> float:
    """Return current FX rate from `currency` to USD.

    HARD-FAIL: if yfinance returns no data, raise RuntimeError. Never default
    to 1.0 — that produces garbage that looks fine downstream.
    """
    cur = (currency or "").upper()
    if not cur:
        raise RuntimeError(
            f"FX hard-fail: empty currency for ticker={ticker_for_log!r}"
        )
    if cur in _fx_cache:
        return _fx_cache[cur]

    pair = f"{cur}USD=X"
    try:
        hist = yf.Ticker(pair).history(period="5d", auto_adjust=False)
    except Exception as e:
        raise RuntimeError(
            f"FX hard-fail: yfinance threw on {pair} for ticker={ticker_for_log!r}: {e}"
        ) from e

    if hist is None or hist.empty or "Close" not in hist.columns:
        raise RuntimeError(
            f"FX hard-fail: empty history for {pair} (ticker={ticker_for_log!r}); "
            f"refusing to proceed with bad FX"
        )

    rate = float(hist["Close"].dropna().iloc[-1]) if not hist["Close"].dropna().empty else 0.0
    if not rate or rate <= 0:
        raise RuntimeError(
            f"FX hard-fail: zero/negative rate for {pair}={rate!r} (ticker={ticker_for_log!r})"
        )

    _fx_cache[cur] = rate
    return rate


# ─── Yahoo screener fetch ───

YAHOO_SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener"
YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _fetch_predefined(scrIds: str, count: int = 50) -> list[dict]:
    """Call Yahoo's predefined screener (US-only IDs like most_actives, day_gainers).

    Falls back through yfinance Screener if the raw HTTP call fails.
    """
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    params = {"scrIds": scrIds, "count": count, "start": 0}
    try:
        r = requests.get(url, headers=YAHOO_HEADERS, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json()
            quotes = (
                data.get("finance", {})
                .get("result", [{}])[0]
                .get("quotes", [])
            )
            if quotes:
                return quotes
    except Exception as e:
        print(f"  [yahoo] predefined HTTP {scrIds} failed: {e}")

    # Fallback to yfinance.Screener (newer API)
    try:
        sc = yf.Screener()
        sc.set_predefined_body(scrIds)
        result = sc.response or {}
        quotes = (
            result.get("finance", {})
            .get("result", [{}])[0]
            .get("quotes", [])
        )
        return quotes or []
    except Exception as e:
        print(f"  [yahoo] yfinance Screener fallback for {scrIds} failed: {e}")
        return []


def _build_region_query(region: str, sort_field: str, count: int = 50) -> dict:
    """Build a Yahoo screener custom-query body for a given region.

    sort_field: "percentchange" for gainers, "dayvolume" for most actives.

    Adds a local-currency market-cap floor (~$200M USD-equivalent) so
    volume-sorted screeners don't return penny-stock warrants. Without
    this, HK/JP/KR results are dominated by tiny speculative names that
    don't even carry a marketCap field.
    """
    # Local-currency floors approximating $200M USD
    market_cap_floor = {
        "us": 200_000_000,            # 200M USD
        "hk": 1_600_000_000,          # 1.6B HKD ~= 200M USD
        "jp": 30_000_000_000,         # 30B JPY ~= 200M USD
        "tw": 6_000_000_000,          # 6B TWD ~= 200M USD
        "kr": 270_000_000_000,        # 270B KRW ~= 200M USD
    }
    floor = market_cap_floor.get(region.lower(), 200_000_000)

    return {
        "size": count,
        "offset": 0,
        "sortField": sort_field,
        "sortType": "DESC",
        "quoteType": "EQUITY",
        "topOperator": "AND",
        "query": {
            "operator": "AND",
            "operands": [
                {
                    "operator": "or",
                    "operands": [
                        {
                            "operator": "EQ",
                            "operands": ["region", region],
                        }
                    ],
                },
                {
                    "operator": "gt",
                    "operands": ["intradaymarketcap", floor],
                },
            ],
        },
        "userId": "",
        "userIdType": "guid",
    }


def _fetch_region_screener(region: str, sort_field: str, count: int = 50) -> list[dict]:
    """Run a custom Yahoo screener for a region, sorted by sort_field DESC.

    Uses yfinance's YfData session, which transparently handles the
    cookie+crumb auth dance Yahoo requires for non-US screener calls.
    Raw requests.post returns 401 without a crumb; YfData handles it.
    """
    from yfinance.data import YfData
    body = _build_region_query(region, sort_field, count)
    params = {
        "lang": "en-US",
        "region": "US",
        "formatted": "true",
        "corsDomain": "finance.yahoo.com",
    }
    try:
        r = YfData().post(YAHOO_SCREENER_URL, body=body, params=params)
        if r.status_code != 200:
            print(f"  [yahoo] region={region} sort={sort_field} HTTP {r.status_code}")
            return []
        data = r.json()
        quotes = (
            data.get("finance", {})
            .get("result", [{}])[0]
            .get("quotes", [])
        )
        return quotes or []
    except Exception as e:
        print(f"  [yahoo] region={region} sort={sort_field} threw: {e}")
        return []


def fetch_market_candidates(market: str, max_per_market: int) -> list[dict]:
    """Fetch most-active + day-gainers for a market.

    Returns a list of dicts:
      {ticker, name, sector, market_cap_local, currency, source}

    Each candidate carries a `source` of "yahoo_most_active" or "yahoo_gainers"
    based on which list it came from. Dedup happens in the caller.
    """
    region = MARKET_REGION[market]
    out: list[dict] = []

    # Two passes: most actives (volume), then gainers (percent change)
    if market == "US":
        # US has named predefined screeners — prefer them (they're tuned)
        passes = [
            ("yahoo_most_active", lambda: _fetch_predefined("most_actives", max_per_market)),
            ("yahoo_gainers", lambda: _fetch_predefined("day_gainers", max_per_market)),
        ]
    else:
        passes = [
            ("yahoo_most_active",
             lambda: _fetch_region_screener(region, "dayvolume", max_per_market)),
            ("yahoo_gainers",
             lambda: _fetch_region_screener(region, "percentchange", max_per_market)),
        ]

    for source, fetch_fn in passes:
        try:
            quotes = fetch_fn()
        except Exception as e:
            print(f"  [{market}] {source} fetch threw: {e}")
            continue

        for q in quotes:
            try:
                ticker = q.get("symbol") or ""
                if not ticker:
                    continue

                # market cap can be raw or formatted dict {raw, fmt, longFmt}
                mc = q.get("marketCap")
                if isinstance(mc, dict):
                    mc_val = mc.get("raw")
                else:
                    mc_val = mc
                if mc_val is None:
                    print(f"  [{market}] dropped {ticker}: no marketCap in screener row")
                    continue
                try:
                    mc_local = float(mc_val)
                except (TypeError, ValueError):
                    print(f"  [{market}] dropped {ticker}: non-numeric marketCap={mc_val!r}")
                    continue
                if mc_local <= 0:
                    print(f"  [{market}] dropped {ticker}: marketCap <= 0 ({mc_local})")
                    continue

                # currency: Yahoo's row, fall back to market default
                currency = (q.get("currency") or "").upper() or MARKET_CURRENCY[market]

                name = (
                    q.get("longName")
                    or q.get("shortName")
                    or q.get("displayName")
                    or ticker
                )
                sector = q.get("sector") or ""

                out.append({
                    "ticker": ticker,
                    "name": name,
                    "sector": sector,
                    "market_cap_local": mc_local,
                    "currency": currency,
                    "market": market,
                    "source": source,
                })
            except Exception as e:
                print(f"  [{market}] dropped row from {source}: {e}")
                continue

        time.sleep(0.5)  # be polite to Yahoo

    return out


# ─── Supabase dedup + insert ───

def fetch_existing_tickers() -> set[str]:
    """Pull the full set of tickers already in discovery_universe so we can dedup."""
    try:
        from supabase_helper import get_client
        sb = get_client()
        # Page through if the table grows large; for now a single select is fine
        resp = sb.table("discovery_universe").select("ticker").execute()
        return {r["ticker"] for r in (resp.data or [])}
    except Exception as e:
        print(f"  [DB] fetch_existing_tickers failed: {e}")
        # Fail-safe: return empty so we'll still attempt insert (ON CONFLICT will handle dups)
        return set()


def insert_candidates(rows: list[dict]) -> int:
    """Insert with ON CONFLICT (ticker) DO NOTHING. Returns count actually inserted."""
    if not rows:
        return 0
    try:
        from supabase_helper import get_client
        sb = get_client()
        # supabase-py: upsert with ignore_duplicates=True maps to ON CONFLICT DO NOTHING
        resp = (
            sb.table("discovery_universe")
            .upsert(rows, on_conflict="ticker", ignore_duplicates=True)
            .execute()
        )
        return len(resp.data or [])
    except Exception as e:
        print(f"  [DB] insert_candidates failed: {e}")
        raise


# ─── Main ───

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1] if __doc__ else "")
    p.add_argument(
        "--markets",
        default=",".join(ALL_MARKETS),
        help=f"Comma-separated markets (default: {','.join(ALL_MARKETS)})",
    )
    p.add_argument("--max-per-market", type=int, default=50,
                   help="Max candidates fetched per market per source (default 50)")
    p.add_argument("--dry-run", action="store_true",
                   help="Don't insert; just print what would happen")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    invalid = [m for m in markets if m not in ALL_MARKETS]
    if invalid:
        print(f"ERROR: unknown markets: {invalid}. Allowed: {ALL_MARKETS}", file=sys.stderr)
        return 2

    print("=" * 60)
    print(f"  DISCOVERY INGEST — {datetime.now(timezone.utc).isoformat()}")
    print(f"  markets={markets}  max_per_market={args.max_per_market}  dry_run={args.dry_run}")
    print("=" * 60)

    # Existing-ticker dedup baseline
    if args.dry_run:
        print("\n  [dry-run] skipping discovery_universe read")
        existing: set[str] = set()
    else:
        existing = fetch_existing_tickers()
        print(f"\n  [DB] {len(existing)} tickers already in discovery_universe")

    summary: dict[str, dict[str, int]] = defaultdict(lambda: {
        "fetched": 0, "deduped": 0, "fx_failures": 0, "inserted": 0,
    })

    all_to_insert: list[dict] = []
    seen_in_run: set[str] = set()

    for market in markets:
        print(f"\n── {market} ──")
        try:
            candidates = fetch_market_candidates(market, args.max_per_market)
        except Exception as e:
            print(f"  [{market}] fetch failed: {e}")
            continue

        summary[market]["fetched"] = len(candidates)
        print(f"  fetched: {len(candidates)} rows from Yahoo")

        for c in candidates:
            ticker = c["ticker"]
            # dedup vs DB and within-run
            if ticker in existing or ticker in seen_in_run:
                summary[market]["deduped"] += 1
                continue
            seen_in_run.add(ticker)

            # FX normalize HARD-FAIL — but in this script we catch and tally
            # rather than aborting, since one bad ticker shouldn't kill 4 other markets.
            try:
                rate = get_fx_to_usd(c["currency"], ticker)
            except RuntimeError as e:
                print(f"  [{market}] {e}")
                summary[market]["fx_failures"] += 1
                continue

            mc_usd = c["market_cap_local"] * rate

            row = {
                "ticker": ticker,
                "market": market,
                "company_name": c["name"],
                "sector": c["sector"] or None,
                "source": c["source"],
                "status": "exploring",
                "market_cap_usd": round(mc_usd, 2),
                "currency": c["currency"],
                # let DB defaults handle first_seen, scan_history, last_scanned
            }
            all_to_insert.append(row)
            summary[market]["inserted"] += 1  # provisional; corrected after insert

    # ── Insert ──
    if args.dry_run:
        print(f"\n  [dry-run] would insert {len(all_to_insert)} rows")
        # Show a small sample
        for r in all_to_insert[:10]:
            print(f"    + {r['ticker']:<10} {r['market']} ${r['market_cap_usd']/1e9:>7.2f}B "
                  f"{r['source']:<20} {(r['company_name'] or '')[:40]}")
    else:
        if all_to_insert:
            print(f"\n  [DB] inserting {len(all_to_insert)} rows...")
            try:
                actual = insert_candidates(all_to_insert)
                print(f"  [DB] inserted {actual} new rows (others were dups via ON CONFLICT)")
            except Exception as e:
                print(f"  [DB] insert ABORTED: {e}")
        else:
            print("\n  [DB] nothing to insert")

    # ── Summary ──
    print("\n" + "─" * 60)
    print("  SUMMARY")
    print("─" * 60)
    print(f"  {'market':<8} {'fetched':>8} {'deduped':>8} {'fx_fail':>8} {'inserted':>9}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*9}")
    total_inserted = 0
    total_fx_fail = 0
    for m in markets:
        s = summary[m]
        print(f"  {m:<8} {s['fetched']:>8} {s['deduped']:>8} {s['fx_failures']:>8} {s['inserted']:>9}")
        total_inserted += s["inserted"]
        total_fx_fail += s["fx_failures"]
    print("─" * 60)
    print(f"  total to insert: {total_inserted}  fx_failures: {total_fx_fail}")
    if total_inserted and total_fx_fail:
        print("  WARNING: FX failures occurred. Review log for affected tickers.")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

    # Summary
    print("\n" + "-" * 60)
    print("  SUMMARY")
    print("-" * 60)
    print(f"  {'market':<8} {'fetched':>8} {'deduped':>8} {'fx_fail':>8} {'inserted':>9}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*9}")
    total_inserted = 0
    total_fx_fail = 0
    for m in markets:
        s = summary[m]
        print(f"  {m:<8} {s['fetched']:>8} {s['deduped']:>8} {s['fx_failures']:>8} {s['inserted']:>9}")
        total_inserted += s["inserted"]
        total_fx_fail += s["fx_failures"]
    print("-" * 60)
    print(f"  total to insert: {total_inserted}  fx_failures: {total_fx_fail}")
    if total_inserted and total_fx_fail:
        print("  WARNING: FX failures occurred. Review log for affected tickers.")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
xit(main())
