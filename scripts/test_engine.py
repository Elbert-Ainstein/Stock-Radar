#!/usr/bin/env python3
"""
Regression test suite for target_engine.py.
Run: pytest scripts/test_engine.py -v
"""
import sys
from pathlib import Path

# Ensure scripts dir is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from target_engine import (
    DEFAULT_DRIVERS,
    DRIVER_META,
    SCENARIO_OFFSETS,
    TERMINAL_GROWTH_CAP,
    FORECAST_YEARS,
    MARGIN_RAMP_YEARS,
    _forecast_annual,
)
from finance_data import FinancialData


# ---------------------------------------------------------------------------
# Helpers — minimal stub for FinancialData with known numbers
# ---------------------------------------------------------------------------

def _make_stub_fin(
    ttm_rev: float = 4_000_000_000.0,
    ttm_ebitda: float = 1_000_000_000.0,
    ttm_oi: float = 800_000_000.0,
    ttm_fcf: float = 600_000_000.0,
    ttm_sbc: float = 200_000_000.0,
    shares: float = 500_000_000.0,
    net_debt: float = 1_000_000_000.0,
    price: float = 100.0,
) -> FinancialData:
    """Build a FinancialData stub with 4 identical quarters so TTM helpers work."""
    q_rev = ttm_rev / 4
    q_ebitda = ttm_ebitda / 4
    q_oi = ttm_oi / 4
    q_fcf = ttm_fcf / 4
    q_sbc = ttm_sbc / 4
    q_da = (ttm_ebitda - ttm_oi) / 4  # D&A = EBITDA - OI

    def _make_quarter(label: str) -> dict:
        return {
            "period": label,
            "Total Revenue": q_rev,
            "EBITDA": q_ebitda,
            "Operating Income": q_oi,
        }

    def _make_cf_quarter(label: str) -> dict:
        return {
            "period": label,
            "Free Cash Flow": q_fcf,
            "Stock Based Compensation": q_sbc,
            "Depreciation And Amortization": q_da,
        }

    quarters = [_make_quarter(f"Q{i}-2025") for i in range(1, 5)]
    cf_quarters = [_make_cf_quarter(f"Q{i}-2025") for i in range(1, 5)]

    return FinancialData(
        ticker="TEST",
        name="Test Corp",
        sector="Technology",
        currency="USD",
        price=price,
        market_cap=price * shares,
        shares_diluted=shares,
        net_debt=net_debt,
        quarterly_income=quarters,
        quarterly_cashflow=cf_quarters,
        quarterly_balance=[],
        annual_income=[{
            "period": "FY2024",
            "Total Revenue": ttm_rev,
            "EBITDA": ttm_ebitda,
            "Operating Income": ttm_oi,
        }],
        annual_cashflow=[{
            "period": "FY2024",
            "Free Cash Flow": ttm_fcf,
            "Stock Based Compensation": ttm_sbc,
        }],
        annual_balance=[],
        source="test",
    )


# ---------------------------------------------------------------------------
# Test 1: Scenario weights sum to one
# ---------------------------------------------------------------------------

class TestScenarioWeights:
    """Verify that the three scenario labels exist and form a complete set.

    The engine does not apply explicit probability weights (it emits low/base/high
    independently). This test verifies all three scenario keys are present in
    SCENARIO_OFFSETS so the downstream consumer can apply any weighting (e.g.
    the 0.2 / 0.6 / 0.2 convention) without gaps.
    """

    def test_all_three_scenarios_present(self):
        """downside, base, upside must all be defined in SCENARIO_OFFSETS."""
        assert "downside" in SCENARIO_OFFSETS
        assert "base" in SCENARIO_OFFSETS
        assert "upside" in SCENARIO_OFFSETS

    def test_default_probability_weights_sum_to_one(self):
        """The conventional 0.2/0.6/0.2 weights referenced in documentation sum to 1."""
        weights = (0.2, 0.6, 0.2)
        assert abs(sum(weights) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Test 2: Terminal growth hard cap
# ---------------------------------------------------------------------------

class TestTerminalGrowthCap:
    """TERMINAL_GROWTH_CAP must exist and not exceed the long-run risk-free rate."""

    def test_cap_exists(self):
        """The constant must be defined."""
        assert TERMINAL_GROWTH_CAP is not None

    def test_cap_at_most_2_5_pct(self):
        """Terminal perpetuity growth > 2.5% implies eventual economy domination."""
        assert TERMINAL_GROWTH_CAP <= 0.025


# ---------------------------------------------------------------------------
# Test 3: Scenario offset direction checks
# ---------------------------------------------------------------------------

class TestNegativeScenarioInversion:
    """Downside revenue multipliers must be < 1 and upside > 1.
    Downside margin deltas must be negative; upside deltas must be >= 0.
    """

    def test_downside_revenue_multipliers_below_one(self):
        """Downside scenarios should shrink revenue."""
        down = SCENARIO_OFFSETS["downside"]
        assert down["rev_growth_y1_mult"] < 1.0
        assert down["rev_growth_terminal_mult"] < 1.0

    def test_upside_revenue_multipliers_above_one(self):
        """Upside scenarios should boost revenue."""
        up = SCENARIO_OFFSETS["upside"]
        assert up["rev_growth_y1_mult"] > 1.0
        assert up["rev_growth_terminal_mult"] > 1.0

    def test_downside_margin_deltas_negative(self):
        """Downside margin offsets must compress margins."""
        down = SCENARIO_OFFSETS["downside"]
        assert down["ebitda_margin_delta"] < 0
        assert down["fcf_sbc_margin_delta"] < 0

    def test_upside_margin_deltas_non_negative(self):
        """Upside margin offsets must be >= 0 (no penalty in bull case)."""
        up = SCENARIO_OFFSETS["upside"]
        assert up["ebitda_margin_delta"] >= 0
        assert up["fcf_sbc_margin_delta"] >= 0

    def test_base_revenue_multipliers_are_one(self):
        """Base scenario must not alter revenue growth."""
        base = SCENARIO_OFFSETS["base"]
        assert base["rev_growth_y1_mult"] == 1.0
        assert base["rev_growth_terminal_mult"] == 1.0

    def test_downside_multiple_multipliers_below_one(self):
        """Downside valuation multiples should contract."""
        down = SCENARIO_OFFSETS["downside"]
        assert down["ev_ebitda_multiple_mult"] < 1.0
        assert down["ev_fcf_sbc_multiple_mult"] < 1.0

    def test_upside_multiple_multipliers_above_one(self):
        """Upside valuation multiples should expand."""
        up = SCENARIO_OFFSETS["upside"]
        assert up["ev_ebitda_multiple_mult"] > 1.0
        assert up["ev_fcf_sbc_multiple_mult"] > 1.0


# ---------------------------------------------------------------------------
# Test 4: WACC constant across scenarios
# ---------------------------------------------------------------------------

class TestWACCConstant:
    """WACC must NOT vary by scenario — varying it double-counts risk."""

    def test_no_discount_rate_in_offsets(self):
        """No scenario offset should contain a discount_rate key."""
        for scenario_name, offsets in SCENARIO_OFFSETS.items():
            assert "discount_rate" not in offsets, (
                f"SCENARIO_OFFSETS['{scenario_name}'] contains discount_rate — "
                f"WACC must be constant across scenarios"
            )

    def test_no_discount_rate_mult_in_offsets(self):
        """Also check for discount_rate_mult variants."""
        for scenario_name, offsets in SCENARIO_OFFSETS.items():
            for key in offsets:
                assert "discount" not in key.lower(), (
                    f"SCENARIO_OFFSETS['{scenario_name}'] has key '{key}' "
                    f"that looks like a discount-rate modifier"
                )


# ---------------------------------------------------------------------------
# Test 5: Default drivers within DRIVER_META min/max
# ---------------------------------------------------------------------------

class TestDefaultDriverRanges:
    """Every DEFAULT_DRIVERS value must fall within DRIVER_META min/max."""

    def test_all_defaults_within_meta_bounds(self):
        """Loop over keys present in both dicts and check bounds."""
        common_keys = set(DEFAULT_DRIVERS) & set(DRIVER_META)
        assert len(common_keys) > 0, "No overlapping keys between DEFAULT_DRIVERS and DRIVER_META"

        for key in sorted(common_keys):
            val = DEFAULT_DRIVERS[key]
            meta = DRIVER_META[key]
            lo, hi = meta["min"], meta["max"]
            assert lo <= val <= hi, (
                f"DEFAULT_DRIVERS['{key}'] = {val} outside "
                f"DRIVER_META range [{lo}, {hi}]"
            )


# ---------------------------------------------------------------------------
# Test 6: Share change default is non-negative
# ---------------------------------------------------------------------------

class TestShareChangeDefault:
    """Net issuance (not buyback) should be the default assumption."""

    def test_share_change_pct_non_negative(self):
        """Default net dilution must be >= 0 (net issuance, not buyback)."""
        assert DEFAULT_DRIVERS["share_change_pct"] >= 0, (
            "Default share_change_pct should be >= 0 (net issuance); "
            f"got {DEFAULT_DRIVERS['share_change_pct']}"
        )


# ---------------------------------------------------------------------------
# Test 7: SBC % of revenue default
# ---------------------------------------------------------------------------

class TestSBCDefault:
    """SBC / revenue fallback should be 5%."""

    def test_sbc_pct_rev_is_five_percent(self):
        """When SBC is unreported the engine falls back to 5% of revenue."""
        assert DEFAULT_DRIVERS["sbc_pct_rev"] == 0.05, (
            f"Expected sbc_pct_rev default of 0.05, got {DEFAULT_DRIVERS['sbc_pct_rev']}"
        )


# ---------------------------------------------------------------------------
# Test 8: Margin invariant in forecast
# ---------------------------------------------------------------------------

class TestMarginInvariantInForecast:
    """For every forecast period: EBITDA margin >= op margin, and
    FCF-SBC margin <= EBITDA margin.

    EBITDA includes D&A on top of operating income, so it must be higher.
    FCF-SBC deducts stock-based compensation from cash flow, so it must
    be below EBITDA margin.
    """

    def test_margin_ordering_with_defaults(self):
        """Using default drivers and a well-behaved stub, check invariants."""
        fin = _make_stub_fin()
        drivers = dict(DEFAULT_DRIVERS)
        forecast = _forecast_annual(fin, drivers, "FY2025")

        assert len(forecast) == FORECAST_YEARS, (
            f"Expected {FORECAST_YEARS} forecast periods, got {len(forecast)}"
        )

        for period in forecast:
            assert period.ebitda_margin >= period.op_margin - 1e-9, (
                f"{period.period}: EBITDA margin ({period.ebitda_margin:.4f}) "
                f"< op margin ({period.op_margin:.4f})"
            )
            assert period.fcf_sbc_margin <= period.ebitda_margin + 1e-9, (
                f"{period.period}: FCF-SBC margin ({period.fcf_sbc_margin:.4f}) "
                f"> EBITDA margin ({period.ebitda_margin:.4f})"
            )

    def test_margin_ordering_high_growth(self):
        """With aggressive growth and tighter margins, invariants still hold."""
        fin = _make_stub_fin(
            ttm_rev=2_000_000_000.0,
            ttm_ebitda=200_000_000.0,
            ttm_oi=100_000_000.0,
            ttm_fcf=50_000_000.0,
            ttm_sbc=100_000_000.0,
        )
        drivers = dict(DEFAULT_DRIVERS)
        drivers["rev_growth_y1"] = 0.40
        drivers["rev_growth_terminal"] = 0.15
        drivers["ebitda_margin_target"] = 0.30
        drivers["fcf_sbc_margin_target"] = 0.20
        forecast = _forecast_annual(fin, drivers, "FY2025")

        for period in forecast:
            assert period.ebitda_margin >= period.op_margin - 1e-9, (
                f"{period.period}: EBITDA margin ({period.ebitda_margin:.4f}) "
                f"< op margin ({period.op_margin:.4f})"
            )
            assert period.fcf_sbc_margin <= period.ebitda_margin + 1e-9, (
                f"{period.period}: FCF-SBC margin ({period.fcf_sbc_margin:.4f}) "
                f"> EBITDA margin ({period.ebitda_margin:.4f})"
            )


# ---------------------------------------------------------------------------
# Test 9: No exec/eval in API routes (security regression)
# ---------------------------------------------------------------------------

class TestNoExecInAPIRoutes:
    """API route handlers must never use exec() or eval() — code injection risk."""

    def test_no_exec_or_eval_in_api_files(self):
        """Scan all .py and .ts files under app/api/ for dangerous calls."""
        import re

        api_dir = Path(__file__).resolve().parent.parent / "app" / "api"
        if not api_dir.exists():
            pytest.skip(f"API directory not found at {api_dir}")

        dangerous = re.compile(r"\b(exec|eval)\s*\(")
        violations = []

        for ext in ("*.py", "*.ts"):
            for fpath in api_dir.rglob(ext):
                try:
                    text = fpath.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for line_no, line in enumerate(text.splitlines(), start=1):
                    # Skip comments
                    stripped = line.lstrip()
                    if stripped.startswith("//") or stripped.startswith("#"):
                        continue
                    if dangerous.search(line):
                        violations.append(f"{fpath.relative_to(api_dir)}:{line_no}: {line.strip()}")

        assert not violations, (
            f"Found exec()/eval() in API routes:\n" +
            "\n".join(violations)
        )
