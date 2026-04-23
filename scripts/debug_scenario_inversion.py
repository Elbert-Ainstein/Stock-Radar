#!/usr/bin/env python3
"""Debug the BULL < BASE scenario inversion for LITE.

Traces drivers, forecast, and terminal value for each scenario side-by-side
to find exactly where upside produces a lower price than base.
"""
from __future__ import annotations
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_env
load_env()

from finance_data import fetch_financials
from target_engine import (
    build_target, _merge_drivers, _apply_scenario, _scenario_price,
    _forecast_annual, _should_use_revenue_multiple, _ttm_fcf_sbc,
    _annual_label_from_q, _discount_years_for_horizon,
    SCENARIO_OFFSETS, VALUATION_YEAR, DISCOUNT_YEARS,
)

TICKER = "LITE"

def main():
    print(f"\n{'='*80}")
    print(f"  SCENARIO INVERSION DEBUG — {TICKER}")
    print(f"{'='*80}\n")

    fin = fetch_financials(TICKER)
    print(f"TTM Revenue:  ${fin.ttm_revenue()/1e9:.3f}B")
    print(f"TTM EBITDA:   ${(fin.ttm_ebitda() or 0)/1e9:.3f}B")
    print(f"TTM FCF-SBC:  ${(_ttm_fcf_sbc(fin) or 0)/1e9:.3f}B")
    print(f"Market Cap:   ${(fin.market_cap or 0)/1e9:.3f}B")
    print(f"Net Debt:     ${(fin.net_debt or 0)/1e9:.3f}B")
    print(f"Shares:       {(fin.shares_diluted or 0)/1e6:.1f}M")

    # Load forward drivers
    try:
        from forward_drivers import load_forward_drivers
        ttm_rev = fin.ttm_revenue() or 0.0
        prior_year_q = None
        q = fin.quarterly_income or []
        if len(q) >= 5:
            v = q[-5].get("Total Revenue")
            if isinstance(v, (int, float)) and v > 0:
                prior_year_q = float(v)
        forward = load_forward_drivers(TICKER, ttm_rev=ttm_rev, prior_year_q_rev=prior_year_q)
    except Exception as e:
        print(f"Forward drivers failed: {e}")
        forward = None

    base_drivers = _merge_drivers(None, fin, forward=forward)
    base_drivers.pop("_smart_defaults_failed", None)
    base_drivers.pop("_tam_bound_applied", None)

    use_rev = _should_use_revenue_multiple(fin, forward=forward, base_drivers=base_drivers)
    print(f"\nUse revenue multiple (P/S)? {use_rev}")

    base_year_label = _annual_label_from_q(fin.latest_quarter_label() or "")
    discount_years = DISCOUNT_YEARS

    print(f"\n{'─'*80}")
    print("  BASE DRIVERS (before scenario offsets)")
    print(f"{'─'*80}")
    key_drivers = [
        "rev_growth_y1", "rev_growth_terminal", "ebitda_margin_target",
        "fcf_sbc_margin_target", "ev_ebitda_multiple", "ev_fcf_sbc_multiple",
        "discount_rate", "share_change_pct", "sbc_pct_rev", "da_pct_rev", "tax_rate",
    ]
    for k in key_drivers:
        v = base_drivers.get(k)
        if v is not None:
            if "margin" in k or "growth" in k or "pct" in k or "rate" in k:
                print(f"  {k:30s} = {v:.4f} ({v*100:.2f}%)")
            else:
                print(f"  {k:30s} = {v:.2f}")

    # Run each scenario and trace
    for scenario in ("downside", "base", "upside"):
        d = _apply_scenario(base_drivers, scenario)
        print(f"\n{'='*80}")
        print(f"  SCENARIO: {scenario.upper()}")
        print(f"{'='*80}")
        print(f"\n  Applied drivers:")
        for k in key_drivers:
            v = d.get(k)
            if v is not None:
                base_v = base_drivers.get(k, 0)
                diff = ""
                if k in ("ev_ebitda_multiple", "ev_fcf_sbc_multiple"):
                    if base_v != 0:
                        diff = f" (×{v/base_v:.3f})"
                elif "margin" in k or "growth" in k or "pct" in k or "rate" in k:
                    diff = f" (delta {(v-base_v)*100:+.2f}pp)"
                if "margin" in k or "growth" in k or "pct" in k or "rate" in k:
                    print(f"    {k:30s} = {v:.4f} ({v*100:.2f}%){diff}")
                else:
                    print(f"    {k:30s} = {v:.2f}{diff}")

        # Forecast
        annual = _forecast_annual(fin, d, base_year_label)
        print(f"\n  Forecast:")
        print(f"    {'Year':<8} {'Revenue':>12} {'EBITDA':>12} {'EBITDA%':>8} {'FCF-SBC':>12} {'FCF%':>8} {'Growth':>8}")
        for p in annual:
            print(f"    {p.period:<8} ${p.revenue/1e9:>10.3f}B ${p.ebitda/1e9:>10.3f}B {p.ebitda_margin:>7.1%} ${p.fcf_sbc/1e9:>10.3f}B {p.fcf_sbc_margin:>7.1%} {p.rev_growth:>7.1%}")

        # Terminal value
        terminal = annual[VALUATION_YEAR - 1]
        ev_from_ebitda = terminal.ebitda * d["ev_ebitda_multiple"]
        ev_from_fcf = terminal.fcf_sbc * d["ev_fcf_sbc_multiple"]

        print(f"\n  Terminal (Y{VALUATION_YEAR}):")
        print(f"    EBITDA Y{VALUATION_YEAR}:      ${terminal.ebitda/1e9:.3f}B")
        print(f"    FCF-SBC Y{VALUATION_YEAR}:     ${terminal.fcf_sbc/1e9:.3f}B")
        print(f"    EV/EBITDA mult:   {d['ev_ebitda_multiple']:.2f}x")
        print(f"    EV/FCF-SBC mult:  {d['ev_fcf_sbc_multiple']:.2f}x")
        print(f"    EV from EBITDA:   ${ev_from_ebitda/1e9:.3f}B")
        print(f"    EV from FCF-SBC:  ${ev_from_fcf/1e9:.3f}B")

        if ev_from_ebitda > 0 and ev_from_fcf <= 0:
            terminal_ev = ev_from_ebitda
            blend_note = "EBITDA-only (FCF leg negative)"
        elif ev_from_fcf > 0 and ev_from_ebitda <= 0:
            terminal_ev = ev_from_fcf
            blend_note = "FCF-only (EBITDA leg negative)"
        else:
            terminal_ev = (ev_from_ebitda + ev_from_fcf) / 2
            blend_note = "50/50 blend"

        discount = (1 + d["discount_rate"]) ** discount_years
        pv_ev = terminal_ev / discount
        net_debt = fin.net_debt or 0.0
        equity = pv_ev - net_debt
        shares_0 = fin.shares_diluted or 0.0
        shares_t = shares_0 * (1 + d["share_change_pct"]) ** (VALUATION_YEAR - discount_years)

        price = max(0.0, equity / shares_t) if shares_t > 0 else 0.0

        print(f"    Blend:            ${terminal_ev/1e9:.3f}B ({blend_note})")
        print(f"    Discount ({discount_years}yr):  ÷{discount:.4f}")
        print(f"    PV(EV):           ${pv_ev/1e9:.3f}B")
        print(f"    Net debt:         ${net_debt/1e9:.3f}B")
        print(f"    Equity:           ${equity/1e9:.3f}B")
        print(f"    Shares (diluted): {shares_t/1e6:.1f}M")
        print(f"    ──────────────────────────────")
        print(f"    PRICE:            ${price:.2f}")

    # Also run the full engine to confirm
    print(f"\n{'='*80}")
    print("  FULL ENGINE OUTPUT")
    print(f"{'='*80}")
    result = build_target(fin, forward=forward)
    print(f"  Bear:  ${result.low:.2f}")
    print(f"  Base:  ${result.base:.2f}")
    print(f"  Bull:  ${result.high:.2f}")
    for name in ("downside", "base", "upside"):
        s = result.scenarios[name]
        print(f"  {name:>8}: ${s.price:.2f}  (EV/EBITDA={s.ev_ebitda_multiple:.2f}x, EV/FCF={s.ev_fcf_sbc_multiple:.2f}x)")


if __name__ == "__main__":
    main()
