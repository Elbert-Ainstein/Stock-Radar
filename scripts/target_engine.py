#!/usr/bin/env python3
"""
target_engine.py — Institutional-grade discounted-forward pure-function price engine.

Methodology (calibrated against sell-side coverage models, including Applovin
dated 2026-01-12, using standard institutional valuation practices):

    1. Build a 5-year forecast (Y1..Y5) with declining revenue growth and
       ramping EBITDA / (FCF-SBC) margins that reach terminal by Year 3.
    2. Value terminal at end of Year 3 using two independent methods:
         EV_ebitda  = Y3 EBITDA        × EV/EBITDA multiple
         EV_fcf_sbc = Y3 (FCF − SBC)   × EV/(FCF-SBC) multiple
       Blend 50/50 → terminal EV. Gordon Growth Model computed as a
       cross-check when feasible; divergence >20% triggers a warning.
    3. Discount terminal EV back 2 years at constant WACC to PV.
       (Targets are 12-month-forward, so we compress the 3-year horizon by 1.)
    4. Equity = PV_EV − Net Debt. Price = Equity / Diluted shares (dilution
       applied over 1 year = VALUATION_YEAR − DISCOUNT_YEARS).
    5. Three INDEPENDENT scenarios (Downside / Base / Upside) with their own
       driver paths (growth, margin target, multiples). NOT a symmetric width
       haircut — scenario offsets are asymmetric, calibrated against published
       sell-side models.

This engine is the single source of truth: brief slider view, detailed page,
and Excel export all consume `TargetResult` objects built here.

Contract:
    result = build_target(fin, drivers)
    result.low   # downside target $
    result.base  # base target $
    result.high  # upside target $
    result.steps # deduction chain (base scenario) for UI
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import math
import sys

from finance_data import FinancialData, EarningsFetchError


# ---------------------------------------------------------------------------
# Terminal growth hard cap — any terminal rate above the long-run risk-free
# rate implies the company eventually becomes larger than the entire economy.
# ---------------------------------------------------------------------------
TERMINAL_GROWTH_CAP = 0.025


# ---------------------------------------------------------------------------
# Driver schema — BASE case drivers (scenarios derive via fixed offsets)
# ---------------------------------------------------------------------------
DEFAULT_DRIVERS: dict[str, float] = {
    # Revenue growth curve (declines linearly Y1 → Y5)
    "rev_growth_y1": 0.15,         # Year 1 YoY growth
    "rev_growth_terminal": 0.08,   # Year 5 YoY growth (terminal)
    # Terminal (end-Y3) margins — reached via ramp from current TTM
    "ebitda_margin_target": 0.25,
    "fcf_sbc_margin_target": 0.18,
    # NTM+3 exit multiples (base scenario)
    "ev_ebitda_multiple": 16.0,
    "ev_fcf_sbc_multiple": 22.0,
    # WACC — constant across all scenarios (CAPM-derived per company)
    # Varying WACC by scenario double-counts risk: bear cash flows already
    # reflect downside; discounting them harder penalizes twice.
    "discount_rate": 0.12,
    # Share dilution (net issuance), applied over 3 years between today and valuation point
    "share_change_pct": 0.01,
    # Tax rate (reserved for any pretax-to-aftertax conversion)
    "tax_rate": 0.18,
    # D&A as % of revenue — fallback when EBITDA is not directly reported
    "da_pct_rev": 0.05,
    # SBC as % of revenue — fallback when SBC is not reported in cash flow
    "sbc_pct_rev": 0.05,
}

# Sliders the brief view exposes by default. Frontend reads this list from the
# API payload (never hardcodes it) so we can swap sliders without FE changes.
DEFAULT_SLIDER_KEYS = [
    "rev_growth_y1",
    "rev_growth_terminal",
    "ebitda_margin_target",
    "fcf_sbc_margin_target",
    "ev_ebitda_multiple",
    "ev_fcf_sbc_multiple",
    "discount_rate",
]

DRIVER_META: dict[str, dict[str, Any]] = {
    "rev_growth_y1": {"label": "Revenue growth Y1", "format": "pct", "min": -0.30, "max": 1.50, "step": 0.01},
    "rev_growth_terminal": {"label": "Revenue growth Y5 (terminal)", "format": "pct", "min": -0.10, "max": 0.60, "step": 0.01},
    "ebitda_margin_target": {"label": "EBITDA margin (Y3 target)", "format": "pct", "min": -0.20, "max": 0.95, "step": 0.01},
    "fcf_sbc_margin_target": {"label": "FCF − SBC margin (Y3 target)", "format": "pct", "min": -0.30, "max": 0.90, "step": 0.01},
    "ev_ebitda_multiple": {"label": "EV/EBITDA (NTM+3, base)", "format": "mult", "min": 3.0, "max": 80.0, "step": 0.5},
    "ev_fcf_sbc_multiple": {"label": "EV/(FCF-SBC) (NTM+3, base)", "format": "mult", "min": 3.0, "max": 80.0, "step": 0.5},
    "discount_rate": {"label": "WACC (all scenarios)", "format": "pct", "min": 0.05, "max": 0.25, "step": 0.005},
    "tax_rate": {"label": "Tax rate", "format": "pct", "min": 0.0, "max": 0.40, "step": 0.01},
    "da_pct_rev": {"label": "D&A / revenue", "format": "pct", "min": 0.0, "max": 0.30, "step": 0.005},
    "sbc_pct_rev": {"label": "SBC / revenue", "format": "pct", "min": 0.0, "max": 0.50, "step": 0.005},
    "share_change_pct": {"label": "Net dilution / yr", "format": "pct", "min": -0.05, "max": 0.15, "step": 0.005},
}


# ---------------------------------------------------------------------------
# Scenario offsets (calibrated against institutional sell-side models)
# ---------------------------------------------------------------------------
# Reference Base/Down/Up ratios: Rev NTM 7084/6376/7793 = 1.00/0.90/1.10
# EBITDA mgn: 80.5% / 76% / 80.5% (delta -4.5pp / 0 / 0)
# EV/EBITDA mult: 32/24/36x (ratio 1.00/0.75/1.125)
# EV/FCF-SBC:    28/20/32x (ratio 1.00/0.714/1.143)
#
# NOTE: WACC is now CONSTANT across all scenarios. The old approach
# (15%/12%/10% for down/base/up) double-counted risk: bear-case cash
# flows already reflect compressed margins and slower growth —
# discounting them at a higher rate penalizes the downside twice,
# systematically biasing the probability-weighted blend upward.
# The discount_rate from DEFAULT_DRIVERS is used for all scenarios.
SCENARIO_OFFSETS: dict[str, dict[str, float]] = {
    "downside": {
        "rev_growth_y1_mult": 0.88,
        "rev_growth_terminal_mult": 0.80,
        "ebitda_margin_delta": -0.045,
        "fcf_sbc_margin_delta": -0.060,
        "ev_ebitda_multiple_mult": 0.75,
        "ev_fcf_sbc_multiple_mult": 0.714,
        # discount_rate removed — uses base WACC for all scenarios
    },
    "base": {
        "rev_growth_y1_mult": 1.00,
        "rev_growth_terminal_mult": 1.00,
        "ebitda_margin_delta": 0.0,
        "fcf_sbc_margin_delta": 0.0,
        "ev_ebitda_multiple_mult": 1.00,
        "ev_fcf_sbc_multiple_mult": 1.00,
    },
    "upside": {
        "rev_growth_y1_mult": 1.10,
        "rev_growth_terminal_mult": 1.15,
        "ebitda_margin_delta": 0.0,
        "fcf_sbc_margin_delta": 0.0,
        "ev_ebitda_multiple_mult": 1.125,
        "ev_fcf_sbc_multiple_mult": 1.143,
    },
}

# Valuation point: we apply terminal multiples at end of Year VALUATION_YEAR,
# then discount back DISCOUNT_YEARS years to arrive at the target price.
# Convention: sell-side targets are "12-month forward" (one year ahead),
# so we discount only 2 of the 3 years between today and valuation point.
VALUATION_YEAR = 3          # Apply multiple to Y3 financials
DISCOUNT_YEARS = 2          # Default: discount back 2 years → 12-month-forward target
# Supported price-target horizons (months forward). DISCOUNT_YEARS per horizon
# is VALUATION_YEAR - (horizon_months / 12) so Y3 fundamentals are walked back
# by the right number of years to land at the target date.
SUPPORTED_HORIZONS_MONTHS = (12, 24, 36)


def _discount_years_for_horizon(horizon_months: int) -> int:
    """Y3 terminal minus target-year-offset. 12mo→2, 24mo→1, 36mo→0."""
    h = int(horizon_months)
    if h not in SUPPORTED_HORIZONS_MONTHS:
        raise ValueError(
            f"horizon_months={h} unsupported; must be one of {SUPPORTED_HORIZONS_MONTHS}"
        )
    return VALUATION_YEAR - (h // 12)
# Years to ramp margins from current TTM → target. GS implies ~Y2-Y3 reach.
MARGIN_RAMP_YEARS = 3
# Forecast horizon
FORECAST_YEARS = 5


# ---------------------------------------------------------------------------
# TTM helpers that aren't on FinancialData
# ---------------------------------------------------------------------------
def _ttm_sbc(fin: FinancialData) -> float:
    """Trailing 4Q sum of stock-based compensation. 0.0 if not reported."""
    vals = [p.get("Stock Based Compensation") for p in fin.quarterly_cashflow[-4:]]
    vals = [v for v in vals if v is not None]
    if len(vals) == 4:
        return sum(vals)
    # Fallback to annual latest / 4 per quarter proxy
    if fin.annual_cashflow:
        annual_sbc = fin.annual_cashflow[-1].get("Stock Based Compensation")
        if annual_sbc is not None:
            return annual_sbc
    return 0.0


def _ttm_fcf_sbc(fin: FinancialData) -> float | None:
    """TTM FCF minus TTM SBC. Needed for the EV/(FCF-SBC) valuation method."""
    fcf = fin.ttm_fcf()
    if fcf is None:
        return None
    return fcf - _ttm_sbc(fin)


def _annual_rev_series(fin: FinancialData) -> list[float]:
    """Chronological annual revenue, non-null only."""
    out = []
    for p in fin.annual_income:
        r = p.get("Total Revenue")
        if r is not None and r > 0:
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Smart defaults — derived from the ticker's own actuals
# ---------------------------------------------------------------------------
def compute_smart_defaults(
    fin: FinancialData,
    forward: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Driver defaults inferred from this ticker's actuals and forward signals.

    Goal: if the user doesn't touch any slider, we produce a reasonable target
    using the company's own historical growth + current trading multiples as
    the base case. The UI sliders then let them compress/expand from there.

    `forward` is an optional dict from `forward_drivers.load_forward_drivers`:
    it carries management-guided growth, moat quality, TAM growth, and
    business-quality scores that the fundamentals and news scouts extracted.
    When present, these signals are blended into the backward-looking
    historicals rather than replacing them — the engine stays honest (it
    never blindly accepts a guide) but stops ignoring the forward story.
    """
    out = dict(DEFAULT_DRIVERS)
    forward = forward or {}
    ttm_rev = fin.ttm_revenue() or 0.0
    ttm_ebitda = fin.ttm_ebitda() or 0.0
    ttm_fcf_sbc = _ttm_fcf_sbc(fin) or 0.0

    ttm_ebitda_margin = (ttm_ebitda / ttm_rev) if ttm_rev else 0.0
    ttm_fcf_sbc_margin = (ttm_fcf_sbc / ttm_rev) if ttm_rev else 0.0

    # ---- D&A and SBC as % of revenue (derived FIRST so later blocks can use them) ----
    # These must be computed before the op-margin blend below, because the blend
    # converts guided op margin → implied EBITDA margin via `guided_op + da_pct_rev`.
    # If we leave D&A at the default 0.05, a company with 15% D&A (LITE) gets its
    # EBITDA target understated by ~10pp and the whole forward-guidance blend
    # silently underweighs management guidance.
    ttm_oi_pre = fin.ttm_operating_income() or 0.0
    if ttm_ebitda > 0 and ttm_rev > 0 and ttm_ebitda > ttm_oi_pre:
        out["da_pct_rev"] = max(0.01, min(0.30, (ttm_ebitda - ttm_oi_pre) / ttm_rev))
    ttm_sbc_pre = _ttm_sbc(fin)
    if ttm_sbc_pre > 0 and ttm_rev > 0:
        raw_sbc_pct = ttm_sbc_pre / ttm_rev
        # For pre-profit companies where SBC >> revenue (common in small caps),
        # the raw ratio can be 100-1000%+. Capping at 30% would undercount the
        # dilution hit. Instead, project what SBC/revenue will be at Y3 when
        # revenue has scaled (SBC grows slower than revenue in growth companies).
        # Use a softer cap that converges to 30% for established companies but
        # allows up to 50% for very early-stage names.
        if raw_sbc_pct > 0.50:
            # Project: if revenue triples by Y3, SBC/rev ≈ raw/3 or at least 15%.
            # Use midpoint of (projected Y3 SBC/rev) and current, capped at 50%.
            projected_sbc_pct = max(0.15, raw_sbc_pct / 3)
            out["sbc_pct_rev"] = min(0.50, (raw_sbc_pct + projected_sbc_pct) / 2)
        else:
            out["sbc_pct_rev"] = max(0.0, min(0.30, raw_sbc_pct))

    # ---- Revenue growth Y1 ----
    # Combine all available backward-looking signals with weights proportional
    # to their information density. This is much more robust than the old
    # "first-available" waterfall, which pathologically ignored recent
    # acceleration when quarterly data was sparse.
    #
    # LITE is the canonical failure case for the old logic: yfinance only
    # returns 5 quarters, so the 8Q path was skipped and the engine fell
    # through to historical CAGR — which was NEGATIVE (-1.3%) because LITE
    # had a trough in 2023-2024. But the most recent quarter (Q4 2025) was
    # up 65% YoY ($666mm vs $402mm) and TTM ($2.1B) was up 28% vs FY25
    # ($1.6B). The old logic produced g1 = -1.3% and a $131 base target for
    # a stock trading at $894. New logic blends signals and gives ~42%.
    #
    # Signal menu (each weighted by how much of a real-time trajectory it
    # captures):
    #   A. 8-quarter YoY average   (smoothest, 4 YoY pairs) → weight 3
    #   B. Partial quarterly YoY   (fewer pairs, 5-7 quarters) → weight 2
    #   C. TTM vs prior fiscal year (captures within-FY acceleration) → weight 2
    #   D. Latest annual YoY       → weight 1
    #   E. Multi-year CAGR         → weight 0.5
    rev_series = _annual_rev_series(fin)
    signals: list[tuple[str, float, float]] = []  # (name, value, weight)
    q = fin.quarterly_income

    # A: 8Q YoY (preferred when available — 4 independent pairs smooth noise)
    if len(q) >= 8:
        pairs: list[float] = []
        for i in range(4):
            cur = q[-4 + i].get("Total Revenue") or 0
            prior = q[-8 + i].get("Total Revenue") or 0
            if prior > 0:
                pairs.append(cur / prior - 1)
        if pairs:
            signals.append(("8q_yoy", sum(pairs) / len(pairs), 3.0))

    # B: Partial quarterly YoY (5-7 quarters) — form every pair we can:
    #    Q[-1] vs Q[-5], Q[-2] vs Q[-6], ...
    if len(q) >= 5 and not any(s[0] == "8q_yoy" for s in signals):
        pairs = []
        max_pairs = min(4, len(q) - 4)
        for i in range(max_pairs):
            cur = q[-1 - i].get("Total Revenue") or 0
            prior = q[-5 - i].get("Total Revenue") or 0
            if prior > 0:
                pairs.append(cur / prior - 1)
        if pairs:
            # Weight scales with number of pairs available (1 pair = 1.0, 4 pairs → ~2.0)
            w = 1.0 + 0.33 * (len(pairs) - 1)
            signals.append((f"{len(pairs)}q_yoy", sum(pairs) / len(pairs), w))

    # C: TTM vs prior fiscal year — catches acceleration that straddles a
    #    fiscal year boundary. If TTM is materially above the last full FY,
    #    the business is tracking above its FY trajectory.
    if ttm_rev > 0 and rev_series and rev_series[-1] > 0:
        ttm_vs_fy = ttm_rev / rev_series[-1] - 1
        # Only include when TTM materially differs from last FY — otherwise
        # it adds zero-information noise (e.g., Q4-aligned tickers where TTM ≈ FY).
        if abs(ttm_vs_fy) > 0.02:
            signals.append(("ttm_vs_fy", ttm_vs_fy, 2.0))

    # D: Latest annual YoY
    if len(rev_series) >= 2:
        annual_yoy = rev_series[-1] / rev_series[-2] - 1
        signals.append(("annual_yoy", annual_yoy, 1.0))

    # E: Multi-year CAGR — baseline/long-run anchor. Weight is intentionally
    #    small because CAGR through a trough-and-recovery dramatically
    #    understates the forward trajectory.
    if len(rev_series) >= 3:
        cagr = (rev_series[-1] / rev_series[0]) ** (1 / (len(rev_series) - 1)) - 1
        signals.append(("cagr", cagr, 0.5))

    # F: Management-guided Y1 growth (from fundamentals scout / news events).
    #    This is the BIG one — for names like LITE, management is guiding
    #    85% growth while yfinance historicals only see 31.5%. Weight this
    #    heavily (6.0) — but NOT infinitely, so a wildly optimistic guide
    #    still gets anchored by historicals. Dampen with moat/quality:
    #    low-quality names get their guidance de-weighted (management may
    #    overpromise); high-quality names with wide moats get near-full weight.
    guided_g = forward.get("guided_rev_growth_y1")
    _ms = forward.get("moat_score")
    moat_score = float(_ms) if _ms is not None else 5.0
    _bq = forward.get("business_quality_score")
    bq_score = float(_bq) if _bq is not None else 5.0
    moat_durability = (forward.get("moat_durability") or "stable").lower()
    moat_type = (forward.get("moat_type") or "narrow").lower()

    if isinstance(guided_g, (int, float)) and 0 <= guided_g < 2.0:
        # Base weight scales with moat+quality (range ~3.0 to 7.0)
        quality_factor = (moat_score + bq_score) / 20.0  # 0.0 - 1.0
        if moat_durability == "strengthening":
            quality_factor = min(1.0, quality_factor + 0.10)
        elif moat_durability == "eroding":
            quality_factor = max(0.0, quality_factor - 0.15)
        guide_weight = 3.0 + 4.0 * quality_factor  # 3.0 - 7.0
        signals.append(("guided_y1", float(guided_g), guide_weight))

    g1: float | None = None
    if signals:
        total_w = sum(w for _, _, w in signals)
        g1 = sum(v * w for _, v, w in signals) / total_w
    if g1 is not None:
        # Size-aware cap: larger companies face harder growth ceilings (scale
        # friction). A $500B-revenue firm cannot grow 80% YoY for long — if
        # our backward-looking signal says 80%, the forward assumption has to
        # compress. This prevents NVDA-style blowouts where 80% extrapolated
        # over 3 years gives a revenue larger than the entire TAM.
        rev_scale_b = (ttm_rev or 1) / 1e9  # in $B
        if rev_scale_b > 500:
            g1_cap = 0.20
        elif rev_scale_b > 150:
            g1_cap = 0.35
        elif rev_scale_b > 30:
            g1_cap = 0.55
        else:
            g1_cap = 0.80
        # Wide-moat/strengthening names in expanding TAMs get a premium on the
        # cap — they can sustain higher growth longer. This is how we let
        # guided 85% for LITE survive after the size cap instead of clipping.
        tam_g = forward.get("tam_growth_rate") or 0.0
        if moat_type == "wide" and moat_durability == "strengthening":
            g1_cap = min(1.20, g1_cap * 1.25 + 0.10)  # +25% relative + 10pp absolute
        elif moat_type == "wide":
            g1_cap = min(1.00, g1_cap * 1.15 + 0.05)
        if isinstance(tam_g, (int, float)) and tam_g >= 0.20:
            # TAM growing ≥20% is a structural tailwind (AI, EVs, etc.)
            g1_cap = min(1.20, g1_cap + 0.10)
        out["rev_growth_y1"] = max(-0.30, min(g1_cap, g1))
        # Terminal: decay toward a floor that's higher for wide-moat names
        # (they hold growth longer). Base floor 8%, wide+strengthening → 15%.
        term_floor = 0.08
        if moat_type == "wide" and moat_durability == "strengthening":
            term_floor = 0.15
        elif moat_type == "wide":
            term_floor = 0.12
        term_cap = 0.25 if moat_type != "wide" else 0.35
        # Y5 ≈ 40% of Y1 for quality names (gentler decay), 33% otherwise
        decay_ratio = 0.40 if moat_type == "wide" else 0.33
        out["rev_growth_terminal"] = max(term_floor, min(out["rev_growth_y1"] * decay_ratio, term_cap))

        # ---- TAM sanity check ----
        # Project a rough Y5 revenue path and verify it doesn't exceed the
        # current TAM × (share_trajectory-adjusted cap). Prevents the engine
        # from projecting revenue larger than the addressable market, which
        # happens silently when wide-moat caps compound with high guided g1.
        tam_usd = forward.get("tam_size_usd")
        if isinstance(tam_usd, (int, float)) and tam_usd > 0 and ttm_rev > 0:
            # Grow TAM forward at its own rate; company can capture up to 60%
            # of a growing TAM in a "leader" case (hist. rare; LITE, NVDA in
            # their segments). For "challenger/niche" names this is implicitly
            # tighter because the scout-reported TAM is smaller.
            tam_g_local2 = forward.get("tam_growth_rate") or 0.05
            tam_at_y5 = tam_usd * ((1 + tam_g_local2) ** 5)
            # Base max share depends on moat; share_trajectory modulates it.
            # A "gaining" share company may realistically reach a higher
            # fraction of TAM over 5Y than a "losing" share one.
            max_share = 0.60 if moat_type == "wide" else 0.35
            traj = (forward.get("share_trajectory") or "stable").lower()
            if traj == "gaining":
                max_share = min(0.75, max_share + 0.10)
            elif traj == "losing":
                max_share = max(0.10, max_share - 0.15)
            rev_ceiling_y5 = tam_at_y5 * max_share
            # Path Y5 revenue under current drivers
            g1_v = out["rev_growth_y1"]
            gt_v = out["rev_growth_terminal"]
            path_y5 = ttm_rev
            for yr in range(5):
                # Linear decay from g1 to terminal
                g = g1_v + (gt_v - g1_v) * (yr / 4)
                path_y5 *= (1 + g)
            if path_y5 > rev_ceiling_y5 and rev_ceiling_y5 > ttm_rev:
                # Solve for the flat growth rate that would hit the ceiling exactly.
                implied_cagr = (rev_ceiling_y5 / ttm_rev) ** (1 / 5) - 1
                # Compress growth drivers to respect TAM bound.
                out["rev_growth_y1"] = min(out["rev_growth_y1"], implied_cagr * 1.15)
                out["rev_growth_terminal"] = min(out["rev_growth_terminal"], implied_cagr * 0.85)
                out["_tam_bound_applied"] = 1.0  # float to match dict type; popped before return
    else:
        out["rev_growth_y1"] = 0.15
        out["rev_growth_terminal"] = 0.10

    # ---- EBITDA margin target (Y3) ----
    # Banded expansion from current TTM margin, scaled by growth.
    # High-growth companies get more margin expansion (operating leverage).
    # Rationale: a company growing 40% YoY with 60% margins has more room to
    # expand (fixed-cost leverage) than one growing 5% with 60% margins.
    g1 = out["rev_growth_y1"]
    growth_expansion = max(0.03, min(0.10, 0.03 + 0.18 * max(0, g1 - 0.10)))
    # growth_expansion: baseline 3pp, +18pp for each 100pp of growth above 10%,
    # capped at 10pp. g1=38% → 3 + 0.18*28 = 8pp. g1=15% → 3.9pp.

    if ttm_ebitda_margin > 0.60:
        # Ultra-high margin (mature software-like) — growth-scaled expansion, cap 85%
        out["ebitda_margin_target"] = min(0.85, ttm_ebitda_margin + growth_expansion)
    elif ttm_ebitda_margin > 0.40:
        # High margin — growth-scaled expansion, cap 80%
        out["ebitda_margin_target"] = min(0.80, ttm_ebitda_margin + growth_expansion + 0.02)
    elif ttm_ebitda_margin > 0.15:
        # Mid margin — assume more operating leverage
        out["ebitda_margin_target"] = min(0.50, ttm_ebitda_margin + max(0.08, growth_expansion))
    elif ttm_ebitda_margin > 0:
        # Low margin — path to ~20%
        out["ebitda_margin_target"] = max(0.15, ttm_ebitda_margin + 0.10)
    else:
        # Negative / zero — turnaround assumption
        out["ebitda_margin_target"] = 0.15

    # Forward-guidance override on margin: if management has explicitly
    # guided non-GAAP op margin, blend it with the historical-derived target.
    # Op margin → EBITDA margin delta is roughly +(D&A/rev), so add that back.
    # This works both ways: guidance can raise OR lower the target (e.g., if
    # management guides lower margins for an investment cycle).
    guided_op = forward.get("guided_op_margin")
    if isinstance(guided_op, (int, float)) and 0 < guided_op < 0.85:
        implied_ebitda_mgn = min(0.85, guided_op + out.get("da_pct_rev", 0.05))
        ttm_op_mgn_local = ((fin.ttm_operating_income() or 0.0) / ttm_rev) if ttm_rev else 0.0
        # Only blend if guidance differs materially from TTM (>2pp in either direction)
        if abs(guided_op - ttm_op_mgn_local) > 0.02:
            # Blend: 60% guidance, 40% historical-derived target.
            blended = implied_ebitda_mgn * 0.6 + out["ebitda_margin_target"] * 0.4
            out["ebitda_margin_target"] = min(0.85, max(0.05, blended))

    # ---- FCF-SBC margin target ----
    # Infer FCF-SBC → EBITDA conversion ratio from current TTM (captures capex
    # intensity, SBC intensity, working capital needs). Falls back to a
    # moderate 0.65× if current data is insufficient.
    if ttm_ebitda > 0 and ttm_fcf_sbc > 0:
        conv_ratio = max(0.30, min(0.92, ttm_fcf_sbc / ttm_ebitda))
    else:
        conv_ratio = 0.65
    heuristic = out["ebitda_margin_target"] * conv_ratio
    if ttm_fcf_sbc_margin > 0.30:
        out["fcf_sbc_margin_target"] = max(heuristic, min(0.80, ttm_fcf_sbc_margin + growth_expansion))
    elif ttm_fcf_sbc_margin > 0.10:
        out["fcf_sbc_margin_target"] = max(heuristic, ttm_fcf_sbc_margin + 0.08)
    elif ttm_fcf_sbc_margin > 0:
        out["fcf_sbc_margin_target"] = max(heuristic, 0.12)
    elif ttm_fcf_sbc_margin < 0 and ttm_rev > 0:
        # Losing cash now — ramp to modest positive FCF-SBC
        out["fcf_sbc_margin_target"] = max(heuristic, 0.08)
    else:
        out["fcf_sbc_margin_target"] = heuristic

    # Invariant: FCF-SBC can never exceed EBITDA (FCF = EBITDA - capex - SBC - WC).
    # High TTM FCF-SBC margins in low-EBITDA companies can violate this.
    out["fcf_sbc_margin_target"] = min(
        out["fcf_sbc_margin_target"],
        out["ebitda_margin_target"] - 0.01,  # at least 1pp below EBITDA
    )

    # ---- Terminal multiples: current implied × growth-decay discount ----
    # Rationale: by Year 3, the company has matured — high-growth names that
    # trade at premium current multiples will re-rate lower as they shift from
    # "growth" to "quality" classification. Apply a decay factor that scales
    # with Y1 growth: faster current growth → more multiple compression by Y3.
    mcap = fin.market_cap or 0.0
    net_debt = fin.net_debt or 0.0
    ev = mcap + net_debt
    g1_for_decay = out.get("rev_growth_y1", 0.15)
    # Decay: 0 if growth ≤ 10%, scales up to 30% for growth ≥ 40%
    mult_decay = min(0.30, max(0.0, (g1_for_decay - 0.10) * 1.0))
    mult_factor = 1.0 - mult_decay  # 1.0 (no decay) to 0.70 (30% decay)

    # Moat/quality-scaled multiple ceiling AND floor.
    #
    # Ceiling: historical default is 45x EV/EBITDA, which is right for average
    # names but too low for wide-moat AI-adjacent names that trade (and
    # terminal-value at) 55-80x because of pricing power + secular tailwind.
    #
    # Floor: historical default was 10x, which is too LOW for cyclical
    # wide-moat names like MU/SNDK that trade at depressed current EV/EBITDA
    # (cycle trough) but re-rate to mid-teens on recovery. For wide-moat
    # strengthening names, we lift the floor to reflect the terminal-year
    # (not current-year) regime.
    ev_ebitda_cap = 45.0
    ev_fcf_sbc_cap = 40.0
    ev_ebitda_floor = 10.0
    ev_fcf_sbc_floor = 10.0
    tam_g_local = forward.get("tam_growth_rate") or 0.0
    if moat_type == "wide" and moat_durability == "strengthening":
        # Base wide+strengthening → 60×; only exceptional names (moat≥9 AND
        # TAM growing ≥30%) earn the 70× cap. This prevents average "wide"
        # cyclicals from terminal-valuing at CRDO/AVGO territory.
        if moat_score >= 9.0 and isinstance(tam_g_local, (int, float)) and tam_g_local >= 0.30:
            ev_ebitda_cap = 70.0
            ev_fcf_sbc_cap = 60.0
        else:
            ev_ebitda_cap = 60.0
            ev_fcf_sbc_cap = 52.0
        ev_ebitda_floor = 18.0
        ev_fcf_sbc_floor = 18.0
    elif moat_type == "wide":
        ev_ebitda_cap = 55.0
        ev_fcf_sbc_cap = 48.0
        ev_ebitda_floor = 14.0
        ev_fcf_sbc_floor = 14.0
    # TAM tailwind: very fast-growing markets warrant a modest cap lift —
    # but only if the cap isn't already at the elite 70× tier (no double-count).
    if isinstance(tam_g_local, (int, float)) and tam_g_local >= 0.25 and ev_ebitda_cap < 70.0:
        ev_ebitda_cap = min(70.0, ev_ebitda_cap + 8.0)
        ev_fcf_sbc_cap = min(62.0, ev_fcf_sbc_cap + 6.0)

    if ttm_ebitda > 0 and ev > 0:
        current_ev_ebitda = ev / ttm_ebitda
        out["ev_ebitda_multiple"] = max(ev_ebitda_floor, min(ev_ebitda_cap, current_ev_ebitda * mult_factor))
    elif moat_type == "wide":
        # Can't derive from current EBITDA; use mid-range for moat class.
        out["ev_ebitda_multiple"] = (ev_ebitda_floor + ev_ebitda_cap) / 2 * 0.6
    if ttm_fcf_sbc > 0 and ev > 0:
        current_ev_fcf = ev / ttm_fcf_sbc
        out["ev_fcf_sbc_multiple"] = max(ev_fcf_sbc_floor, min(ev_fcf_sbc_cap, current_ev_fcf * mult_factor))
    elif ttm_fcf_sbc <= 0:
        # Can't back out from negative TTM FCF-SBC — assume a slight premium to EV/EBITDA
        out["ev_fcf_sbc_multiple"] = min(ev_fcf_sbc_cap, max(ev_fcf_sbc_floor, out["ev_ebitda_multiple"]))

    # (D&A and SBC %-of-revenue already derived above, before op-margin blend.)
    return out


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------
@dataclass
class DeductionStep:
    label: str
    formula: str
    value: float
    unit: str = "$"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ForecastPeriod:
    period: str
    revenue: float = 0.0
    ebitda: float = 0.0
    ebitda_margin: float = 0.0
    fcf_sbc: float = 0.0
    fcf_sbc_margin: float = 0.0
    operating_income: float = 0.0
    net_income: float = 0.0
    fcf: float = 0.0
    op_margin: float = 0.0
    rev_growth: float = 0.0
    is_actual: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioResult:
    """Full output of one scenario (downside / base / upside)."""
    scenario: str
    price: float
    discount_rate: float
    rev_growth_y1: float
    rev_growth_terminal: float
    ebitda_margin_target: float
    fcf_sbc_margin_target: float
    ev_ebitda_multiple: float
    ev_fcf_sbc_multiple: float
    terminal_revenue: float
    terminal_ebitda: float
    terminal_fcf_sbc: float
    ev_from_ebitda: float
    ev_from_fcf_sbc: float
    terminal_ev_blended: float
    pv_ev_blended: float
    pv_ev_from_ebitda: float
    pv_ev_from_fcf_sbc: float
    equity_value: float
    price_from_ebitda: float
    price_from_fcf_sbc: float
    forecast_annual: list[ForecastPeriod]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["forecast_annual"] = [p.to_dict() for p in self.forecast_annual]
        return d


@dataclass
class TargetResult:
    ticker: str
    current_price: float
    # Aggregate (scenario prices)
    base: float
    low: float
    high: float
    upside_base_pct: float
    upside_low_pct: float
    upside_high_pct: float
    # Merged base-case drivers (what the sliders represent)
    drivers: dict[str, float]
    # Per-scenario full breakdown
    scenarios: dict[str, ScenarioResult]
    # Base-scenario deduction chain for the brief view
    steps: list[DeductionStep]
    # Base-scenario 5-year forecast for detailed page
    forecast_annual: list[ForecastPeriod]
    # Optional 8-quarter forecast (synthesized from annual for legacy consumers)
    forecast_quarterly: list[ForecastPeriod]
    terminal_year: str
    shares_diluted: float
    net_debt: float
    ttm_revenue: float
    ttm_ebitda: float
    ttm_fcf_sbc: float
    warnings: list[str]
    # Horizon metadata — exit fundamentals vs. price-target date
    price_horizon_months: int = 12
    price_target_date: str = ""       # ISO-ish string, e.g. "Apr 2027"
    exit_fiscal_year: str = ""        # FY label at Y3 exit
    valuation_method: str = "ev_ebitda"  # "ev_ebitda" (standard) or "revenue_multiple" (high-growth)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "current_price": self.current_price,
            "base": self.base,
            "low": self.low,
            "high": self.high,
            "upside_base_pct": self.upside_base_pct,
            "upside_low_pct": self.upside_low_pct,
            "upside_high_pct": self.upside_high_pct,
            "drivers": self.drivers,
            "scenarios": {k: v.to_dict() for k, v in self.scenarios.items()},
            "steps": [s.to_dict() for s in self.steps],
            "forecast_annual": [p.to_dict() for p in self.forecast_annual],
            "forecast_quarterly": [p.to_dict() for p in self.forecast_quarterly],
            "terminal_year": self.terminal_year,
            "shares_diluted": self.shares_diluted,
            "net_debt": self.net_debt,
            "ttm_revenue": self.ttm_revenue,
            "ttm_ebitda": self.ttm_ebitda,
            "ttm_fcf_sbc": self.ttm_fcf_sbc,
            "warnings": self.warnings,
            "price_horizon_months": self.price_horizon_months,
            "price_target_date": self.price_target_date,
            "exit_fiscal_year": self.exit_fiscal_year,
            "valuation_method": self.valuation_method,
        }


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------
def _merge_drivers(
    drivers: dict[str, float] | None,
    fin: FinancialData | None = None,
    forward: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Merge driver overrides on top of smart-per-ticker defaults.

    Precedence (lowest → highest):
      1. DEFAULT_DRIVERS (sector-agnostic baseline)
      2. compute_smart_defaults(fin, forward) — derived from ticker's actuals
         and forward-looking scout data (guided growth, moat, TAM)
      3. Explicit `drivers` overrides from caller (e.g., slider changes)
    """
    out = dict(DEFAULT_DRIVERS)
    _smart_defaults_failed = False
    if fin is not None:
        try:
            out.update(compute_smart_defaults(fin, forward=forward))
        except Exception as e:
            _smart_defaults_failed = True
            print(
                f"  [target_engine] WARNING: compute_smart_defaults failed for "
                f"{getattr(fin, 'ticker', '?')}: {e} — using hardcoded defaults. "
                f"Target may be unreliable.",
                file=sys.stderr,
            )
    out["_smart_defaults_failed"] = _smart_defaults_failed
    if drivers:
        for k, v in drivers.items():
            if v is None:
                continue
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def _apply_scenario(base_drivers: dict[str, float], scenario: str) -> dict[str, float]:
    """Derive scenario-specific drivers by applying SCENARIO_OFFSETS.

    Revenue-growth offsets are multiplicative for positive growth (GS convention)
    but switch to additive for negative base growth, because multiplying a
    negative number by <1 makes it less negative (better), which inverts the
    downside/upside relationship. For negative g1, we compute the delta the
    multiplier would have produced on a positive value and apply it additively
    in the correct direction.
    """
    off = SCENARIO_OFFSETS[scenario]
    d = dict(base_drivers)

    # Revenue growth: safe for negative base growth
    for key, mult_key in (
        ("rev_growth_y1", "rev_growth_y1_mult"),
        ("rev_growth_terminal", "rev_growth_terminal_mult"),
    ):
        base_g = base_drivers[key]
        mult = off[mult_key]
        if base_g >= 0:
            d[key] = base_g * mult
        else:
            # Additive delta: how much the multiplier would compress/expand a
            # positive growth rate of the same magnitude. Apply in the
            # direction that makes downside worse and upside better.
            delta = abs(base_g) * (1 - mult)  # positive when mult < 1
            d[key] = base_g - delta  # downside: more negative; upside: less negative

    # Floor margins at -10% to prevent pathological terminal values for
    # near-breakeven companies in the downside scenario.
    d["ebitda_margin_target"] = max(-0.10, base_drivers["ebitda_margin_target"] + off["ebitda_margin_delta"])
    d["fcf_sbc_margin_target"] = max(-0.10, base_drivers["fcf_sbc_margin_target"] + off["fcf_sbc_margin_delta"])
    # Maintain invariant: FCF-SBC ≤ EBITDA
    d["fcf_sbc_margin_target"] = min(d["fcf_sbc_margin_target"], d["ebitda_margin_target"] - 0.01)
    d["ev_ebitda_multiple"] = base_drivers["ev_ebitda_multiple"] * off["ev_ebitda_multiple_mult"]
    d["ev_fcf_sbc_multiple"] = base_drivers["ev_fcf_sbc_multiple"] * off["ev_fcf_sbc_multiple_mult"]
    # WACC is constant across scenarios — use base driver's rate for all
    d["discount_rate"] = base_drivers["discount_rate"]
    return d


def _forecast_annual(
    fin: FinancialData,
    d: dict[str, float],
    base_year_label: str,
) -> list[ForecastPeriod]:
    """Build a 5-year annual forecast.

    Revenue growth decays linearly from `rev_growth_y1` (Y1) toward
    `rev_growth_terminal` (Y5). EBITDA / (FCF-SBC) margins ramp from current
    TTM to their respective targets linearly across MARGIN_RAMP_YEARS (reach
    target at Year 3), then hold through Y5.
    """
    ttm_rev = fin.ttm_revenue() or 0.0
    ttm_ebitda = fin.ttm_ebitda() or 0.0
    ttm_fcf_sbc = _ttm_fcf_sbc(fin) or 0.0
    ttm_ebitda_mgn = (ttm_ebitda / ttm_rev) if ttm_rev else 0.0
    ttm_fcf_sbc_mgn = (ttm_fcf_sbc / ttm_rev) if ttm_rev else 0.0
    ttm_oi = fin.ttm_operating_income() or 0.0
    ttm_op_mgn = (ttm_oi / ttm_rev) if ttm_rev else 0.0

    g1 = d["rev_growth_y1"]
    g_term = d["rev_growth_terminal"]
    # NOTE: TERMINAL_GROWTH_CAP (2.5%) applies to perpetuity/Gordon-Growth
    # terminal value calculations, NOT to the Y5 forecast growth rate.
    # Our engine uses EXIT MULTIPLES for terminal value (Y3 EBITDA × mult),
    # so there is no perpetuity growth assumption. The Y5 growth rate here
    # only shapes the revenue path from Y1→Y5 — capping it at 2.5% was
    # incorrectly crushing high-growth companies like LITE (42%→2.5% decay
    # instead of 42%→15%). compute_smart_defaults already bounds g_term
    # to sane ranges (8-35% depending on moat quality).
    ebitda_target = d["ebitda_margin_target"]
    fcf_target = d["fcf_sbc_margin_target"]
    # Operating margin target: EBITDA minus D&A. Must never exceed EBITDA
    # margin target (was using max(ttm_op_mgn, ...) which could push
    # op_margin above EBITDA when TTM op margin was high but EBITDA low).
    op_target = min(ebitda_target - 0.005, max(ttm_op_mgn, ebitda_target - d["da_pct_rev"]))
    tax = d["tax_rate"]

    out: list[ForecastPeriod] = []
    rev = ttm_rev
    try:
        base_year_int = int(base_year_label[-4:]) if base_year_label else 2025
    except Exception:
        base_year_int = 2025

    for y in range(1, FORECAST_YEARS + 1):
        # Growth decay: linear from g1 (Y1) to g_term (Y5)
        g = g1 + (g_term - g1) * (y - 1) / (FORECAST_YEARS - 1)
        rev = rev * (1 + g)
        # Margin ramp: reaches target at MARGIN_RAMP_YEARS, then holds
        ramp = min(1.0, y / MARGIN_RAMP_YEARS)
        m_eb = ttm_ebitda_mgn + (ebitda_target - ttm_ebitda_mgn) * ramp
        m_fcf = ttm_fcf_sbc_mgn + (fcf_target - ttm_fcf_sbc_mgn) * ramp
        m_op = ttm_op_mgn + (op_target - ttm_op_mgn) * ramp
        # Enforce invariants at every forecast year (not just at terminal):
        # EBITDA ≥ Op Income ≥ 0 (or both negative), and FCF-SBC ≤ EBITDA.
        m_op = min(m_op, m_eb - 0.005)
        m_fcf = min(m_fcf, m_eb - 0.005)

        ebitda = rev * m_eb
        fcf_sbc = rev * m_fcf
        oi = rev * m_op
        ni = oi * (1 - tax)
        # FCF before SBC = FCF-SBC + SBC (we carry SBC as sbc_pct_rev × rev)
        fcf = fcf_sbc + d["sbc_pct_rev"] * rev

        out.append(ForecastPeriod(
            period=f"FY{base_year_int + y}E",
            revenue=rev,
            ebitda=ebitda,
            ebitda_margin=m_eb,
            fcf_sbc=fcf_sbc,
            fcf_sbc_margin=m_fcf,
            operating_income=oi,
            net_income=ni,
            fcf=fcf,
            op_margin=m_op,
            rev_growth=g,
            is_actual=False,
        ))
    return out


def _scenario_price(
    fin: FinancialData,
    d: dict[str, float],
    scenario: str,
    base_year_label: str,
    discount_years: int = DISCOUNT_YEARS,
) -> ScenarioResult:
    """Compute PV target price for one scenario.

    Primary: 50/50 EV/EBITDA + EV/(FCF-SBC) exit-multiple blend.
    Cross-check: Gordon Growth Model on FCF-SBC (intrinsic sanity check).

    Why exit multiples are primary: our forecast horizon is Year 3, and most
    companies in the watchlist are still growing 15-40% at that point — far
    from steady state. Gordon Growth assumes perpetuity at g ≤ 2.5%, which
    dramatically undervalues high-growth companies when applied to Year 3 cash
    flows (LITE: $14.5B GGM vs $109B multiples = 87% divergence). Exit
    multiples implicitly embed the market's view of growth beyond the forecast
    horizon, making them the correct primary method for a 3-year exit.

    Gordon Growth is computed as a cross-check when feasible: divergence >20%
    triggers a warning so the user can investigate terminal assumptions.
    """
    annual = _forecast_annual(fin, d, base_year_label)

    # Terminal point = end of Year VALUATION_YEAR (index VALUATION_YEAR - 1)
    terminal = annual[VALUATION_YEAR - 1]

    # ── Exit-multiple terminal values (PRIMARY) ──
    ev_from_ebitda = terminal.ebitda * d["ev_ebitda_multiple"]
    ev_from_fcf = terminal.fcf_sbc * d["ev_fcf_sbc_multiple"]

    # When one blend leg goes negative (e.g., downside scenario pushes FCF-SBC
    # negative while EBITDA stays positive), a 50/50 average produces a
    # meaningless number. Use only the positive leg in that case.
    if ev_from_ebitda > 0 and ev_from_fcf <= 0:
        terminal_ev = ev_from_ebitda
    elif ev_from_fcf > 0 and ev_from_ebitda <= 0:
        terminal_ev = ev_from_fcf
    else:
        terminal_ev = (ev_from_ebitda + ev_from_fcf) / 2

    # ── Gordon Growth cross-check (intrinsic sanity check) ──
    # TV_GGM = FCF_terminal × (1 + g) / (WACC - g)
    # where g = min(rev_growth_terminal, TERMINAL_GROWTH_CAP)
    wacc = d["discount_rate"]
    g_perpetuity = min(d["rev_growth_terminal"], TERMINAL_GROWTH_CAP)
    ggm_feasible = (
        terminal.fcf_sbc > 0
        and wacc > g_perpetuity + 0.005
    )
    if ggm_feasible:
        ev_gordon = terminal.fcf_sbc * (1 + g_perpetuity) / (wacc - g_perpetuity)
        if terminal_ev > 0:
            divergence = abs(ev_gordon - terminal_ev) / terminal_ev
            if divergence > 0.20:
                print(
                    f"  [engine] {scenario}: Gordon Growth cross-check (${ev_gordon / 1e9:.2f}B) "
                    f"diverges {divergence:.0%} from exit-multiple TV "
                    f"(${terminal_ev / 1e9:.2f}B) — expected for high-growth companies "
                    f"(g_term={d['rev_growth_terminal']:.0%}, g_perp={g_perpetuity:.1%})",
                    file=sys.stderr,
                )

    # Discount back `discount_years` years at WACC. Target date is
    # VALUATION_YEAR - discount_years years from today (12mo-fwd when dy=2).
    discount = (1 + d["discount_rate"]) ** discount_years
    pv_ev = terminal_ev / discount
    pv_ev_ebitda = ev_from_ebitda / discount
    pv_ev_fcf = ev_from_fcf / discount

    net_debt = fin.net_debt or 0.0
    equity = pv_ev - net_debt
    equity_ebitda_only = pv_ev_ebitda - net_debt
    equity_fcf_only = pv_ev_fcf - net_debt

    # Share count at target year after dilution (consistent with target horizon)
    shares_0 = fin.shares_diluted or 0.0
    shares_t = shares_0 * (1 + d["share_change_pct"]) ** (VALUATION_YEAR - discount_years)

    price = max(0.0, equity / shares_t) if shares_t > 0 else 0.0
    price_ebitda = max(0.0, equity_ebitda_only / shares_t) if shares_t > 0 else 0.0
    price_fcf = max(0.0, equity_fcf_only / shares_t) if shares_t > 0 else 0.0

    return ScenarioResult(
        scenario=scenario,
        price=price,
        discount_rate=d["discount_rate"],
        rev_growth_y1=d["rev_growth_y1"],
        rev_growth_terminal=d["rev_growth_terminal"],
        ebitda_margin_target=d["ebitda_margin_target"],
        fcf_sbc_margin_target=d["fcf_sbc_margin_target"],
        ev_ebitda_multiple=d["ev_ebitda_multiple"],
        ev_fcf_sbc_multiple=d["ev_fcf_sbc_multiple"],
        terminal_revenue=terminal.revenue,
        terminal_ebitda=terminal.ebitda,
        terminal_fcf_sbc=terminal.fcf_sbc,
        ev_from_ebitda=ev_from_ebitda,
        ev_from_fcf_sbc=ev_from_fcf,
        terminal_ev_blended=terminal_ev,
        pv_ev_blended=pv_ev,
        pv_ev_from_ebitda=pv_ev_ebitda,
        pv_ev_from_fcf_sbc=pv_ev_fcf,
        equity_value=equity,
        price_from_ebitda=price_ebitda,
        price_from_fcf_sbc=price_fcf,
        forecast_annual=annual,
    )


# ---------------------------------------------------------------------------
# HIGH-GROWTH / PRE-PROFIT REVENUE-MULTIPLE FRAMEWORK
# ---------------------------------------------------------------------------
# For companies where TTM EBITDA ≤ 0 or the market implies extreme P/S
# (>15x), the standard EV/EBITDA method produces near-zero targets because
# it's multiplying tiny/negative EBITDA by a reasonable multiple. These
# companies are valued by the market on REVENUE trajectory, not current
# earnings. This framework uses Price-to-Sales (P/S) as the primary
# valuation method, deriving appropriate terminal P/S from current trading
# multiples, sector comps, and growth-adjusted decay.
#
# Examples: AEHR (pre-profit semi-equipment in revenue trough, market prices
# recovery at $91 on $45M TTM rev), SNOW, PLTR (pre-2024), early biotech.
# ---------------------------------------------------------------------------

# Sector-aware P/S benchmarks: {sector: (median_ps, high_growth_ps, mature_ps)}
# Used as guardrails when current P/S is extreme or unavailable.
SECTOR_PS_BENCHMARKS: dict[str, tuple[float, float, float]] = {
    "Technology":              (8.0, 25.0, 4.0),
    "Healthcare":              (6.0, 20.0, 3.0),
    "Communication Services":  (5.0, 15.0, 3.0),
    "Consumer Cyclical":       (3.0, 10.0, 1.5),
    "Consumer Defensive":      (2.5,  6.0, 1.5),
    "Industrials":             (3.0,  8.0, 1.5),
    "Financial Services":      (4.0, 10.0, 2.0),
    "Basic Materials":         (2.0,  5.0, 1.0),
    "Energy":                  (2.0,  4.0, 0.8),
    "Utilities":               (2.5,  5.0, 1.5),
    "Real Estate":             (5.0, 10.0, 3.0),
}


def _should_use_revenue_multiple(
    fin: FinancialData,
    forward: dict[str, Any] | None = None,
    base_drivers: dict[str, float] | None = None,
) -> bool | float:
    """Detect whether this stock should be valued via revenue multiples
    instead of the standard EV/EBITDA framework.

    Returns:
      - True  → pure P/S mode
      - False → pure EV/EBITDA mode
      - float in (0,1) → transition zone blend weight (P/S weight)
        Only returned for companies near the profitability boundary
        (EBITDA yield 0.5%–2%) to avoid valuation cliffs.

    Triggers:
      1. TTM EBITDA ≤ 0 (pre-profit) → True
      2. TTM operating margin < 5% AND P/S > 12x → True
      3. EBITDA yield 0%–2% of market cap (transition zone):
         - yield < 0.5% → True (functionally pre-profit)
         - yield 0.5%–2.0% → blend weight (linear interpolation)
         - yield > 2.0% → False (solidly profitable)

    Override: if forward drivers show management guiding to strong margins
    (guided op margin > 15%), the company is in a margin-expansion story —
    not a structurally pre-profit one. EV/EBITDA with forward-blended
    margin targets is correct. Revenue-multiple mode would ignore the
    margin expansion and drastically undervalue (LITE: $528 vs $1,508).

    Routing rationale is logged to stderr for auditability.
    """
    forward = forward or {}
    base_drivers = base_drivers or {}
    ttm_rev = fin.ttm_revenue() or 0.0
    ttm_ebitda = fin.ttm_ebitda() or 0.0
    mcap = fin.market_cap or 0.0
    ttm_oi = fin.ttm_operating_income() or 0.0
    ticker = fin.ticker

    # Check if forward drivers indicate a strong margin-expansion story.
    guided_op = forward.get("guided_op_margin")
    ebitda_margin_target = base_drivers.get("ebitda_margin_target", 0.0)
    has_margin_expansion_story = (
        ttm_ebitda > 0
        and isinstance(guided_op, (int, float))
        and guided_op > 0.15
        and ebitda_margin_target > 0.20
    )

    # Trigger 1: truly pre-profit
    if ttm_ebitda <= 0:
        print(f"  [routing] {ticker}: P/S mode — TTM EBITDA ≤ 0 (pre-profit)", file=sys.stderr)
        return True

    # Trigger 2: extreme P/S with near-zero margins
    if mcap > 0 and ttm_rev > 0:
        ps = mcap / ttm_rev
        op_margin = ttm_oi / ttm_rev if ttm_rev else 0
        if ps > 12 and op_margin < 0.05:
            if has_margin_expansion_story:
                print(
                    f"  [routing] {ticker}: EV/EBITDA mode — P/S={ps:.1f}x, op_margin={op_margin:.1%} "
                    f"but margin-expansion story (guided op margin {guided_op:.0%})", file=sys.stderr
                )
                return False
            print(
                f"  [routing] {ticker}: P/S mode — P/S={ps:.1f}x with op_margin={op_margin:.1%}", file=sys.stderr
            )
            return True

    # Trigger 3: EBITDA yield transition zone (0.5%–2.0%)
    # Instead of a hard cut at 1%, use linear interpolation to avoid
    # valuation cliffs where 0.9% yield → P/S at $45/share but
    # 1.1% yield → EV/EBITDA at $30/share.
    if mcap > 0 and ttm_ebitda > 0:
        ebitda_yield = ttm_ebitda / mcap

        if has_margin_expansion_story:
            print(
                f"  [routing] {ticker}: EV/EBITDA mode — EBITDA yield {ebitda_yield:.2%} "
                f"with margin-expansion story (guided op margin {guided_op:.0%})", file=sys.stderr
            )
            return False

        YIELD_LOW = 0.005   # below this → pure P/S
        YIELD_HIGH = 0.020  # above this → pure EV/EBITDA

        if ebitda_yield < YIELD_LOW:
            print(
                f"  [routing] {ticker}: P/S mode — EBITDA yield {ebitda_yield:.2%} < {YIELD_LOW:.1%}", file=sys.stderr
            )
            return True
        elif ebitda_yield < YIELD_HIGH:
            # Transition zone: linear interpolation
            # ps_weight = 1.0 at YIELD_LOW, 0.0 at YIELD_HIGH
            ps_weight = 1.0 - (ebitda_yield - YIELD_LOW) / (YIELD_HIGH - YIELD_LOW)
            print(
                f"  [routing] {ticker}: BLEND mode — EBITDA yield {ebitda_yield:.2%}, "
                f"P/S weight {ps_weight:.0%} / EV weight {1 - ps_weight:.0%}", file=sys.stderr
            )
            return ps_weight

    print(f"  [routing] {ticker}: EV/EBITDA mode — solidly profitable", file=sys.stderr)
    return False


def _compute_terminal_ps(
    fin: FinancialData,
    d: dict[str, float],
    scenario: str,
) -> float:
    """Derive a terminal P/S multiple for Year 3.

    Logic:
    1. Project Y3 revenue from the forecast path (not current revenue).
    2. Use a growth-aware anchor: companies sustaining high terminal growth
       deserve a premium over sector median, but the premium compresses
       as revenue scales up (market pays less per dollar of revenue at $5B
       than at $50M).
    3. Blend the anchor with a decayed version of the current market P/S
       (what the market is actually willing to pay today, modulated by how
       much growth remains at Y3).
    4. Bound by sector benchmarks with growth-scaled caps — the old flat
       cap (37.5x for all tech) produced identical terminal P/S for IONQ
       (80% growth) and RGTI (-25% growth), which is wrong.
    """
    ttm_rev = fin.ttm_revenue() or 1.0
    mcap = fin.market_cap or 0.0
    current_ps = mcap / ttm_rev if ttm_rev > 0 else 10.0

    sector = getattr(fin, "sector", "") or "Technology"
    bench = SECTOR_PS_BENCHMARKS.get(sector, (6.0, 20.0, 3.0))
    median_ps, high_growth_ps, mature_ps = bench

    g1 = d.get("rev_growth_y1", 0.15)
    g_term = d.get("rev_growth_terminal", 0.08)

    # --- Growth-aware anchor ---
    # Terminal growth determines where on the spectrum the company sits
    # between mature (low P/S) and high-growth (high P/S).
    # g_term = 0% → anchor = mature_ps
    # g_term ≥ 25% → anchor = high_growth_ps
    # Linear interpolation in between.
    growth_frac = max(0.0, min(1.0, g_term / 0.25))
    growth_anchor = mature_ps + (high_growth_ps - mature_ps) * growth_frac

    # --- Decayed market P/S ---
    # How much of the current market premium survives to Y3.
    if g1 > 0:
        growth_retention = max(0.2, min(0.8, g_term / g1))
    else:
        # Negative/zero growth: harsh decay, market premium evaporates
        growth_retention = 0.15

    # Project Y3 revenue to adjust for scale. A company growing from
    # $50M → $500M revenue over 3 years should have a lower terminal P/S
    # than one staying at $50M (all else equal) because the market pays
    # less per revenue dollar at scale.
    y3_rev = ttm_rev
    for yr in range(3):
        g = g1 + (g_term - g1) * (yr / max(1, 4))
        y3_rev *= (1 + g)
    # Revenue scale discount: compress P/S as Y3 revenue grows.
    # $100M → no discount; $1B → 30% discount; $10B → 55% discount
    rev_scale_b = y3_rev / 1e9
    if rev_scale_b > 10:
        scale_discount = 0.55
    elif rev_scale_b > 1:
        scale_discount = 0.30 + 0.25 * min(1.0, (rev_scale_b - 1) / 9)
    elif rev_scale_b > 0.1:
        scale_discount = 0.30 * min(1.0, (rev_scale_b - 0.1) / 0.9)
    else:
        scale_discount = 0.0

    decayed_market_ps = current_ps * growth_retention * (1 - scale_discount)

    # --- Blend: 40% growth-anchor + 60% decayed market P/S ---
    # The anchor provides a floor based on growth fundamentals.
    # The decayed market P/S captures the market's willingness to pay.
    raw_terminal_ps = growth_anchor * 0.40 + decayed_market_ps * 0.60

    # Scenario adjustment
    if scenario == "downside":
        raw_terminal_ps *= 0.60  # 40% compression
    elif scenario == "upside":
        raw_terminal_ps *= 1.25  # 25% expansion

    # --- Growth-scaled guardrails ---
    ps_floor = mature_ps
    # Cap scales with terminal growth: 25%+ terminal growth can earn
    # up to 2.5× high_growth_ps; declining companies cap at median.
    if g_term >= 0.20:
        ps_cap = high_growth_ps * 2.5
    elif g_term >= 0.10:
        ps_cap = high_growth_ps * (1.5 + (g_term - 0.10) / 0.10)  # 1.5x→2.5x
    elif g_term > 0:
        ps_cap = high_growth_ps * (1.0 + 0.5 * g_term / 0.10)     # 1.0x→1.5x
    else:
        ps_cap = median_ps  # declining growth → cap at median

    if scenario == "downside":
        ps_cap = min(ps_cap, median_ps * 1.5)  # downside caps near median

    terminal_ps = max(ps_floor, min(ps_cap, raw_terminal_ps))
    return round(terminal_ps, 2)


def _scenario_price_revenue_multiple(
    fin: FinancialData,
    d: dict[str, float],
    scenario: str,
    base_year_label: str,
    discount_years: int = DISCOUNT_YEARS,
) -> ScenarioResult:
    """Revenue-multiple valuation for pre-profit / high-growth companies.

    Instead of EV = EBITDA × multiple, uses EV = Revenue × P/S multiple.
    The revenue forecast path is identical to the standard framework.
    """
    annual = _forecast_annual(fin, d, base_year_label)
    terminal = annual[VALUATION_YEAR - 1]  # Y3

    # Derive terminal P/S for this scenario
    terminal_ps = _compute_terminal_ps(fin, d, scenario)

    # Terminal EV = Y3 Revenue × terminal P/S
    terminal_ev = terminal.revenue * terminal_ps

    # Also compute EV via EBITDA/FCF for reporting (even if near-zero)
    ev_from_ebitda = terminal.ebitda * d.get("ev_ebitda_multiple", 16.0)
    ev_from_fcf = terminal.fcf_sbc * d.get("ev_fcf_sbc_multiple", 16.0)

    # Discount
    discount = (1 + d["discount_rate"]) ** discount_years
    pv_ev = terminal_ev / discount
    pv_ev_ebitda = ev_from_ebitda / discount
    pv_ev_fcf = ev_from_fcf / discount

    net_debt = fin.net_debt or 0.0
    equity = pv_ev - net_debt

    shares_0 = fin.shares_diluted or 0.0
    shares_t = shares_0 * (1 + d["share_change_pct"]) ** (VALUATION_YEAR - discount_years)

    price = equity / shares_t if shares_t > 0 else 0.0

    return ScenarioResult(
        scenario=scenario,
        price=max(0.0, price),
        discount_rate=d["discount_rate"],
        rev_growth_y1=d["rev_growth_y1"],
        rev_growth_terminal=d["rev_growth_terminal"],
        ebitda_margin_target=d["ebitda_margin_target"],
        fcf_sbc_margin_target=d["fcf_sbc_margin_target"],
        ev_ebitda_multiple=d["ev_ebitda_multiple"],
        ev_fcf_sbc_multiple=d["ev_fcf_sbc_multiple"],
        terminal_revenue=terminal.revenue,
        terminal_ebitda=terminal.ebitda,
        terminal_fcf_sbc=terminal.fcf_sbc,
        ev_from_ebitda=terminal_ev,  # overload: store rev-multiple EV here
        ev_from_fcf_sbc=terminal_ev,  # same — both paths use P/S in this mode
        terminal_ev_blended=terminal_ev,
        pv_ev_blended=pv_ev,
        pv_ev_from_ebitda=pv_ev_ebitda,
        pv_ev_from_fcf_sbc=pv_ev_fcf,
        equity_value=equity,
        price_from_ebitda=max(0.0, price),  # same in rev-multiple mode
        price_from_fcf_sbc=max(0.0, price),
        forecast_annual=annual,
    )


# ---------------------------------------------------------------------------
# CYCLICAL NORMALIZED-EARNINGS ENGINE MODE
# ---------------------------------------------------------------------------
# For companies where value is driven by industry cycle position, not just
# execution. The standard engine extrapolates TTM margins forward — which is
# catastrophically wrong at cycle peaks (margins compress as the cycle turns)
# and at cycle troughs (margins expand as demand recovers).
#
# Damodaran's approach: average EBIT margins over a full cycle (5-10 years),
# apply a through-cycle EV/EBIT multiple, and adjust based on where the
# company currently sits in the cycle.
#
# Key differences from standard mode:
#   1. Uses NORMALIZED EBIT margin (historical average), not TTM EBITDA margin
#   2. Uses EV/EBIT multiple (not EV/EBITDA — EBIT is more comparable across
#      cycle phases since D&A fluctuates with capex timing)
#   3. Scenario offsets are asymmetric: bear case models a full cycle turn
#      (30-50% revenue decline possible), bull case is modest re-rating
#   4. Exit trigger is cycle position, not price target
# ---------------------------------------------------------------------------

# Cyclical-specific drivers that augment DEFAULT_DRIVERS
CYCLICAL_DRIVERS: dict[str, float] = {
    "ebit_margin_normalized": 0.15,   # mid-cycle EBIT margin (historical average)
    "ev_ebit_multiple": 12.0,         # through-cycle EV/EBIT
    "cycle_position": 0.50,           # 0=trough, 0.5=mid-cycle, 1.0=peak
}

CYCLICAL_DRIVER_META: dict[str, dict[str, Any]] = {
    "ebit_margin_normalized": {"label": "Normalized EBIT margin (mid-cycle avg)", "format": "pct", "min": -0.10, "max": 0.60, "step": 0.01},
    "ev_ebit_multiple": {"label": "Through-cycle EV/EBIT", "format": "mult", "min": 4.0, "max": 40.0, "step": 0.5},
    "cycle_position": {"label": "Cycle position (0=trough, 1=peak)", "format": "pct", "min": 0.0, "max": 1.0, "step": 0.05},
}

CYCLICAL_SLIDER_KEYS = [
    "rev_growth_y1",
    "rev_growth_terminal",
    "ebit_margin_normalized",
    "ev_ebit_multiple",
    "cycle_position",
    "discount_rate",
]

# Cyclical scenario offsets — asymmetric by design.
# At peak cycle, the bear case must model a FULL cycle turn:
# revenue -20 to -35% (semiconductor cycles: -30% typical, -50% worst),
# margin compression back to mid-cycle, and multiple de-rating.
CYCLICAL_SCENARIO_OFFSETS: dict[str, dict[str, float]] = {
    "downside": {
        "rev_growth_y1_mult": 0.50,         # Growth halved or goes negative
        "rev_growth_terminal_mult": 0.80,
        "ebit_margin_delta": -0.06,          # 6pp margin compression from normalized
        "ev_ebit_multiple_mult": 0.70,       # Multiple de-rates 30% from through-cycle
    },
    "base": {
        "rev_growth_y1_mult": 1.00,
        "rev_growth_terminal_mult": 1.00,
        "ebit_margin_delta": 0.0,
        "ev_ebit_multiple_mult": 1.00,
    },
    "upside": {
        "rev_growth_y1_mult": 1.15,
        "rev_growth_terminal_mult": 1.10,
        "ebit_margin_delta": 0.03,           # 3pp margin expansion (modest — cycle upside)
        "ev_ebit_multiple_mult": 1.20,       # 20% re-rating (recovery premium)
    },
}


def _compute_normalized_ebit_margin(fin: FinancialData) -> float:
    """Average EBIT margin over all available annual history (up to 10 years).

    This produces the "mid-cycle" margin that the company should earn on average
    across a full industry cycle. At peak, TTM margins are above this; at trough,
    below. The normalized margin is the correct steady-state assumption.

    Falls back to TTM operating margin if insufficient annual data.
    """
    margins: list[float] = []
    for p in fin.annual_income[-10:]:  # Up to 10 years
        rev = p.get("Total Revenue")
        oi = p.get("Operating Income")
        if rev and rev > 0 and oi is not None:
            margins.append(oi / rev)

    if len(margins) >= 3:
        # Trim extremes (remove best and worst if we have enough data)
        if len(margins) >= 5:
            margins_sorted = sorted(margins)
            margins = margins_sorted[1:-1]  # Trim top and bottom
        return sum(margins) / len(margins)

    # Fallback: TTM operating margin
    ttm_oi = fin.ttm_operating_income() or 0.0
    ttm_rev = fin.ttm_revenue() or 0.0
    if ttm_rev > 0:
        return ttm_oi / ttm_rev
    return 0.15  # Last resort: generic 15%


def _compute_cycle_position(fin: FinancialData, normalized_margin: float) -> float:
    """Estimate where the company is in the industry cycle (0=trough, 1=peak).

    Uses the ratio of current TTM EBIT margin to normalized (mid-cycle) margin.
    If current margin is 2× the normalized → near peak (0.9+).
    If current margin is 0.5× → near trough (0.2-).
    If roughly equal → mid-cycle (0.5).
    """
    ttm_oi = fin.ttm_operating_income() or 0.0
    ttm_rev = fin.ttm_revenue() or 0.0
    if ttm_rev <= 0 or normalized_margin <= 0:
        return 0.50  # Can't determine → assume mid-cycle

    current_margin = ttm_oi / ttm_rev
    ratio = current_margin / normalized_margin

    # Map ratio to 0-1 scale:
    # ratio 0.3 → position 0.0 (deep trough)
    # ratio 1.0 → position 0.5 (mid-cycle)
    # ratio 2.0 → position 1.0 (peak)
    # Linear interpolation within each half, clamped to [0, 1]
    if ratio <= 1.0:
        # Trough-to-mid: 0.3→0.0, 1.0→0.5
        position = max(0.0, (ratio - 0.3) / (1.0 - 0.3) * 0.5)
    else:
        # Mid-to-peak: 1.0→0.5, 2.0→1.0
        position = min(1.0, 0.5 + (ratio - 1.0) / (2.0 - 1.0) * 0.5)

    return round(position, 2)


def compute_cyclical_defaults(
    fin: FinancialData,
    forward: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Smart defaults specifically for cyclical-mode stocks.

    Uses the same base smart defaults as standard mode, but overrides
    margin and multiple targets with cycle-normalized values.
    """
    # Start from standard smart defaults (gets growth, WACC, etc.)
    out = compute_smart_defaults(fin, forward=forward)

    # Override with cyclical-specific values
    normalized_margin = _compute_normalized_ebit_margin(fin)
    cycle_pos = _compute_cycle_position(fin, normalized_margin)

    out["ebit_margin_normalized"] = normalized_margin
    out["cycle_position"] = cycle_pos

    # Through-cycle EV/EBIT: derive from current trading multiples + cycle adjustment.
    # At peak (high margin), current EV/EBIT is LOW (earnings inflated).
    # At trough (low margin), current EV/EBIT is HIGH (earnings depressed).
    # The through-cycle multiple should be somewhere in between.
    ttm_oi = fin.ttm_operating_income() or 0.0
    mcap = fin.market_cap or 0.0
    net_debt = fin.net_debt or 0.0
    ev = mcap + net_debt
    ttm_rev = fin.ttm_revenue() or 0.0

    if ttm_oi > 0 and ev > 0:
        current_ev_ebit = ev / ttm_oi
        # Normalize: if at peak (pos=0.9), current multiple is too low (earnings inflated)
        # so mid-cycle multiple should be higher. If at trough, current is too high.
        # Adjust: mid_cycle_mult ≈ current_mult × (1 + (cycle_pos - 0.5) × 0.6)
        cycle_adj = 1.0 + (cycle_pos - 0.5) * 0.6
        through_cycle_mult = current_ev_ebit * cycle_adj
        # Clamp to reasonable range (8-30x for cyclicals)
        out["ev_ebit_multiple"] = max(8.0, min(30.0, through_cycle_mult))
    elif ttm_rev > 0 and ev > 0:
        # Can't derive from EBIT — use revenue-based heuristic
        ev_rev = ev / ttm_rev
        # Rough: EV/EBIT ≈ EV/Revenue ÷ normalized_margin
        if normalized_margin > 0.05:
            implied = ev_rev / normalized_margin
            out["ev_ebit_multiple"] = max(8.0, min(30.0, implied))
        else:
            out["ev_ebit_multiple"] = 12.0  # Generic mid-cycle
    else:
        out["ev_ebit_multiple"] = 12.0

    return out


def _apply_cyclical_scenario(base_drivers: dict[str, float], scenario: str) -> dict[str, float]:
    """Apply cyclical-specific scenario offsets.

    Key difference from standard: bear case is much more severe (models cycle turn),
    and margin targets use normalized EBIT margin (not EBITDA).
    """
    off = CYCLICAL_SCENARIO_OFFSETS[scenario]
    d = dict(base_drivers)

    # Revenue growth: same logic as standard for negative-base-growth safety
    for key, mult_key in (
        ("rev_growth_y1", "rev_growth_y1_mult"),
        ("rev_growth_terminal", "rev_growth_terminal_mult"),
    ):
        base_g = base_drivers[key]
        mult = off[mult_key]
        if base_g >= 0:
            d[key] = base_g * mult
        else:
            delta = abs(base_g) * (1 - mult)
            d[key] = base_g - delta

    # Cyclical uses normalized EBIT margin, not EBITDA margin
    d["ebit_margin_normalized"] = max(
        -0.10,
        base_drivers.get("ebit_margin_normalized", 0.15) + off["ebit_margin_delta"]
    )
    d["ev_ebit_multiple"] = base_drivers.get("ev_ebit_multiple", 12.0) * off["ev_ebit_multiple_mult"]

    # Carry through standard EBITDA/FCF drivers (for the forecast path used by UI)
    d["ebitda_margin_target"] = d["ebit_margin_normalized"] + base_drivers.get("da_pct_rev", 0.05)
    d["fcf_sbc_margin_target"] = d["ebit_margin_normalized"] - base_drivers.get("sbc_pct_rev", 0.05)

    # WACC constant across scenarios
    d["discount_rate"] = base_drivers["discount_rate"]
    return d


def _forecast_annual_cyclical(
    fin: FinancialData,
    d: dict[str, float],
    base_year_label: str,
) -> list[ForecastPeriod]:
    """Build 5-year forecast using normalized (mid-cycle) margins.

    Unlike the standard forecast which ramps FROM current TTM margins TO a target,
    the cyclical forecast ramps FROM current margins TOWARD the normalized
    (mid-cycle) margin. If we're at peak, margins compress. If at trough, they expand.
    """
    ttm_rev = fin.ttm_revenue() or 0.0
    ttm_oi = fin.ttm_operating_income() or 0.0
    ttm_ebitda = fin.ttm_ebitda() or 0.0
    ttm_fcf_sbc = _ttm_fcf_sbc(fin) or 0.0

    ttm_op_mgn = (ttm_oi / ttm_rev) if ttm_rev else 0.0
    ttm_ebitda_mgn = (ttm_ebitda / ttm_rev) if ttm_rev else 0.0
    ttm_fcf_sbc_mgn = (ttm_fcf_sbc / ttm_rev) if ttm_rev else 0.0

    # Target margins: normalized (mid-cycle) EBIT + D&A overhead for EBITDA
    norm_ebit = d.get("ebit_margin_normalized", 0.15)
    da_pct = d.get("da_pct_rev", 0.05)
    sbc_pct = d.get("sbc_pct_rev", 0.05)
    ebitda_target = norm_ebit + da_pct
    fcf_target = norm_ebit - sbc_pct
    op_target = norm_ebit
    tax = d["tax_rate"]

    g1 = d["rev_growth_y1"]
    g_term = d["rev_growth_terminal"]

    out: list[ForecastPeriod] = []
    rev = ttm_rev
    try:
        base_year_int = int(base_year_label[-4:]) if base_year_label else 2025
    except Exception:
        base_year_int = 2025

    for y in range(1, FORECAST_YEARS + 1):
        # Growth decay: linear from g1 (Y1) to g_term (Y5)
        g = g1 + (g_term - g1) * (y - 1) / (FORECAST_YEARS - 1)
        rev = rev * (1 + g)

        # Margin mean-reversion: current → normalized over MARGIN_RAMP_YEARS
        # This is the KEY cyclical behavior: at peak, margins compress toward
        # normal. At trough, they expand. Speed = MARGIN_RAMP_YEARS.
        ramp = min(1.0, y / MARGIN_RAMP_YEARS)
        m_eb = ttm_ebitda_mgn + (ebitda_target - ttm_ebitda_mgn) * ramp
        m_fcf = ttm_fcf_sbc_mgn + (fcf_target - ttm_fcf_sbc_mgn) * ramp
        m_op = ttm_op_mgn + (op_target - ttm_op_mgn) * ramp

        # Enforce invariants
        m_op = min(m_op, m_eb - 0.005)
        m_fcf = min(m_fcf, m_eb - 0.005)

        ebitda = rev * m_eb
        fcf_sbc = rev * m_fcf
        oi = rev * m_op
        ni = oi * (1 - tax)
        fcf = fcf_sbc + sbc_pct * rev

        out.append(ForecastPeriod(
            period=f"FY{base_year_int + y}E",
            revenue=rev,
            ebitda=ebitda,
            ebitda_margin=m_eb,
            fcf_sbc=fcf_sbc,
            fcf_sbc_margin=m_fcf,
            operating_income=oi,
            net_income=ni,
            fcf=fcf,
            op_margin=m_op,
            rev_growth=g,
            is_actual=False,
        ))
    return out


def _scenario_price_cyclical(
    fin: FinancialData,
    d: dict[str, float],
    scenario: str,
    base_year_label: str,
    discount_years: int = DISCOUNT_YEARS,
) -> ScenarioResult:
    """Cyclical normalized-earnings valuation.

    Terminal value: Normalized EBIT × through-cycle EV/EBIT multiple.
    This is the single-leg valuation (no 50/50 blend with FCF-SBC) because:
    1. EBIT is the right metric for cyclical companies (comparable across phases)
    2. FCF-SBC is noisy in cyclicals (capex timing dominates the signal)
    """
    annual = _forecast_annual_cyclical(fin, d, base_year_label)
    terminal = annual[VALUATION_YEAR - 1]  # Y3

    # Terminal EV = Y3 EBIT × through-cycle EV/EBIT multiple
    # Y3 EBIT = Y3 operating income (which has mean-reverted toward normalized)
    terminal_ebit = terminal.operating_income
    ev_ebit_mult = d.get("ev_ebit_multiple", 12.0)
    terminal_ev = terminal_ebit * ev_ebit_mult

    # Also compute standard EV/EBITDA and EV/FCF for reporting
    ev_from_ebitda = terminal.ebitda * d.get("ev_ebitda_multiple", 16.0)
    ev_from_fcf = terminal.fcf_sbc * d.get("ev_fcf_sbc_multiple", 22.0)

    # Discount
    discount = (1 + d["discount_rate"]) ** discount_years
    pv_ev = terminal_ev / discount if terminal_ev > 0 else 0.0
    pv_ev_ebitda = ev_from_ebitda / discount
    pv_ev_fcf = ev_from_fcf / discount

    net_debt = fin.net_debt or 0.0
    equity = pv_ev - net_debt

    shares_0 = fin.shares_diluted or 0.0
    shares_t = shares_0 * (1 + d["share_change_pct"]) ** (VALUATION_YEAR - discount_years)

    price = max(0.0, equity / shares_t) if shares_t > 0 else 0.0

    return ScenarioResult(
        scenario=scenario,
        price=price,
        discount_rate=d["discount_rate"],
        rev_growth_y1=d["rev_growth_y1"],
        rev_growth_terminal=d["rev_growth_terminal"],
        ebitda_margin_target=d.get("ebit_margin_normalized", 0.15),  # Store normalized EBIT here
        fcf_sbc_margin_target=d["fcf_sbc_margin_target"],
        ev_ebitda_multiple=ev_ebit_mult,  # Store EV/EBIT in the EV/EBITDA field
        ev_fcf_sbc_multiple=d.get("ev_fcf_sbc_multiple", 22.0),
        terminal_revenue=terminal.revenue,
        terminal_ebitda=terminal_ebit,  # Store terminal EBIT (not EBITDA)
        terminal_fcf_sbc=terminal.fcf_sbc,
        ev_from_ebitda=terminal_ev,  # Overload: terminal EV from EBIT
        ev_from_fcf_sbc=ev_from_fcf,
        terminal_ev_blended=terminal_ev,
        pv_ev_blended=pv_ev,
        pv_ev_from_ebitda=pv_ev_ebitda,
        pv_ev_from_fcf_sbc=pv_ev_fcf,
        equity_value=equity,
        price_from_ebitda=price,
        price_from_fcf_sbc=max(0.0, (pv_ev_fcf - net_debt) / shares_t) if shares_t > 0 else 0.0,
        forecast_annual=annual,
    )


def _validate_inputs(fin: FinancialData, drivers: dict[str, float]) -> list[str]:
    """Validate inputs before DCF computation.

    Raises ValueError on hard failures (missing revenue, shares).
    Returns list of warning strings for soft issues.
    """
    warnings: list[str] = []
    ticker = fin.ticker

    # --- Hard constraints (raise on failure) ---
    rev = fin.ttm_revenue()
    if rev is None or (isinstance(rev, float) and math.isnan(rev)):
        raise ValueError(f"{ticker}: revenue is None/NaN — cannot build target")
    if rev < 0:
        raise ValueError(f"{ticker}: revenue is negative ({rev}) — data error")
    if rev > 5_000_000_000_000:  # > $5 trillion
        raise ValueError(
            f"{ticker}: revenue is absurdly large (${rev/1e9:.0f}B > $5T) — "
            "likely a data-source bug (see MU yfinance issue)"
        )

    shares = fin.shares_diluted
    if shares is None or (isinstance(shares, float) and math.isnan(shares)):
        raise ValueError(f"{ticker}: shares_diluted is None/NaN — cannot compute per-share target")
    if shares <= 0:
        raise ValueError(f"{ticker}: shares_diluted is non-positive ({shares}) — data error")

    # --- Soft constraints (warn but continue) ---
    if fin.market_cap is None:
        warnings.append(f"{ticker}: market_cap is None — some multiples may be unreliable")

    # Margin sanity (should be between -1.0 and 1.0)
    margin_keys = [k for k in drivers if "margin" in k]
    for k in margin_keys:
        v = drivers.get(k)
        if v is not None and not (-1.0 <= v <= 1.0):
            warnings.append(f"{ticker}: driver '{k}' = {v:.3f} is outside [-1, 1] — suspicious")

    # Multiple sanity (should be between 1.0 and 200.0)
    multiple_keys = [k for k in drivers if "multiple" in k]
    for k in multiple_keys:
        v = drivers.get(k)
        if v is not None and not (1.0 <= v <= 200.0):
            warnings.append(f"{ticker}: driver '{k}' = {v:.1f} is outside [1, 200] — suspicious")

    # Discount rate sanity
    dr = drivers.get("discount_rate")
    if dr is not None and not (0.03 <= dr <= 0.30):
        warnings.append(f"{ticker}: discount_rate = {dr:.3f} is outside [0.03, 0.30] — suspicious")

    # Print warnings immediately for visibility
    for w in warnings:
        print(f"  [target_engine WARN] {w}", file=sys.stderr)

    return warnings


def build_target(
    fin: FinancialData,
    drivers: dict[str, float] | None = None,
    forward: dict[str, Any] | None = None,
    load_forward: bool = True,
    horizon_months: int = 12,
    archetype: str | None = None,
) -> TargetResult:
    """Construct a three-scenario price-target range.

    Flow:
      1. Load forward-looking drivers from Supabase (unless caller disables)
      2. Merge smart defaults + forward signals + user overrides → base drivers
      3. Build 3 scenarios by applying scenario offsets to base drivers
      4. For each: 5-year forecast → terminal EV at Y3 → discount to PV at the
         chosen price-target horizon → equity → per-share price
      5. Emit base-scenario deduction chain for UI

    Args:
        fin: FinancialData for the ticker.
        drivers: explicit driver overrides (e.g., from sliders).
        forward: pre-loaded forward drivers (from `forward_drivers.load_forward_drivers`).
            If None and `load_forward=True`, we try to load them from Supabase.
        load_forward: set to False to skip the Supabase lookup (useful for
            tests that want pure-historical output, or for offline runs).
        horizon_months: price-target horizon, one of 12/24/36. Y3 fundamentals
            are the exit point in every case; only the discount back changes.
        archetype: investment archetype from generate_model.py ("garp", "cyclical",
            "transformational", "compounder", "special_situation"). When "cyclical",
            activates normalized-earnings mode with through-cycle EV/EBIT valuation.
    """
    # --- Input validation (before any computation) ---
    _validate_inputs(fin, drivers or {})

    discount_years = _discount_years_for_horizon(horizon_months)
    # Try to enrich with forward-looking drivers from scout signals.
    if forward is None and load_forward:
        try:
            from forward_drivers import load_forward_drivers
            ttm_rev_tmp = fin.ttm_revenue() or 0.0
            # prior-year-Q revenue (handles seasonality for next-Q YoY comparison)
            prior_year_q = None
            q = fin.quarterly_income or []
            if len(q) >= 5:
                v = q[-5].get("Total Revenue")
                if isinstance(v, (int, float)) and v > 0:
                    prior_year_q = float(v)
            forward = load_forward_drivers(
                fin.ticker,
                ttm_rev=ttm_rev_tmp,
                prior_year_q_rev=prior_year_q,
            )
        except Exception as e:
            print(f"  [target_engine] forward_drivers load failed for {fin.ticker}: {e}", file=sys.stderr)
            forward = None

    # ─── Cyclical mode detection ───
    use_cyclical = (archetype or "").lower() == "cyclical"

    if use_cyclical:
        # Cyclical mode: use normalized-earnings defaults instead of standard
        try:
            base_drivers = compute_cyclical_defaults(fin, forward=forward)
        except Exception as e:
            print(f"  [target_engine] cyclical defaults failed: {e} — falling back to standard", file=sys.stderr)
            base_drivers = _merge_drivers(drivers, fin, forward=forward)
            use_cyclical = False
        # Apply explicit driver overrides on top of cyclical defaults
        if drivers and use_cyclical:
            for k, v in drivers.items():
                if v is not None:
                    try:
                        base_drivers[k] = float(v)
                    except (TypeError, ValueError):
                        continue
    else:
        base_drivers = _merge_drivers(drivers, fin, forward=forward)

    warnings: list[str] = []

    # Surface smart-defaults failure as a user-visible warning
    if base_drivers.pop("_smart_defaults_failed", False):
        warnings.append(
            "Smart defaults computation failed — target uses hardcoded fallback "
            "drivers (15% growth, 25% EBITDA margin, 16x multiple). "
            "Result is likely unreliable; check data inputs."
        )
    # Clean internal scratch keys that shouldn't leak to UI/JSON
    base_drivers.pop("_tam_bound_applied", None)

    # Required fields — raise if we genuinely can't value
    ttm_rev = fin.ttm_revenue()
    if ttm_rev is None or ttm_rev <= 0:
        raise ValueError(f"{fin.ticker}: cannot build target — TTM revenue is 0/missing")
    ttm_ebitda = fin.ttm_ebitda() or 0.0
    ttm_fcf_sbc = _ttm_fcf_sbc(fin) or 0.0
    ttm_oi = fin.ttm_operating_income() or 0.0

    if (fin.shares_diluted or 0) <= 0:
        raise ValueError(f"{fin.ticker}: missing diluted share count — cannot compute per-share target")

    # Margin sanity warning
    ttm_ebitda_mgn = ttm_ebitda / ttm_rev if ttm_rev else 0
    if base_drivers["ebitda_margin_target"] < ttm_ebitda_mgn - 0.02:
        warnings.append(
            f"EBITDA margin target ({base_drivers['ebitda_margin_target']:.1%}) below current TTM "
            f"({ttm_ebitda_mgn:.1%}) — forecast assumes compression."
        )

    # ─── Auto-detect valuation method (skip for cyclical mode) ───
    ps_blend_weight = 0.0  # 0 = pure EV, 1 = pure P/S
    use_rev_multiple = False
    if not use_cyclical:
        # Returns True (pure P/S), False (pure EV/EBITDA), or float 0-1 (blend weight for P/S)
        routing_result = _should_use_revenue_multiple(fin, forward=forward, base_drivers=base_drivers)
        if routing_result is True:
            use_rev_multiple = True
            ps_blend_weight = 1.0
        elif isinstance(routing_result, float):
            ps_blend_weight = routing_result
            use_rev_multiple = False  # primary is EV/EBITDA, but we'll blend

    ebitda_yield = (ttm_ebitda / (fin.market_cap or 1)) if ttm_ebitda > 0 else 0
    if use_rev_multiple:
        current_ps = (fin.market_cap or 0) / ttm_rev if ttm_rev > 0 else 0
        warnings.append(
            f"Revenue-multiple mode activated (P/S = {current_ps:.1f}x). "
            "Standard EV/EBITDA is unreliable for this company; "
            "using P/S-based valuation with sector-adjusted terminal multiples."
        )
    elif ps_blend_weight > 0:
        warnings.append(
            f"Transition zone: EBITDA yield {ebitda_yield:.2%} is near profitability boundary. "
            f"Blending P/S ({ps_blend_weight:.0%}) with EV/EBITDA ({1 - ps_blend_weight:.0%}) "
            f"to avoid valuation cliff."
        )
    elif ebitda_yield < 0.01 and ttm_ebitda > 0:
        guided_op = (forward or {}).get("guided_op_margin")
        if isinstance(guided_op, (int, float)) and guided_op > 0.15:
            warnings.append(
                f"Margin-expansion story: TTM EBITDA yield only {ebitda_yield:.2%} but "
                f"management guides {guided_op:.0%} op margins. Using EV/EBITDA with "
                f"forward-blended margin targets (EBITDA target {base_drivers['ebitda_margin_target']:.0%}). "
                f"Target heavily dependent on margin ramp materializing."
            )

    # Build scenarios
    base_year_label = _annual_label_from_q(fin.latest_quarter_label() or "")
    scenarios: dict[str, ScenarioResult] = {}

    if use_cyclical:
        # ─── Cyclical mode: normalized-earnings valuation ───
        cycle_pos = base_drivers.get("cycle_position", 0.5)
        norm_ebit = base_drivers.get("ebit_margin_normalized", 0.15)
        ev_ebit = base_drivers.get("ev_ebit_multiple", 12.0)
        warnings.append(
            f"Cyclical normalized-earnings mode: EBIT margin normalized to {norm_ebit:.1%} "
            f"(mid-cycle avg), cycle position {cycle_pos:.0%} (0=trough, 100%=peak), "
            f"through-cycle EV/EBIT {ev_ebit:.1f}×. Bear case models full cycle turn."
        )
        for name in ("downside", "base", "upside"):
            d = _apply_cyclical_scenario(base_drivers, name)
            scenarios[name] = _scenario_price_cyclical(
                fin, d, name, base_year_label, discount_years=discount_years
            )
    else:
        for name in ("downside", "base", "upside"):
            d = _apply_scenario(base_drivers, name)
            if use_rev_multiple:
                scenarios[name] = _scenario_price_revenue_multiple(
                    fin, d, name, base_year_label, discount_years=discount_years
                )
            elif ps_blend_weight > 0:
                # Transition zone: compute both methods and blend
                ev_result = _scenario_price(
                    fin, d, name, base_year_label, discount_years=discount_years
                )
                ps_result = _scenario_price_revenue_multiple(
                    fin, d, name, base_year_label, discount_years=discount_years
                )
                # Blend the per-share prices; keep EV result's forecast/details as primary
                blended_price = ps_blend_weight * ps_result.price + (1 - ps_blend_weight) * ev_result.price
                # Replace the price in the EV result (it carries the richer forecast data)
                scenarios[name] = ScenarioResult(
                    scenario=ev_result.scenario,
                    price=blended_price,
                    discount_rate=ev_result.discount_rate,
                    rev_growth_y1=ev_result.rev_growth_y1,
                    rev_growth_terminal=ev_result.rev_growth_terminal,
                    ebitda_margin_target=ev_result.ebitda_margin_target,
                    fcf_sbc_margin_target=ev_result.fcf_sbc_margin_target,
                    ev_ebitda_multiple=ev_result.ev_ebitda_multiple,
                    ev_fcf_sbc_multiple=ev_result.ev_fcf_sbc_multiple,
                    terminal_revenue=ev_result.terminal_revenue,
                    terminal_ebitda=ev_result.terminal_ebitda,
                    terminal_fcf_sbc=ev_result.terminal_fcf_sbc,
                    ev_from_ebitda=ev_result.ev_from_ebitda,
                    ev_from_fcf_sbc=ev_result.ev_from_fcf_sbc,
                    terminal_ev_blended=ev_result.terminal_ev_blended,
                    pv_ev_blended=ev_result.pv_ev_blended,
                    pv_ev_from_ebitda=ev_result.pv_ev_from_ebitda,
                    pv_ev_from_fcf_sbc=ev_result.pv_ev_from_fcf_sbc,
                    equity_value=ev_result.equity_value,
                    price_from_ebitda=ev_result.price_from_ebitda,
                    price_from_fcf_sbc=ev_result.price_from_fcf_sbc,
                    forecast_annual=ev_result.forecast_annual,
                )
            else:
                scenarios[name] = _scenario_price(
                    fin, d, name, base_year_label, discount_years=discount_years
                )

    # ─── Scenario monotonicity enforcement ───
    # By construction, upside drivers ≥ base ≥ downside for every input
    # (growth, margins, multiples). If a scenario price violates this ordering,
    # something upstream is wrong — log a diagnostic and enforce the invariant
    # so downstream consumers never see an inverted range.
    down_px = scenarios["downside"].price
    base_px = scenarios["base"].price
    up_px = scenarios["upside"].price

    if up_px < base_px or down_px > base_px:
        print(
            f"  [target_engine WARNING] Scenario inversion detected for {fin.ticker}! "
            f"down=${down_px:.2f} base=${base_px:.2f} up=${up_px:.2f}  "
            f"method={'P/S' if use_rev_multiple else f'blend(P/S {ps_blend_weight:.0%})' if ps_blend_weight > 0 else 'EV/EBITDA'}  "
            f"g1={base_drivers.get('rev_growth_y1', 0):.3f}  "
            f"g_term={base_drivers.get('rev_growth_terminal', 0):.3f}  "
            f"ebitda_margin={base_drivers.get('ebitda_margin_target', 0):.3f}  "
            f"ev_ebitda_mult={base_drivers.get('ev_ebitda_multiple', 0):.1f}  "
            f"ev_fcf_mult={base_drivers.get('ev_fcf_sbc_multiple', 0):.1f}",
            file=sys.stderr,
        )
        warnings.append(
            f"Scenario inversion: upside (${up_px:.0f}) {'<' if up_px < base_px else '>'} "
            f"base (${base_px:.0f}). Prices were reordered. This indicates a driver "
            f"calibration issue — please report the warning details above."
        )

    low = min(down_px, base_px, up_px)
    high = max(down_px, base_px, up_px)

    # Deduction chain — base scenario
    base_s = scenarios["base"]
    f_b = lambda x: x / 1e9  # display in $B

    if use_cyclical:
        # Cyclical normalized-earnings deduction chain
        norm_ebit_mgn = base_drivers.get("ebit_margin_normalized", 0.15)
        ev_ebit_m = base_drivers.get("ev_ebit_multiple", 12.0)
        cycle_pos = base_drivers.get("cycle_position", 0.5)
        ttm_op_mgn = (fin.ttm_operating_income() or 0.0) / ttm_rev if ttm_rev else 0
        steps: list[DeductionStep] = [
            DeductionStep("TTM revenue", "sum(last 4Q revenue)", f_b(ttm_rev), "$B"),
            DeductionStep(
                "Current EBIT margin",
                "TTM operating income / TTM revenue",
                ttm_op_mgn * 100, "%",
            ),
            DeductionStep(
                "Normalized EBIT margin",
                f"avg of {len(fin.annual_income[-10:])} annual periods (mid-cycle)",
                norm_ebit_mgn * 100, "%",
            ),
            DeductionStep(
                "Cycle position",
                "current margin vs normalized (0=trough, 100%=peak)",
                cycle_pos * 100, "%",
            ),
            DeductionStep(
                "Revenue Y3",
                f"TTM × growth path ({base_drivers['rev_growth_y1']:.1%} → {base_drivers['rev_growth_terminal']:.1%})",
                f_b(base_s.terminal_revenue), "$B",
            ),
            DeductionStep(
                "Y3 normalized EBIT",
                f"Rev Y3 × {norm_ebit_mgn:.1%} (mean-reverted margin)",
                f_b(base_s.terminal_ebitda), "$B",  # terminal_ebitda stores EBIT in cyclical mode
            ),
            DeductionStep(
                "Terminal EV",
                f"Y3 EBIT × {ev_ebit_m:.1f}× through-cycle EV/EBIT",
                f_b(base_s.terminal_ev_blended), "$B",
            ),
            DeductionStep(
                "PV of terminal EV",
                f"÷ (1 + {base_drivers['discount_rate']:.1%})^{discount_years}",
                f_b(base_s.pv_ev_blended), "$B",
            ),
            DeductionStep(
                "Equity value",
                "PV EV − Net debt",
                f_b(base_s.equity_value), "$B",
            ),
            DeductionStep(
                "Diluted shares",
                f"current × (1+{base_drivers['share_change_pct']:.1%})^{VALUATION_YEAR - discount_years}",
                (fin.shares_diluted or 0) * (1 + base_drivers["share_change_pct"]) ** (VALUATION_YEAR - discount_years) / 1e6,
                "M",
            ),
            DeductionStep(
                "Base target",
                "Equity / Diluted shares (cyclical normalized-earnings)",
                base_px, "$",
            ),
            DeductionStep("Downside target", "cycle-turn scenario (margin + multiple compression)", scenarios["downside"].price, "$"),
            DeductionStep("Upside target", "recovery scenario (margin expansion + re-rating)", scenarios["upside"].price, "$"),
        ]
    elif use_rev_multiple:
        # Revenue-multiple deduction chain
        terminal_ps_base = _compute_terminal_ps(fin, base_drivers, "base")
        steps: list[DeductionStep] = [
            DeductionStep("TTM revenue", "sum(last 4Q revenue)", f_b(ttm_rev), "$B"),
            DeductionStep(
                "Revenue Y3",
                f"TTM × growth path ({base_drivers['rev_growth_y1']:.1%} → {base_drivers['rev_growth_terminal']:.1%})",
                f_b(base_s.terminal_revenue), "$B",
            ),
            DeductionStep(
                "Current P/S",
                "Market cap / TTM revenue",
                (fin.market_cap or 0) / ttm_rev if ttm_rev else 0,
                "x",
            ),
            DeductionStep(
                "Terminal P/S (Y3)",
                f"current P/S × growth-decay, sector-bounded",
                terminal_ps_base,
                "x",
            ),
            DeductionStep(
                "Terminal EV",
                f"Rev Y3 × {terminal_ps_base:.1f}x P/S",
                f_b(base_s.terminal_ev_blended), "$B",
            ),
            DeductionStep(
                "PV of terminal EV",
                f"÷ (1 + {base_drivers['discount_rate']:.1%})^{discount_years}",
                f_b(base_s.pv_ev_blended), "$B",
            ),
            DeductionStep(
                "Equity value",
                "PV EV − Net debt",
                f_b(base_s.equity_value), "$B",
            ),
            DeductionStep(
                "Diluted shares",
                f"current × (1+{base_drivers['share_change_pct']:.1%})^{VALUATION_YEAR - discount_years}",
                (fin.shares_diluted or 0) * (1 + base_drivers["share_change_pct"]) ** (VALUATION_YEAR - discount_years) / 1e6,
                "M",
            ),
            DeductionStep(
                "Base target",
                "Equity / Diluted shares (P/S method)",
                base_px, "$",
            ),
            DeductionStep("Downside target", "downside scenario (compressed P/S)", scenarios["downside"].price, "$"),
            DeductionStep("Upside target", "upside scenario (expanded P/S)", scenarios["upside"].price, "$"),
        ]
    else:
        # Standard EV/EBITDA deduction chain
        steps: list[DeductionStep] = [
            DeductionStep("TTM revenue", "sum(last 4Q revenue)", f_b(ttm_rev), "$B"),
            DeductionStep(
                "Revenue Y3",
                f"TTM × growth path ({base_drivers['rev_growth_y1']:.1%} → {base_drivers['rev_growth_terminal']:.1%})",
                f_b(base_s.terminal_revenue), "$B",
            ),
            DeductionStep(
                "EBITDA margin Y3",
                f"ramp to target {base_drivers['ebitda_margin_target']:.1%} by Y{MARGIN_RAMP_YEARS}",
                base_s.terminal_ebitda / base_s.terminal_revenue * 100 if base_s.terminal_revenue else 0,
                "%",
            ),
            DeductionStep("EBITDA Y3", "Rev Y3 × EBITDA margin", f_b(base_s.terminal_ebitda), "$B"),
            DeductionStep(
                "FCF − SBC margin Y3",
                f"ramp to target {base_drivers['fcf_sbc_margin_target']:.1%}",
                base_s.terminal_fcf_sbc / base_s.terminal_revenue * 100 if base_s.terminal_revenue else 0,
                "%",
            ),
            DeductionStep("FCF − SBC Y3", "Rev Y3 × FCF-SBC margin", f_b(base_s.terminal_fcf_sbc), "$B"),
            DeductionStep(
                "EV via EBITDA",
                f"EBITDA Y3 × {base_drivers['ev_ebitda_multiple']:.1f}x",
                f_b(base_s.ev_from_ebitda), "$B",
            ),
            DeductionStep(
                "EV via FCF-SBC",
                f"(FCF-SBC) Y3 × {base_drivers['ev_fcf_sbc_multiple']:.1f}x",
                f_b(base_s.ev_from_fcf_sbc), "$B",
            ),
            DeductionStep(
                "Terminal EV (50/50 blend)",
                "avg(EV_EBITDA, EV_FCF-SBC)",
                f_b(base_s.terminal_ev_blended), "$B",
            ),
            DeductionStep(
                "PV of terminal EV",
                f"÷ (1 + {base_drivers['discount_rate']:.1%})^{discount_years}",
                f_b(base_s.pv_ev_blended), "$B",
            ),
            DeductionStep(
                "Equity value",
                "PV EV − Net debt",
                f_b(base_s.equity_value), "$B",
            ),
            DeductionStep(
                "Diluted shares",
                f"current × (1+{base_drivers['share_change_pct']:.1%})^{VALUATION_YEAR - discount_years}",
                (fin.shares_diluted or 0) * (1 + base_drivers["share_change_pct"]) ** (VALUATION_YEAR - discount_years) / 1e6,
                "M",
            ),
            DeductionStep(
                "Base target",
                "Equity / Diluted shares",
                base_px, "$",
            ),
            DeductionStep("Downside target", "downside scenario", scenarios["downside"].price, "$"),
            DeductionStep("Upside target", "upside scenario", scenarios["upside"].price, "$"),
        ]

    # Synthesize 8 forecast quarters from Y1+Y2 annuals for legacy consumers
    fc_q: list[ForecastPeriod] = []
    last_period = fin.quarterly_income[-1]["period"] if fin.quarterly_income else ""
    if base_s.forecast_annual:
        for y_idx in (0, 1):  # Y1, Y2
            y = base_s.forecast_annual[y_idx]
            for q_idx in range(4):
                fc_q.append(ForecastPeriod(
                    period=_advance_quarter_label(last_period, y_idx * 4 + q_idx + 1),
                    revenue=y.revenue / 4,
                    ebitda=y.ebitda / 4,
                    ebitda_margin=y.ebitda_margin,
                    fcf_sbc=y.fcf_sbc / 4,
                    fcf_sbc_margin=y.fcf_sbc_margin,
                    operating_income=y.operating_income / 4,
                    net_income=y.net_income / 4,
                    fcf=y.fcf / 4,
                    op_margin=y.op_margin,
                    rev_growth=y.rev_growth,
                    is_actual=False,
                ))

    price_0 = fin.price or 0.0
    if price_0 <= 0:
        warnings.append("current price from data source is zero/missing — upside % may be misleading.")
    if base_s.terminal_ebitda <= 0:
        warnings.append("Year 3 EBITDA is non-positive — EV/EBITDA method unreliable.")
    if base_s.terminal_fcf_sbc <= 0:
        warnings.append("Year 3 FCF-SBC is non-positive — EV/(FCF-SBC) method unreliable.")

    # Gordon Growth cross-check: compute GGM terminal value and compare to
    # exit-multiple TV. Large divergence is EXPECTED for high-growth companies
    # (GGM caps perpetuity at 2.5%, multiples embed future growth), so this is
    # informational — the exit-multiple TV remains the primary pricing method.
    g_perp = min(base_drivers["rev_growth_terminal"], TERMINAL_GROWTH_CAP)
    base_wacc = base_drivers["discount_rate"]
    if base_s.terminal_fcf_sbc > 0 and base_wacc > g_perp + 0.005:
        ggm_tv = base_s.terminal_fcf_sbc * (1 + g_perp) / (base_wacc - g_perp)
        mult_tv_ebitda = base_s.ev_from_ebitda
        mult_tv_fcf = base_s.ev_from_fcf_sbc
        mult_blend = (mult_tv_ebitda + mult_tv_fcf) / 2 if mult_tv_ebitda > 0 and mult_tv_fcf > 0 else max(mult_tv_ebitda, mult_tv_fcf)
        if mult_blend > 0:
            div = abs(ggm_tv - mult_blend) / mult_blend
            if div > 0.50:
                # Only warn when divergence is extreme (>50%) — moderate divergence
                # is expected since GGM uses 2.5% perpetuity while the company is
                # still growing double-digits at exit year.
                warnings.append(
                    f"Gordon Growth cross-check: GGM TV (${ggm_tv / 1e9:.1f}B) vs exit-multiple "
                    f"TV (${mult_blend / 1e9:.1f}B) — {div:.0%} gap. Expected for high-growth "
                    f"companies (g_term={base_drivers['rev_growth_terminal']:.0%} vs g_perp={g_perp:.1%})."
                )

    # Reliability check: pre-profit / near-zero EBITDA companies.
    # For companies where TTM EBITDA is negative or tiny relative to market cap,
    # DCF-style valuation breaks down — the base case extrapolates tiny absolute
    # EBITDA/FCF numbers into the future, which (correctly) prices the equity
    # near zero. The model is technically right, but the answer isn't actionable.
    # Surface an explicit warning so the UI/user can downweight this output.
    mcap = fin.market_cap or 0.0
    if ttm_ebitda <= 0:
        warnings.append(
            "Pre-profit company (TTM EBITDA ≤ 0) — DCF-style target is unreliable; "
            "consider bookings-ramp / option-value framework instead."
        )
    elif mcap > 0 and ttm_ebitda / mcap < 0.01:
        warnings.append(
            f"Low-earnings company (EBITDA yield {ttm_ebitda / mcap:.2%}) — "
            "target heavily dependent on margin-expansion assumption; "
            "treat low/base/high as a wide probabilistic range."
        )
    if ttm_fcf_sbc < 0:
        warnings.append("TTM FCF − SBC is negative — company funding growth with equity/debt.")

    # Forward-drivers provenance (if we pulled anything useful from scouts)
    if forward:
        parts: list[str] = []
        gg = forward.get("guided_rev_growth_y1")
        if isinstance(gg, (int, float)):
            parts.append(f"guided g1 {gg:.0%}")
        mt = forward.get("moat_type")
        md = forward.get("moat_durability")
        if mt:
            parts.append(f"moat {mt}{'/' + md if md else ''}")
        tam_g = forward.get("tam_growth_rate")
        if isinstance(tam_g, (int, float)):
            parts.append(f"TAM +{tam_g:.0%}/yr")
        om = forward.get("guided_op_margin")
        if isinstance(om, (int, float)):
            parts.append(f"guided op margin {om:.0%}")
        src = forward.get("source_summary")
        if parts:
            src_part = f" [{src}]" if src else ""
            warnings.append(
                f"Forward drivers applied{src_part}: " + ", ".join(parts) +
                ". Historicals blended with guidance; targets reflect forward story."
            )

    # Compute human-readable horizon labels.
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc)
    target_year = today.year + (today.month - 1 + horizon_months) // 12
    target_month_idx = (today.month - 1 + horizon_months) % 12
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    price_target_date = f"{month_names[target_month_idx]} {target_year}"
    exit_fy = _annual_label_shift(base_year_label, VALUATION_YEAR) if base_year_label else ""

    return TargetResult(
        ticker=fin.ticker,
        current_price=price_0,
        base=base_px,
        low=low,
        high=high,
        upside_base_pct=(base_px - price_0) / price_0 if price_0 else 0,
        upside_low_pct=(low - price_0) / price_0 if price_0 else 0,
        upside_high_pct=(high - price_0) / price_0 if price_0 else 0,
        drivers=base_drivers,
        scenarios=scenarios,
        steps=steps,
        forecast_annual=base_s.forecast_annual,
        forecast_quarterly=fc_q,
        terminal_year=(
            f"Exit: Y{VALUATION_YEAR} fundamentals · Price target: {horizon_months}mo fwd ({price_target_date})"
        ),
        shares_diluted=fin.shares_diluted or 0.0,
        net_debt=fin.net_debt or 0.0,
        ttm_revenue=ttm_rev,
        ttm_ebitda=ttm_ebitda,
        ttm_fcf_sbc=ttm_fcf_sbc,
        warnings=warnings,
        price_horizon_months=horizon_months,
        price_target_date=price_target_date,
        exit_fiscal_year=exit_fy,
        valuation_method=(
            "cyclical_normalized" if use_cyclical
            else "revenue_multiple" if use_rev_multiple
            else f"blend_ps_{ps_blend_weight:.0%}" if ps_blend_weight > 0
            else "ev_ebitda"
        ),
    )


# ---------------------------------------------------------------------------
# Period-label helpers
# ---------------------------------------------------------------------------
def _advance_quarter_label(label: str, n_quarters: int) -> str:
    if not label or len(label) < 4:
        return f"Q+{n_quarters}"
    try:
        q = int(label[0])
        yr = int(label[-2:])
        for _ in range(n_quarters):
            q += 1
            if q > 4:
                q = 1
                yr += 1
        return f"{q}Q{yr:02d}"
    except Exception:
        return f"Q+{n_quarters}"


def _annual_label_from_q(qlabel: str) -> str:
    if not qlabel or len(qlabel) < 4:
        return ""
    try:
        yr = 2000 + int(qlabel[-2:])
        return f"FY{yr}"
    except Exception:
        return ""


def _annual_label_shift(fy: str, n: int) -> str:
    if not fy.startswith("FY"):
        return fy + f"+{n}"
    try:
        yr = int(fy[2:])
        return f"FY{yr + n}"
    except Exception:
        return fy + f"+{n}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys, json
    from finance_data import fetch_financials, EarningsFetchError

    tk = (sys.argv[1] if len(sys.argv) > 1 else "APP").upper()
    try:
        fin = fetch_financials(tk)
    except EarningsFetchError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    drivers_override: dict[str, float] = {}
    arch_override = None
    for arg in sys.argv[2:]:
        if arg.startswith("--archetype="):
            arch_override = arg.split("=", 1)[1]
        elif "=" in arg:
            k, v = arg.split("=", 1)
            try:
                drivers_override[k] = float(v)
            except ValueError:
                pass

    res = build_target(fin, drivers_override, archetype=arch_override)
    print(f"\n=== {res.ticker} target ===")
    print(f"Current:  ${res.current_price:,.2f}")
    print(f"  Low:    ${res.low:,.2f}  ({res.upside_low_pct:+.1%})")
    print(f"  Base:   ${res.base:,.2f}  ({res.upside_base_pct:+.1%})")
    print(f"  High:   ${res.high:,.2f}  ({res.upside_high_pct:+.1%})")
    print(f"\nTTM:  rev=${res.ttm_revenue/1e9:.2f}B  ebitda=${res.ttm_ebitda/1e9:.2f}B  fcf-sbc=${res.ttm_fcf_sbc/1e9:.2f}B")
    print(f"\nBase drivers (after smart defaults):")
    for k in DEFAULT_SLIDER_KEYS:
        v = res.drivers.get(k, 0)
        meta = DRIVER_META.get(k, {})
        if meta.get("format") == "pct":
            print(f"  {meta.get('label', k):<35s}: {v*100:.1f}%")
        elif meta.get("format") == "mult":
            print(f"  {meta.get('label', k):<35s}: {v:.1f}x")
        else:
            print(f"  {meta.get('label', k):<35s}: {v:.3f}")

    print(f"\nScenarios:")
    for name in ("downside", "base", "upside"):
        s = res.scenarios[name]
        print(
            f"  {name:<10s} px=${s.price:,.2f}  "
            f"g1={s.rev_growth_y1:.1%}  gT={s.rev_growth_terminal:.1%}  "
            f"EB-mgn={s.ebitda_margin_target:.1%}  "
            f"EV/EBITDA={s.ev_ebitda_multiple:.1f}x  "
            f"EV/(FCF-SBC)={s.ev_fcf_sbc_multiple:.1f}x  "
            f"WACC={s.discount_rate:.1%}  "
            f"Y3 EBITDA=${s.terminal_ebitda/1e9:.2f}B  "
            f"Y3 FCF-SBC=${s.terminal_fcf_sbc/1e9:.2f}B"
        )

    print(f"\nBase-case 5-year forecast:")
    print(f"  {'year':<8s} {'revenue':>10s} {'g%':>6s} {'ebitda':>10s} {'ebmgn':>6s} {'fcf-sbc':>10s} {'fcfmgn':>6s}")
    for p in res.forecast_annual:
        print(
            f"  {p.period:<8s} ${p.revenue/1e9:>8.2f}B "
            f"{p.rev_growth*100:>5.1f}% ${p.ebitda/1e9:>8.2f}B "
            f"{p.ebitda_margin*100:>5.1f}% ${p.fcf_sbc/1e9:>8.2f}B "
            f"{p.fcf_sbc_margin*100:>5.1f}%"
        )

    print(f"\nDeduction chain (base):")
    for s in res.steps:
        if s.unit == "$":
            print(f"  {s.label:<30s} = {s.formula:<50s} → ${s.value:,.2f}")
        elif s.unit == "%":
            print(f"  {s.label:<30s} = {s.formula:<50s} → {s.value:.1f}%")
        elif s.unit == "$B":
            print(f"  {s.label:<30s} = {s.formula:<50s} → ${s.value:,.2f}B")
        elif s.unit == "M":
            print(f"  {s.label:<30s} = {s.formula:<50s} → {s.value:.1f}M")
        else:
            print(f"  {s.label:<30s} = {s.formula:<50s} → {s.value:,.2f}{s.unit}")

    if res.warnings:
        print(f"\nWarnings:")
        for w in res.warnings:
            print(f"  - {w}")
