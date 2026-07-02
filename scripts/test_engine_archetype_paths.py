"""Offline regression tests for the paths the suite was blind to (audit 2026-07-02):

1. Archetype valuation-year vs discount-year consistency in _scenario_price —
   the old code took the terminal at the archetype's val_year (compounder/
   cyclical Y5, transformational Y4) but discounted by the Y3-based
   discount_years, letting 1-2 years of growth accrue undiscounted
   (~+19.5% measured on a stub at a 9.3% WACC; line 1622 was a tautology).

2. P/S mode net-debt handling in _scenario_price_revenue_multiple — terminal
   P/S is derived from market_cap/ttm_rev (an EQUITY multiple), so the old
   `equity = pv_ev - net_debt` double-counted cash / double-penalized debt
   (measured +27% on a $2B-net-cash stub: base $73.29 → $93.09).

Run: pytest scripts/test_engine_archetype_paths.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from target_engine import (
    DEFAULT_DRIVERS,
    VALUATION_YEAR,
    _archetype_params,
    _scenario_price,
    _scenario_price_revenue_multiple,
)
from test_engine import _make_stub_fin


def _drivers() -> dict:
    return dict(DEFAULT_DRIVERS)


# ── 1. Archetype discount consistency ────────────────────────────────────────

@pytest.mark.parametrize(
    "archetype",
    ["garp", "compounder", "transformational", "special_situation"],
)
def test_terminal_discount_matches_archetype_valuation_year(archetype):
    """PV must equal terminal EV discounted from the archetype's val_year back
    to the target date (12-month horizon → target 1 year out)."""
    fin = _make_stub_fin()
    d = _drivers()
    r = _scenario_price(fin, d, "base", "2025", discount_years=2, archetype=archetype)
    _, val_year, _ = _archetype_params(archetype)
    years_to_target = VALUATION_YEAR - 2  # 12-month horizon → 1 year out
    expected_years = max(0, val_year - years_to_target)
    w = d["discount_rate"]
    assert r.pv_ev_blended == pytest.approx(
        r.terminal_ev_blended / (1 + w) ** expected_years, rel=1e-9
    ), (
        f"{archetype}: terminal at Y{val_year} must be discounted "
        f"{expected_years} years to a 12-month target"
    )


def test_garp_path_unchanged_by_archetype_fix():
    """garp (val_year == VALUATION_YEAR) must discount exactly discount_years —
    the fix must not move any garp output."""
    fin = _make_stub_fin()
    d = _drivers()
    r = _scenario_price(fin, d, "base", "2025", discount_years=2, archetype="garp")
    w = d["discount_rate"]
    assert r.pv_ev_blended == pytest.approx(r.terminal_ev_blended / (1 + w) ** 2, rel=1e-9)


def test_compounder_not_inflated_vs_garp_discounting():
    """The old bug inflated compounder ~(1+WACC)^2 vs consistent discounting.
    On identical inputs, a compounder Y5 terminal discounted correctly must be
    strictly below the same terminal under the buggy 2-year discount."""
    fin = _make_stub_fin()
    d = _drivers()
    r = _scenario_price(fin, d, "base", "2025", discount_years=2, archetype="compounder")
    w = d["discount_rate"]
    buggy_pv = r.terminal_ev_blended / (1 + w) ** 2
    assert r.pv_ev_blended < buggy_pv
    assert buggy_pv / r.pv_ev_blended == pytest.approx((1 + w) ** 2, rel=1e-9)


# ── 2. P/S mode net-debt invariance ──────────────────────────────────────────

def test_ps_price_independent_of_net_debt():
    """P/S is an equity multiple: the target must not move with net debt.
    Old code: a $2B net-cash stub inflated the base price by |net_debt|/share."""
    d = _drivers()
    r_zero = _scenario_price_revenue_multiple(
        _make_stub_fin(net_debt=0.0), d, "base", "2025", discount_years=2
    )
    r_cash = _scenario_price_revenue_multiple(
        _make_stub_fin(net_debt=-2_000_000_000.0), d, "base", "2025", discount_years=2
    )
    r_debt = _scenario_price_revenue_multiple(
        _make_stub_fin(net_debt=3_000_000_000.0), d, "base", "2025", discount_years=2
    )
    assert r_zero.price == pytest.approx(r_cash.price, rel=1e-9)
    assert r_zero.price == pytest.approx(r_debt.price, rel=1e-9)


def test_ps_equity_is_pv_of_terminal_value():
    """In P/S mode, equity value IS the discounted Rev×P/S — no net-debt bridge."""
    d = _drivers()
    r = _scenario_price_revenue_multiple(
        _make_stub_fin(net_debt=-2_000_000_000.0), d, "base", "2025", discount_years=2
    )
    assert r.equity_value == pytest.approx(r.pv_ev_blended, rel=1e-9)
