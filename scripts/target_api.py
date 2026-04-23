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
from target_engine import (
    build_target, DEFAULT_DRIVERS, DRIVER_META, DEFAULT_SLIDER_KEYS,
    CYCLICAL_DRIVERS, CYCLICAL_DRIVER_META, CYCLICAL_SLIDER_KEYS,
)


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


def _load_stock_from_db(ticker: str) -> dict:
    """Load archetype, model_defaults, valuation_method, and scenarios from Supabase.

    Returns a dict with keys: archetype, model_defaults, valuation_method, scenarios.
    All values may be None if DB is unreachable.
    """
    result = {"archetype": None, "model_defaults": None, "valuation_method": None, "scenarios": None}
    try:
        from supabase_helper import get_client
        sb = get_client()
        resp = (
            sb.table("stocks")
            .select("archetype, model_defaults, valuation_method, scenarios")
            .eq("ticker", ticker.upper())
            .maybe_single()
            .execute()
        )
        if resp.data:
            result["archetype"] = resp.data.get("archetype")
            result["model_defaults"] = resp.data.get("model_defaults")
            result["valuation_method"] = resp.data.get("valuation_method")
            result["scenarios"] = resp.data.get("scenarios")
    except Exception as e:
        print(f"  [target_api] DB load failed for {ticker}: {e}", file=__import__("sys").stderr)
    return result


def _analyst_to_driver_overrides(model_defaults: dict, valuation_method: str | None) -> dict[str, float]:
    """Convert analyst model_defaults into engine-compatible driver overrides.

    The analyst's model_defaults contain forward-looking assumptions (target revenue,
    target margin, target multiple) that should take priority over raw TTM data when
    the engine's forward_drivers are unavailable.
    """
    overrides: dict[str, float] = {}
    if not model_defaults:
        return overrides

    vm = model_defaults.get("valuation_method") or valuation_method or "pe"
    rev_b = model_defaults.get("revenue_b", 0)
    op_margin = model_defaults.get("op_margin", 0)
    tax_rate = model_defaults.get("tax_rate")
    pe = model_defaults.get("pe_multiple")
    ps = model_defaults.get("ps_multiple")

    if op_margin and op_margin > 0:
        overrides["ebitda_margin_target"] = min(op_margin + 0.05, 0.95)

    if tax_rate and tax_rate > 0:
        overrides["tax_rate"] = tax_rate

    if vm == "pe" and pe and pe > 0:
        overrides["ev_ebitda_multiple"] = max(8, pe * 0.6)
    elif vm == "ps" and ps and ps > 0:
        overrides["ev_ebitda_multiple"] = max(8, ps * 0.8)

    return overrides


def payload_for(
    ticker: str,
    overrides: dict[str, float] | None = None,
    horizon_months: int = 12,
    archetype: str | None = None,
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

    # Load analyst data from Supabase (archetype, model_defaults, scenarios)
    db_data = _load_stock_from_db(ticker)

    # Resolve archetype: explicit param > Supabase > None
    archetype_data: dict | None = None
    if archetype:
        archetype_data = {"primary": archetype, "secondary": None, "justification": "CLI override"}
    elif db_data["archetype"]:
        archetype_data = db_data["archetype"]

    arch_primary = (archetype_data or {}).get("primary") if isinstance(archetype_data, dict) else None

    # Build driver overrides: analyst defaults (low priority) + user overrides (high priority)
    merged_overrides = {}
    if db_data["model_defaults"]:
        analyst_ovr = _analyst_to_driver_overrides(db_data["model_defaults"], db_data["valuation_method"])
        if analyst_ovr:
            print(f"  [target_api] Using analyst fallback drivers for {ticker}: {analyst_ovr}", file=__import__("sys").stderr)
            merged_overrides.update(analyst_ovr)
    # User overrides take priority
    if overrides:
        merged_overrides.update(overrides)

    try:
        t = build_target(fin, merged_overrides or {}, horizon_months=horizon_months, archetype=arch_primary)
    except Exception as e:
        return {"ticker": ticker, "error": f"target engine failed: {e}"}

    # Attach analyst scenario prices so dashboard can show them as fallback
    if db_data["scenarios"]:
        analyst_scenarios = db_data["scenarios"]

    # Enrich with slider metadata so the frontend can render sliders without
    # hardcoding ranges. Use cyclical-specific sliders when in cyclical mode.
    is_cyclical = t.valuation_method == "cyclical_normalized"
    slider_keys = CYCLICAL_SLIDER_KEYS if is_cyclical else DEFAULT_SLIDER_KEYS
    all_meta = {**DRIVER_META, **CYCLICAL_DRIVER_META} if is_cyclical else DRIVER_META
    all_defaults = {**DEFAULT_DRIVERS, **CYCLICAL_DRIVERS} if is_cyclical else DEFAULT_DRIVERS
    sliders = []
    for k in slider_keys:
        meta = dict(all_meta.get(k, {}))
        meta["key"] = k
        meta["value"] = t.drivers.get(k, all_defaults.get(k, 0))
        meta["default"] = all_defaults.get(k, 0)
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
        "archetype": archetype_data,
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
        "analyst_scenarios": db_data.get("scenarios"),
        "analyst_model_defaults": db_data.get("model_defaults"),
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
    arch_override = None
    for a in args[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            k = k.strip()
            if k == "horizon_months":
                try:
                    horizon_months = int(float(v))
                except ValueError:
                    pass
                continue
            if k == "archetype":
                arch_override = v.strip()
                continue
            try:
                overrides[k] = float(v)
            except ValueError:
                pass

    p = payload_for(ticker, overrides, horizon_months=horizon_months, archetype=arch_override)
    print(json.dumps(p, indent=2, default=str))


if __name__ == "__main__":
    main()
