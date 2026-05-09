#!/usr/bin/env python3
"""
capture_engine_fixtures.py - Regenerate scripts/test_engine_fixtures.json.

Run when an engine change is INTENTIONAL and you've reviewed the diff in the
fixture JSON before committing.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from utils import load_env  # noqa: E402

load_env()

from finance_data import fetch_financials  # noqa: E402
from target_engine import build_target  # noqa: E402
from backtest_targets import close_at_or_before, load_price_history  # noqa: E402


# (name, ticker, as_of, archetype, expected_method, tolerance_pct, note)
FIXTURES = [
    ("LITE_cyclical_trough",         "LITE", "2024-05-15", "cyclical",          None,        25.0, "deep cyclical trough"),
    ("LITE_cyclical_peak",           "LITE", "2022-02-15", "cyclical",          None,        20.0, "AI-optical peak"),
    ("ASML_compounder_guidance_cut", "ASML", "2024-08-15", "compounder",        None,        20.0, "Q3 2024 guidance cut"),
    ("ASML_compounder_bull",         "ASML", "2021-05-15", "compounder",        None,        20.0, "post-COVID semi supercycle"),
    ("ASML_compounder_mid_cycle",    "ASML", "2023-05-15", "compounder",        None,        20.0, "mid-cycle stable"),
    ("MRVL_regime_transition",       "MRVL", None,         None,                "ev_ebitda", 50.0, "post-Inphi; must NOT auto-promote (live)"),
    ("AMD_garp",                     "AMD",  "2023-02-15", "garp",              None,        20.0, "GARP, AI-cycle inflection"),
    ("FSLY_pre_profit_ps",           "FSLY", "2022-02-15", None,                None,        25.0, "pre-profit, P/S routing"),
    ("TSLA_transformational",        "TSLA", "2020-08-15", "transformational",  None,        25.0, "transformational tilts + 25% Gordon floor"),
    ("GE_special_situation",         "GE",   "2024-08-15", "special_situation", None,        30.0, "post-spin GE Aerospace"),
]


def capture_one(name, ticker, as_of_str, archetype, expected_method, tolerance_pct, note):
    print("")
    print("=== " + name + " ===", flush=True)
    print("  ticker=" + ticker + " as_of=" + str(as_of_str) + " archetype=" + str(archetype), flush=True)

    spot = None
    as_of_dt = None
    if as_of_str:
        as_of_dt = datetime.fromisoformat(as_of_str).replace(tzinfo=timezone.utc)
        prices = load_price_history(
            ticker,
            as_of_dt - timedelta(days=30),
            as_of_dt + timedelta(days=10),
        )
        tup = close_at_or_before(prices, as_of_dt)
        if tup is None:
            return {"name": name, "error": "no spot price within 7 days"}
        spot = tup[1]
        print("  spot={:.2f} on {}".format(spot, tup[0].date()), flush=True)

    fin = fetch_financials(ticker, as_of=as_of_dt)
    if as_of_dt is not None and spot is not None:
        fin.price = spot
        if fin.shares_diluted:
            fin.market_cap = spot * fin.shares_diluted

    result = build_target(
        fin,
        drivers=None,
        forward=None,
        load_forward=False,
        horizon_months=12,
        archetype=archetype,
    )

    ttm_rev = fin.ttm_revenue() or 0.0
    ttm_ebitda = fin.ttm_ebitda() or 0.0

    out = {
        "name": name,
        "ticker": ticker,
        "as_of": as_of_str,
        "archetype": archetype,
        "expected_method": expected_method,
        "tolerance_pct": tolerance_pct,
        "spot": spot if spot else fin.price,
        "method": result.valuation_method,
        "low": result.low,
        "base": result.base,
        "high": result.high,
        "pinned_data": {
            "ttm_revenue": ttm_rev,
            "ttm_ebitda": ttm_ebitda,
        },
        "note": note,
    }
    print(
        "  method={} low={:.2f} base={:.2f} high={:.2f} ttm_rev={:.2f}B ttm_ebitda={:.2f}B".format(
            out["method"], out["low"], out["base"], out["high"], ttm_rev / 1e9, ttm_ebitda / 1e9
        ),
        flush=True,
    )
    return out


def main():
    results = []
    errors = []
    for spec in FIXTURES:
        try:
            r = capture_one(*spec)
        except Exception as e:
            r = {"name": spec[0], "error": "unhandled: {}: {}".format(type(e).__name__, e)}
        if "error" in r:
            errors.append(r)
        results.append(r)

    out_path = HERE / "test_engine_fixtures.json"
    payload = {
        "_meta": {
            "captured_at": datetime.now().isoformat(),
            "purpose": (
                "Regression fixture: low/base/high tolerance bands + method-equality + "
                "TTM data-layer canary. Updated only when an engine change is intentional."
            ),
            "tolerance_pct": 50.0,
            "skip_floor": 2,
            "method_must_match_when_set": True,
        },
        "fixtures": results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print("")
    print("Wrote " + str(out_path), flush=True)

    if errors:
        print("")
        print("[!] {} fixture(s) errored:".format(len(errors)), flush=True)
        for e in errors:
            print("  - " + e["name"] + ": " + e["error"], flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
