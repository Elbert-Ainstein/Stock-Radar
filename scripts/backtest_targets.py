#!/usr/bin/env python3
"""
backtest_targets.py — Point-in-time backtest of the target-price engine.

Walks a quarterly grid of as-of dates. At each date:
  1. Fetches financials filtered to as_of (filing-lag enforced)
  2. Injects historical adjusted-close price as the spot
  3. Runs build_target with forward drivers DISABLED
  4. Compares engine target to actual price 12 months later

Outputs CSV + summary metrics: directional hit rate, mean absolute error,
bull-capture rate, error vs growth phase.

Look-ahead bias is prevented at three layers:
  • finance_data.fetch_financials(as_of=...) drops periods filed after as_of
  • build_target(forward=None, load_forward=False) skips Supabase signals
  • Spot price is injected from yfinance historical (not a live quote)

Known policy biases (NOT date-aware in v1, documented):
  • Sector multiples (config/sector_stats.json — current values)
  • RISK_FREE_RATE / EQUITY_RISK_PREMIUM (Apr 2026 calibration)
  • TERMINAL_GROWTH_CAP (current)
  • Sector betas (current)

Usage:
    python backtest_targets.py --ticker LITE --start 2018 --end 2024
    python backtest_targets.py --ticker LITE --output ../data/backtest_LITE.csv
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# Add scripts/ to path for sibling imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import load_env  # noqa: E402

load_env()

from finance_data import fetch_financials, EarningsFetchError  # noqa: E402
from target_engine import build_target  # noqa: E402


# ─── Quarterly grid ──────────────────────────────────────────────────

# Mid-month dates spaced ~quarterly. Choosing the 15th of Feb/May/Aug/Nov
# means we are ~45 days past the previous quarter-end — typically enough
# for the prior 10-Q to be filed under the conservative 60-day filter,
# while still avoiding the immediate post-earnings noise.
QUARTERLY_OFFSETS = [
    (2, 15),   # mid-Feb (sees prior FY annual + Q3 quarterly)
    (5, 15),   # mid-May (sees Q1)
    (8, 15),   # mid-Aug (sees Q2)
    (11, 15),  # mid-Nov (sees Q3)
]


def quarterly_as_of_dates(start_year: int, end_year: int) -> list[datetime]:
    out = []
    for y in range(start_year, end_year + 1):
        for m, d in QUARTERLY_OFFSETS:
            out.append(datetime(y, m, d, tzinfo=timezone.utc))
    return out


# ─── Historical price loader ─────────────────────────────────────────

def load_price_history(ticker: str, start: datetime, end: datetime):
    """Load adjusted close prices via yfinance.

    Returns a sorted list of (date, close) tuples. yfinance gives only
    trading days; weekends/holidays produce gaps.
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError("yfinance required: pip install yfinance --break-system-packages") from e

    df = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True,  # adjust for splits & dividends
    )
    if df.empty:
        raise RuntimeError(f"No price history for {ticker} between {start.date()} and {end.date()}")

    # Flatten MultiIndex if present
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.get_level_values(0)

    out = []
    for ts, row in df["Close"].items():
        if isinstance(row, float) and not math.isnan(row):
            out.append((ts.to_pydatetime().replace(tzinfo=timezone.utc), float(row)))
    return out


def close_at_or_before(prices: list[tuple[datetime, float]], target: datetime, max_gap_days: int = 7):
    """Get the most recent close on or before target. Returns None if no price within max_gap."""
    cutoff = target - timedelta(days=max_gap_days)
    best = None
    for ts, px in prices:
        if ts <= target and ts >= cutoff:
            best = (ts, px)
        elif ts > target:
            break
    return best  # (timestamp, price) or None


# ─── Result schema ───────────────────────────────────────────────────

@dataclass
class BacktestRow:
    ticker: str
    as_of: str           # ISO date
    spot_price: float | None
    target_base: float | None
    target_low: float | None
    target_high: float | None
    valuation_method: str
    actual_price_12m: float | None
    actual_date_12m: str | None
    return_12m_pct: float | None       # spot → actual_12m
    target_return_implied_pct: float | None  # spot → target_base
    error_pct: float | None            # (actual_12m − target_base) / target_base
    abs_error_pct: float | None
    directional_hit: bool | None       # did target & actual agree on up/down?
    bull_capture_pct: float | None     # (actual − base) / (high − base) if actual > base
    n_quarters_visible: int
    n_annuals_visible: int
    error_msg: str = ""


def run_one(ticker: str, as_of: datetime, prices: list[tuple[datetime, float]], archetype: str | None = None) -> BacktestRow:
    """Run a single backtest sample at as_of."""
    row = BacktestRow(
        ticker=ticker,
        as_of=as_of.strftime("%Y-%m-%d"),
        spot_price=None, target_base=None, target_low=None, target_high=None,
        valuation_method="",
        actual_price_12m=None, actual_date_12m=None,
        return_12m_pct=None, target_return_implied_pct=None,
        error_pct=None, abs_error_pct=None,
        directional_hit=None, bull_capture_pct=None,
        n_quarters_visible=0, n_annuals_visible=0,
    )

    # --- spot price ---
    spot = close_at_or_before(prices, as_of)
    if spot is None:
        row.error_msg = "no spot price"
        return row
    row.spot_price = spot[1]

    # --- forward price (12 months later) ---
    fwd_target = as_of + timedelta(days=365)
    fwd = close_at_or_before(prices, fwd_target, max_gap_days=14)
    if fwd is not None:
        row.actual_price_12m = fwd[1]
        row.actual_date_12m = fwd[0].strftime("%Y-%m-%d")
        row.return_12m_pct = (fwd[1] - spot[1]) / spot[1] * 100

    # --- fetch financials at as_of ---
    try:
        fin = fetch_financials(ticker, as_of=as_of)
    except EarningsFetchError as e:
        row.error_msg = f"fetch fail: {str(e)[:80]}"
        return row

    row.n_quarters_visible = len(fin.quarterly_income)
    row.n_annuals_visible = len(fin.annual_income)
    if row.n_quarters_visible < 4 and row.n_annuals_visible < 2:
        row.error_msg = f"insufficient history ({row.n_quarters_visible}q / {row.n_annuals_visible}y)"
        return row

    # --- inject historical price/market_cap ---
    fin.price = spot[1]
    if fin.shares_diluted:
        fin.market_cap = spot[1] * fin.shares_diluted

    # --- run engine, forward drivers OFF ---
    try:
        result = build_target(
            fin,
            drivers=None,
            forward=None,
            load_forward=False,
            horizon_months=12,
            archetype=archetype,
        )
    except Exception as e:
        row.error_msg = f"engine fail: {str(e)[:80]}"
        return row

    row.target_base = result.base
    row.target_low = result.low
    row.target_high = result.high
    row.valuation_method = result.valuation_method
    row.target_return_implied_pct = (result.base - spot[1]) / spot[1] * 100 if spot[1] else None

    if row.actual_price_12m is not None and result.base:
        row.error_pct = (row.actual_price_12m - result.base) / result.base * 100
        row.abs_error_pct = abs(row.error_pct)
        target_says_up = result.base > spot[1]
        actual_went_up = row.actual_price_12m > spot[1]
        row.directional_hit = (target_says_up == actual_went_up)
        # Bull-capture: did the high case anticipate the upside?
        if row.actual_price_12m > result.base and result.high > result.base:
            row.bull_capture_pct = min(
                100.0,
                (row.actual_price_12m - result.base) / (result.high - result.base) * 100,
            )
        elif row.actual_price_12m < result.base and result.low < result.base:
            row.bull_capture_pct = -min(
                100.0,
                (result.base - row.actual_price_12m) / (result.base - result.low) * 100,
            )

    return row


# ─── Aggregation ─────────────────────────────────────────────────────

def summarize(rows: list[BacktestRow]) -> dict:
    valid = [r for r in rows if r.target_base is not None and r.actual_price_12m is not None]
    if not valid:
        return {"n_valid": 0}

    errs = [r.error_pct for r in valid if r.error_pct is not None]
    abs_errs = [r.abs_error_pct for r in valid if r.abs_error_pct is not None]
    hits = [r for r in valid if r.directional_hit is not None]

    return {
        "n_total": len(rows),
        "n_valid": len(valid),
        "n_failed": len(rows) - len(valid),
        "directional_hit_rate_pct": (
            sum(1 for r in hits if r.directional_hit) / len(hits) * 100 if hits else None
        ),
        "mean_error_pct": sum(errs) / len(errs) if errs else None,
        "median_error_pct": sorted(errs)[len(errs) // 2] if errs else None,
        "mean_abs_error_pct": sum(abs_errs) / len(abs_errs) if abs_errs else None,
        "rmse_pct": math.sqrt(sum(e * e for e in errs) / len(errs)) if errs else None,
        "n_undershoot": sum(1 for e in errs if e > 0),  # actual > target (engine too low)
        "n_overshoot": sum(1 for e in errs if e < 0),   # actual < target (engine too high)
        "pct_undershoot": sum(1 for e in errs if e > 0) / len(errs) * 100 if errs else None,
    }


def write_csv(rows: list[BacktestRow], path: str) -> None:
    fields = list(BacktestRow.__dataclass_fields__.keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))


# ─── CLI ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Point-in-time backtest of target engine")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g. LITE)")
    parser.add_argument("--start", type=int, default=2018, help="Start year (inclusive)")
    parser.add_argument("--end", type=int, default=2024, help="End year (inclusive)")
    parser.add_argument("--output", default=None, help="CSV output path")
    parser.add_argument("--archetype", default=None,
                        choices=[None, "garp", "cyclical", "transformational", "compounder", "special_situation"],
                        help="Force archetype passed to build_target (default None = engine's own routing)")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    suffix = f"_arch-{args.archetype}" if args.archetype else ""
    output = args.output or os.path.join(
        os.path.dirname(__file__), "..", "data", f"backtest_{ticker}{suffix}.csv"
    )

    print(f"Backtest: {ticker} {args.start}–{args.end}")
    print(f"  Output: {output}")

    # Pre-load all prices once (cheaper than per-quarter calls)
    print(f"  Loading price history...")
    px_start = datetime(args.start - 1, 1, 1, tzinfo=timezone.utc)
    px_end = datetime(args.end + 2, 1, 1, tzinfo=timezone.utc)
    prices = load_price_history(ticker, px_start, px_end)
    print(f"  Got {len(prices)} trading days "
          f"({prices[0][0].date()} to {prices[-1][0].date()})")

    # Run backtest at each quarterly as-of
    dates = quarterly_as_of_dates(args.start, args.end)
    rows: list[BacktestRow] = []
    for i, as_of in enumerate(dates, 1):
        print(f"  [{i}/{len(dates)}] {as_of.date()} ...", end=" ", flush=True)
        row = run_one(ticker, as_of, prices, archetype=args.archetype)
        rows.append(row)
        if row.error_msg:
            print(f"SKIP ({row.error_msg})")
        elif row.target_base is None:
            print("no target")
        else:
            ret = f"{row.return_12m_pct:+.0f}%" if row.return_12m_pct is not None else "n/a"
            err = f"{row.error_pct:+.0f}%" if row.error_pct is not None else "n/a"
            print(
                f"spot=${row.spot_price:.0f}  target=${row.target_base:.0f}  "
                f"actual_12m={ret}  err={err}  [{row.valuation_method}]"
            )

    # Write CSV
    os.makedirs(os.path.dirname(output), exist_ok=True)
    write_csv(rows, output)
    print(f"\nWrote {len(rows)} rows to {output}")

    # Summary
    summary = summarize(rows)
    print("\n── Summary ──")
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"  {k:30s} {v:.2f}")
        else:
            print(f"  {k:30s} {v}")


if __name__ == "__main__":
    main()
