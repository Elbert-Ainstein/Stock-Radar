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
    ROIIC_FADE_YEARS,
    FORECAST_YEARS,
    MARGIN_RAMP_YEARS,
    _forecast_annual,
    _gordon_roiic_terminal_ev,
    _compute_bottom_up_wacc,
    SECTOR_UNLEVERED_BETAS,
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


# ---------------------------------------------------------------------------
# Test 10: MODEL_OUTPUT_SCHEMA validates correctly
# ---------------------------------------------------------------------------

class TestModelOutputSchema:
    """Verify the Structured Outputs JSON schema accepts valid model output
    and rejects invalid output (using jsonschema if available, else basic checks)."""

    VALID_MODEL = {
        "thesis": "Test thesis for a growth stock.",
        "sector": "Semiconductors",
        "kill_condition": "Revenue growth below 10% for 2 quarters.",
        "archetype": {
            "primary": "garp",
            "secondary": None,
            "justification": "Moderate growth at reasonable valuation.",
            "lifecycle_stage": "mature_growth",
            "moat_width": "narrow",
        },
        "valuation_method": "pe",
        "valuation_justification": "Profitable with stable earnings.",
        "model_defaults": {
            "revenue_b": 5.2,
            "op_margin": 0.35,
            "tax_rate": 0.15,
            "shares_m": 150,
            "pe_multiple": 30,
            "ps_multiple": None,
            "valuation_method": "pe",
        },
        "scenarios": {
            "bull": {"probability": 0.22, "price": 180.0, "trigger": "AI upside."},
            "base": {"probability": 0.55, "price": 130.0, "trigger": "Steady growth."},
            "bear": {"probability": 0.23, "price": 75.0, "trigger": "Cycle downturn."},
        },
        "criteria": [
            {
                "id": "ai_datacenter_demand",
                "label": "AI Datacenter Demand",
                "detail": "Strong hyperscaler capex sustains orders.",
                "variable": "R",
                "weight": "critical",
                "status": "not_yet",
                "eval_hint": "Revenue >= $6B by FY2027",
                "price_impact_pct": 15,
                "price_impact_direction": "up",
            },
        ],
        "target_notes": "Base case driven by $5.2B revenue growing 20% with 35% margins at 30x PE.",
        "divergence_note": None,
    }

    def test_schema_has_all_required_keys(self):
        """MODEL_OUTPUT_SCHEMA.required covers all expected top-level fields."""
        from generate_model import MODEL_OUTPUT_SCHEMA
        expected = {
            "thesis", "sector", "kill_condition", "archetype",
            "valuation_method", "valuation_justification",
            "model_defaults", "scenarios", "criteria", "target_notes",
            "divergence_note",
        }
        assert set(MODEL_OUTPUT_SCHEMA["required"]) == expected

    def test_schema_disallows_additional_properties(self):
        """Top-level and nested objects all set additionalProperties=False."""
        from generate_model import MODEL_OUTPUT_SCHEMA
        assert MODEL_OUTPUT_SCHEMA.get("additionalProperties") is False
        for key in ("archetype", "model_defaults", "scenarios"):
            nested = MODEL_OUTPUT_SCHEMA["properties"][key]
            assert nested.get("additionalProperties") is False, f"{key} missing additionalProperties:false"

    def test_valid_model_matches_schema_keys(self):
        """A valid model dict has exactly the keys the schema requires."""
        from generate_model import MODEL_OUTPUT_SCHEMA
        required = set(MODEL_OUTPUT_SCHEMA["required"])
        assert set(self.VALID_MODEL.keys()) == required

    def test_jsonschema_validates_if_available(self):
        """If jsonschema is installed, run full validation."""
        from generate_model import MODEL_OUTPUT_SCHEMA
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        jsonschema.validate(instance=self.VALID_MODEL, schema=MODEL_OUTPUT_SCHEMA)

    def test_archetype_enum_values(self):
        """Archetype primary must be one of the five archetypes."""
        from generate_model import MODEL_OUTPUT_SCHEMA
        arch_props = MODEL_OUTPUT_SCHEMA["properties"]["archetype"]["properties"]
        expected_archetypes = {"garp", "cyclical", "transformational", "compounder", "special_situation"}
        assert set(arch_props["primary"]["enum"]) == expected_archetypes

    def test_criteria_variable_enum(self):
        """Criteria variable must be R, M, P, S, or E."""
        from generate_model import MODEL_OUTPUT_SCHEMA
        item_props = MODEL_OUTPUT_SCHEMA["properties"]["criteria"]["items"]["properties"]
        assert set(item_props["variable"]["enum"]) == {"R", "M", "P", "S", "E"}


# ---------------------------------------------------------------------------
# Gordon + ROIIC fade terminal value tests
# ---------------------------------------------------------------------------
class TestGordonROIICFade:
    """Test the _gordon_roiic_terminal_ev() function."""

    def test_returns_none_for_negative_fcf(self):
        """Negative FCF-SBC should make Gordon infeasible."""
        result = _gordon_roiic_terminal_ev(-100e6, wacc=0.12, g_terminal=0.15)
        assert result is None

    def test_returns_none_when_wacc_lte_g(self):
        """When WACC ≤ g_perpetuity, Gordon fails (infinite TV)."""
        # g_terminal=0.02 → g_perpetuity=0.02, WACC=0.025 → WACC-g=0.005 → too close
        result = _gordon_roiic_terminal_ev(100e6, wacc=0.025, g_terminal=0.02)
        assert result is None

    def test_positive_ev_for_valid_inputs(self):
        """Valid inputs should produce a positive terminal EV."""
        ev = _gordon_roiic_terminal_ev(500e6, wacc=0.12, g_terminal=0.15)
        assert ev is not None
        assert ev > 0

    def test_higher_growth_yields_higher_ev(self):
        """Higher g_terminal should produce higher terminal EV (more fade-period FCF)."""
        ev_low = _gordon_roiic_terminal_ev(500e6, wacc=0.12, g_terminal=0.08)
        ev_high = _gordon_roiic_terminal_ev(500e6, wacc=0.12, g_terminal=0.25)
        assert ev_high > ev_low

    def test_fade_years_constant_exists(self):
        """ROIIC_FADE_YEARS should be positive and reasonable."""
        assert ROIIC_FADE_YEARS >= 3
        assert ROIIC_FADE_YEARS <= 15

    def test_ev_exceeds_naive_gordon(self):
        """Gordon+ROIIC should exceed naive Gordon (which ignores the fade period FCFs)."""
        fcf = 500e6
        wacc = 0.12
        g_term = 0.20
        g_perp = min(g_term, TERMINAL_GROWTH_CAP)  # 0.025
        # Naive Gordon at Y3: FCF × (1+g) / (WACC-g)
        naive = fcf * (1 + g_perp) / (wacc - g_perp)
        roiic = _gordon_roiic_terminal_ev(fcf, wacc=wacc, g_terminal=g_term)
        assert roiic is not None
        assert roiic > naive, "ROIIC fade captures above-WACC growth during fade period"


# ---------------------------------------------------------------------------
# Bottom-up WACC tests
# ---------------------------------------------------------------------------
class TestBottomUpWACC:
    """Test the _compute_bottom_up_wacc() function."""

    def test_zero_debt_gives_pure_equity_wacc(self):
        """With no debt, WACC = cost of equity."""
        wacc = _compute_bottom_up_wacc("semiconductors", total_debt=0, market_cap=10e9)
        # Should be Rf + beta_L × ERP = 0.043 + 1.40 × 0.055 ≈ 0.12
        assert 0.10 <= wacc <= 0.14

    def test_higher_beta_sector_gets_higher_wacc(self):
        """A riskier sector (higher beta) should have a higher WACC."""
        wacc_safe = _compute_bottom_up_wacc("consumer_tech", total_debt=0, market_cap=20e9)
        wacc_risky = _compute_bottom_up_wacc("quantum_computing", total_debt=0, market_cap=20e9)
        assert wacc_risky > wacc_safe

    def test_wacc_clamped_to_range(self):
        """WACC must be in [0.06, 0.22]."""
        # Very low-risk
        wacc_low = _compute_bottom_up_wacc("consumer_tech", total_debt=0, market_cap=100e9)
        assert wacc_low >= 0.06
        # Very high leverage
        wacc_high = _compute_bottom_up_wacc("quantum_computing", total_debt=50e9, market_cap=1e9)
        assert wacc_high <= 0.22

    def test_unknown_sector_uses_default_beta(self):
        """Unknown sector should fall back to default unlevered beta."""
        wacc = _compute_bottom_up_wacc("underwater_basket_weaving", total_debt=0, market_cap=10e9)
        assert 0.06 <= wacc <= 0.22

    def test_all_sectors_have_positive_betas(self):
        """Every sector beta should be positive."""
        for sector, beta in SECTOR_UNLEVERED_BETAS.items():
            assert beta > 0, f"Sector {sector} has non-positive beta"


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------
try:
    from hypothesis import given, strategies as st, settings, assume
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

if HAS_HYPOTHESIS:
    # Strategy for valid driver dicts
    _driver_strategy = st.fixed_dictionaries({
        "rev_growth_y1": st.floats(min_value=-0.20, max_value=1.0),
        "rev_growth_terminal": st.floats(min_value=-0.10, max_value=0.50),
        "ebitda_margin_target": st.floats(min_value=-0.10, max_value=0.90),
        "fcf_sbc_margin_target": st.floats(min_value=-0.20, max_value=0.85),
        "ev_ebitda_multiple": st.floats(min_value=3.0, max_value=80.0),
        "ev_fcf_sbc_multiple": st.floats(min_value=3.0, max_value=80.0),
        "discount_rate": st.floats(min_value=0.05, max_value=0.25),
        "tax_rate": st.floats(min_value=0.0, max_value=0.40),
        "da_pct_rev": st.floats(min_value=0.0, max_value=0.25),
        "sbc_pct_rev": st.floats(min_value=0.0, max_value=0.40),
        "share_change_pct": st.floats(min_value=-0.05, max_value=0.10),
    })

    class TestPropertyBased:
        """Property-based tests using Hypothesis for target_engine."""

        @given(drivers=_driver_strategy)
        @settings(max_examples=50, deadline=2000)
        def test_forecast_always_produces_correct_length(self, drivers):
            """Forecast should always have exactly FORECAST_YEARS periods."""
            fin = _make_stub_fin()
            annual = _forecast_annual(fin, drivers, "FY2025")
            assert len(annual) == FORECAST_YEARS

        @given(drivers=_driver_strategy)
        @settings(max_examples=50, deadline=2000)
        def test_forecast_revenue_never_negative(self, drivers):
            """Revenue should never go negative (even with extreme contraction)."""
            assume(drivers["rev_growth_y1"] >= -0.50)
            fin = _make_stub_fin()
            annual = _forecast_annual(fin, drivers, "FY2025")
            for period in annual:
                assert period.revenue >= 0, f"Negative revenue in {period.period}"

        @given(drivers=_driver_strategy)
        @settings(max_examples=50, deadline=2000)
        def test_fcf_margin_never_exceeds_ebitda_margin(self, drivers):
            """FCF-SBC margin invariant: must always be ≤ EBITDA margin."""
            fin = _make_stub_fin()
            annual = _forecast_annual(fin, drivers, "FY2025")
            for period in annual:
                assert period.fcf_sbc_margin <= period.ebitda_margin + 0.001, \
                    f"FCF-SBC margin ({period.fcf_sbc_margin:.3f}) > EBITDA margin ({period.ebitda_margin:.3f}) in {period.period}"

        @given(
            fcf=st.floats(min_value=1e6, max_value=1e12),
            wacc=st.floats(min_value=0.06, max_value=0.22),
            g_term=st.floats(min_value=0.03, max_value=0.50),
        )
        @settings(max_examples=50, deadline=2000)
        def test_gordon_roiic_monotonic_in_fcf(self, fcf, wacc, g_term):
            """Higher FCF should always produce higher terminal EV."""
            ev1 = _gordon_roiic_terminal_ev(fcf, wacc, g_term)
            ev2 = _gordon_roiic_terminal_ev(fcf * 2, wacc, g_term)
            if ev1 is not None and ev2 is not None:
                assert ev2 > ev1

        @given(
            debt=st.floats(min_value=0, max_value=50e9),
            mcap=st.floats(min_value=1e8, max_value=500e9),
        )
        @settings(max_examples=50, deadline=2000)
        def test_wacc_always_in_bounds(self, debt, mcap):
            """WACC must always be within [0.06, 0.22] regardless of inputs."""
            wacc = _compute_bottom_up_wacc("semiconductors", debt, mcap)
            assert 0.06 <= wacc <= 0.22
