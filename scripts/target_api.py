#!/usr/bin/env python3
"""
target_api.py — JSON output for the Next.js brief/detailed dashboard views.

Usage:
    # Base case for a single ticker
    python target_api.py LITE
    # With driver overrides (slider changes)
    python target_api.py LITE rev_growth_y1=0.25 ev_ebitda_multiple=22
    # Batch: write JSON for every watchlist ticker
    python target_api.py --batch

Output is a single JSON document on stdout (one-line for batch; pretty single).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from finance_data import fetch_financials, EarningsFetchError
from target_engine import build_target, DEFAULT_DRIVERS, DRIVER_META, DEFAULT_SLIDER_KEYS


# Hardcoded fallback — used only when Supabase is unreachable.
# Prefer get_watchlist() which reads the live DB (see --batch handler).
_FALLBACK_WATCHLIST = ["LITE", "MRVL", "MU", "APP", "NVDA", "SNDK", "TER", "AMD", "RKLB", "ACHR", "AAPL"]


def _get_batch_tickers() -> list[str]:
    """Return the live watchlist from Supabase, falling back to hardcoded list."""
    try:
        from utils import load_env, get_watchlist
        load_env()
        wl = get_watchlist()
        tickers = [w["ticker"] for w in wl if w.get("ticker")]
        if tickers:
            return tickers
    except Exception:
        pass
    return _FALLBACK_WATCHLIST


def payload_for(
    ticker: str,
    overrides: dict[str, float] | None = None,
    horizon_months: int = 12,
) -> dict:
    """Build the full JSON payload for one ticker. Returns {'error': ...} on failure."""
    try:
        fin = fetch_financials(ticker)
    except EarningsFetchError as e:
        return {
            "ticker": ticker,
            "error": str(e),
            "hint": "This ticker has insufficient earnings history — no model can be built.",
        }

    try:
        t = build_target(fin, overrides or {}, horizon_months=horizon_months)
    except Exception as e:
        return {"ticker": ticker, "error": f"target engine failed: {e}"}

    # Enrich with slider metadata so the frontend can render sliders without
    # hardcoding ranges
    sliders = []
    for k in DEFAULT_SLIDER_KEYS:
        meta = dict(DRIVER_META.get(k, {}))
        meta["key"] = k
        meta["value"] = t.drivers.get(k, DEFAULT_DRIVERS[k])
        meta["default"] = DEFAULT_DRIVERS[k]
        sliders.append(meta)

    # Historical context for detailed page
    hist_quarterly = [
        {
            "period": p["period"],
            "date": p["date"],
            "revenue": p.get("Total Revenue"),
            "operating_income": p.get("Operating Income"),
            "net_income": p.get("Net Income"),
        }
        for p in fin.quarterly_income[-6:]
    ]
    hist_annual = [
        {
            "period": p["period"],
            "date": p["date"],
            "revenue": p.get("Total Revenue"),
            "operating_income": p.get("Operating Income"),
            "net_income": p.get("Net Income"),
        }
        for p in fin.annual_income[-5:]
    ]

    return {
        "ticker": fin.ticker,
        "name": fin.name,
        "sector": fin.sector,
        "currency": fin.currency,
        "source": fin.source,
        "fetched_at": fin.fetched_at,
        "target": t.to_dict(),
        "sliders": sliders,
        "all_drivers": {
            k: {**DRIVER_META.get(k, {}), "key": k, "value": t.drivers.get(k, v), "default": v}
            for k, v in DEFAULT_DRIVERS.items()
        },
        "historicals": {
            "quarterly": hist_quarterly,
            "annual": hist_annual,
            "ttm": {
                "revenue": fin.ttm_revenue(),
                "operating_income": fin.ttm_operating_income(),
                "ebitda": fin.ttm_ebitda(),
                "fcf": fin.ttm_fcf(),
            },
        },
        "capitalization": {
            "price": fin.price,
            "market_cap": fin.market_cap,
            "shares_diluted": fin.shares_diluted,
            "net_debt": fin.net_debt,
        },
        "warnings": fin.warnings + t.warnings,
    }


def main():
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"error": "provide a ticker, or --batch"}))
        sys.exit(1)

    if args[0] == "--batch":
        out_dir = Path(args[1]) if len(args) > 1 else Path(
            Path(__file__).resolve().parent.parent / "out" / "targets"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = []
        for tk in _get_batch_tickers():
            p = payload_for(tk)
            fp = out_dir / f"{tk}.json"
            fp.write_text(json.dumps(p, indent=2, default=str))
            if "error" in p:
                summary.append({"ticker": tk, "status": "error", "error": p["error"]})
            else:
                tgt = p["target"]
                summary.append({
                    "ticker": tk,
                    "status": "ok",
                    "current": round(tgt["current_price"], 2),
                    "low": round(tgt["low"], 2),
                    "base": round(tgt["base"], 2),
                    "high": round(tgt["high"], 2),
                    "upside_base_pct": round(tgt["upside_base_pct"], 3),
                })
        (out_dir / "_summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
        return

    ticker = args[0].upper()
    overrides: dict[str, float] = {}
    horizon_months = 12
    for a in args[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            k = k.strip()
            # Horizon is a special non-driver arg: `horizon_months=24`
            if k == "horizon_months":
                try:
                    horizon_months = int(float(v))
                except ValueError:
                    pass
                continue
            try:
                overrides[k] = float(v)
            except ValueError:
                pass

    p = payload_for(ticker, overrides, horizon_months=horizon_months)
    print(json.dumps(p, indent=2, default=str))


if __name__ == "__main__":
    main()
