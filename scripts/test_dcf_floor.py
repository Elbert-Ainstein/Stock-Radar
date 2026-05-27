#!/usr/bin/env python3
"""test_dcf_floor.py — V1 validation harness for the --dcf-as-floor flag (C1 cycle).

Calls `target_engine.build_target` directly with the `dcf_role` parameter and
prints the resulting scenario prices, multiples, and (when role=downside_floor)
the Gordon-derived floor reference.

Usage:
    python scripts/test_dcf_floor.py LITE
    python scripts/test_dcf_floor.py LITE --dcf-as-floor
    python scripts/test_dcf_floor.py LITE CAMT COHR --dcf-as-floor

Why a dedicated script for V1:
- run_thesis.py is the LLM-thesis path and does NOT call build_target.
- analyst.py calls build_target but as part of a full batch over the watchlist
  — too heavy for the single-stock validation cycle defined in C1.5.
- verify_model.py uses sys.argv directly without argparse (ticker-as-positional),
  conflicting with a --dcf-as-floor flag.

After C1 validates that the math works, V2 wires the flag into the production
paths (analyst.py / model_export.py / target_api.py). V1 stays surgical.

Pass criterion for C1.5 (5 path-dependent checks per squad cycle iter 1):
    [1] target_high >= $580 (2x the pure-DCF $290-$350 figure from Socratic id=21)
    [2] dcf_role='downside_floor' on upside+base scenarios (rules out Gordon-fallback)
    [3] upside.dcf_floor_price is populated and > 0 (Gordon kept as floor reference)
    [4] floor < target_high (Gordon is lower bound, not driver)
    [5] target_high / floor >= 1.5x (the gap is meaningful, not coincidental)

A single-check pass (target_high >= $580 alone) is insufficient — it could be
met by coincidentally inflated exit multiples without proving the dcf_role
routing actually demoted Gordon. The 5-check criterion catches that case.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/test_dcf_floor.py` from repo root
sys.path.insert(0, str(Path(__file__).parent))

from finance_data import fetch_financials, EarningsFetchError
from target_engine import build_target


def run_one(ticker: str, dcf_role: str, archetype: str | None = None) -> int:
    """Run engine on one ticker, print scenario summary, return 0/1 (0=ok)."""
    arch_label = f", archetype={archetype}" if archetype else ""
    print(f"\n=== test_dcf_floor: {ticker} (dcf_role={dcf_role}{arch_label}) ===")

    try:
        fin = fetch_financials(ticker)
    except EarningsFetchError as e:
        print(f"  [fetch_fail] {e}")
        return 1

    try:
        t = build_target(fin, dcf_role=dcf_role, archetype=archetype)
    except Exception as e:
        print(f"  [engine_fail] {e}")
        return 1

    print(f"  spot:        ${t.current_price:>10.2f}")
    print(f"  target_low:  ${t.low:>10.2f}")
    print(f"  target_base: ${t.base:>10.2f}")
    print(f"  target_high: ${t.high:>10.2f}")
    print(f"  net_debt:    ${t.net_debt / 1e9:>10.2f}B")

    # Per-scenario detail
    for name in ("downside", "base", "upside"):
        if name not in t.scenarios:
            continue
        s = t.scenarios[name]
        print(f"\n  --- {name} scenario ---")
        print(f"    price:                  ${s.price:>10.2f}")
        print(f"    dcf_role:               {s.dcf_role}")
        print(f"    g1 / g_terminal:        {s.rev_growth_y1*100:>5.1f}% / {s.rev_growth_terminal*100:>5.1f}%")
        print(f"    ebitda_mt / fcf_mt:     {s.ebitda_margin_target*100:>5.1f}% / {s.fcf_sbc_margin_target*100:>5.1f}%")
        print(f"    ev_ebitda / ev_fcf mult: {s.ev_ebitda_multiple:>5.1f}x / {s.ev_fcf_sbc_multiple:>5.1f}x")
        print(f"    terminal_ev_blended:    ${s.terminal_ev_blended / 1e9:>10.2f}B")
        print(f"    ev_from_ebitda:         ${s.ev_from_ebitda / 1e9:>10.2f}B")
        print(f"    ev_from_fcf_sbc:        ${s.ev_from_fcf_sbc / 1e9:>10.2f}B")
        if s.dcf_floor_terminal_ev is not None:
            print(f"    dcf_floor_terminal_ev:  ${s.dcf_floor_terminal_ev / 1e9:>10.2f}B  ← Gordon (downside floor reference)")
            print(f"    dcf_floor_price:        ${s.dcf_floor_price:>10.2f}  ← what Gordon alone would imply")

    # 2026-05-26 — Critic finding #1: pass criterion was unfalsifiable as written
    # (target_high >= $580 could be met by coincidentally inflated exit multiples
    # without proving the routing logic is correct). The path-dependent version
    # requires: target_high meaningfully ABOVE Gordon-only floor. If the floor
    # is null or above target_high, the test fails — meaning Gordon either
    # didn't get demoted or the exit multiples produced a degenerate result.
    if ticker.upper() == "LITE" and dcf_role == "downside_floor":
        upside_s = t.scenarios.get("upside")
        base_s = t.scenarios.get("base")
        floor_ref = upside_s.dcf_floor_price if upside_s else None

        print(f"\n  PASS CRITERION (LITE / downside_floor mode):")
        check1 = t.high >= 580
        print(f"    [1] target_high ${t.high:.2f} >= $580 ........... {'✓' if check1 else '✗'}")

        check2 = (
            upside_s is not None
            and upside_s.dcf_role == "downside_floor"
            and base_s is not None
            and base_s.dcf_role == "downside_floor"
        )
        print(f"    [2] dcf_role='downside_floor' on upside+base .. {'✓' if check2 else '✗'}  (rules out Gordon-fallback)")

        check3 = floor_ref is not None and floor_ref > 0
        print(f"    [3] upside.dcf_floor_price populated .......... {'✓' if check3 else '✗'}  (Gordon kept as reference)")

        check4 = check3 and floor_ref < t.high
        print(f"    [4] floor < target_high ....................... {'✓' if check4 else '✗'}  (Gordon is lower bound, not driver)")

        check5 = check4 and (t.high / floor_ref) >= 1.5
        gap_ratio = (t.high / floor_ref) if check3 and floor_ref > 0 else 0
        print(f"    [5] target_high / floor >= 1.5x ............... {'✓' if check5 else '✗'}  (gap is meaningful, ratio={gap_ratio:.2f}x)")

        all_pass = check1 and check2 and check3 and check4 and check5
        print(f"    OVERALL: {'✓ PASS' if all_pass else '✗ FAIL'}")
        return 0 if all_pass else 1

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate DCF role contextual routing (C1 v1).")
    ap.add_argument("tickers", nargs="+", help="One or more tickers (e.g. LITE CAMT COHR)")
    ap.add_argument(
        "--dcf-as-floor",
        action="store_true",
        help=(
            "Force dcf_role='downside_floor' on every ticker for this run. "
            "Exit multiples drive terminal_ev; Gordon Growth kept as floor reference "
            "in scenario.dcf_floor_terminal_ev / scenario.dcf_floor_price. "
            "Use for regime-shift candidates where Gordon's <=4.5% perpetuity cap "
            "structurally undershoots (memory: user_dcf_is_wrong_primary 2026-05-01)."
        ),
    )
    ap.add_argument(
        "--archetype",
        default=None,
        help=(
            "Override the engine's archetype auto-promote heuristic for this run. "
            "Common values: 'garp', 'cyclical', 'transformational', 'compounder', "
            "'secular_growth', 'special_situation'. Pass when the heuristic "
            "mis-routes a regime-shift stock (memory: regime-shift-vs-historical-math 2026-05-26). "
            "Example: LITE auto-promotes to 'cyclical' from pre-2024 margin trajectory; "
            "pass --archetype=secular_growth to bypass and analyze with current-regime math."
        ),
    )
    args = ap.parse_args()

    dcf_role = "downside_floor" if args.dcf_as_floor else "primary"

    failures = 0
    for tk in args.tickers:
        failures += run_one(tk, dcf_role, archetype=args.archetype)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {len(args.tickers)} ticker(s), {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
