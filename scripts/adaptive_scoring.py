#!/usr/bin/env python3
"""
adaptive_scoring.py — Continuous scoring functions that replace binary gates.

Three function shapes:
  1. Sigmoid   — smooth transition between two regimes
  2. Log-decay — size-dependent caps that tighten with scale
  3. Z-score   — sector-relative positioning (Damodaran stats)

Plus:
  - Input-stability EMA tracker for volatile LLM-derived parameters
  - Context builder that assembles sigmoid parameters from company data

Design principle: "Flexible as water, bending to what deserves more
attention." Hard criteria (accounting identities, mathematical impossibilities)
stay binary in target_engine._validate_inputs(). Everything else flows
through continuous functions here.

See docs/Adaptive_Routing_Architecture.docx for the full design.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

# ─── Sector statistics (Damodaran-sourced) ──────────────────────────
_SECTOR_STATS_PATH = Path(__file__).resolve().parent.parent / "config" / "sector_stats.json"
_sector_stats: dict | None = None


def _load_sector_stats() -> dict:
    """Lazy-load sector statistics from config/sector_stats.json."""
    global _sector_stats
    if _sector_stats is None:
        try:
            with open(_SECTOR_STATS_PATH) as f:
                _sector_stats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"  [adaptive] WARNING: Could not load sector stats: {e}")
            _sector_stats = {}
    return _sector_stats


def get_sector_stats(sector: str) -> dict:
    """Return stats for a sector, falling back to 'default'."""
    stats = _load_sector_stats()
    # Try exact match, then lowercase, then default
    if sector in stats:
        return stats[sector]
    sector_lower = sector.lower().replace(" ", "_")
    for key in stats:
        if key.lower() == sector_lower:
            return stats[key]
    return stats.get("default", {})


# ═══════════════════════════════════════════════════════════════════════
# Layer 1: Continuous Scoring Functions
# ═══════════════════════════════════════════════════════════════════════

def sigmoid(x: float, midpoint: float = 0.0, k: float = 1.0) -> float:
    """Parameterized sigmoid: smooth transition centered at midpoint.

    Returns a value in (0, 1).
      - k > 0: increasing (score rises as x increases)
      - k < 0: decreasing (score falls as x increases)
      - |k| controls steepness (higher = sharper transition)

    Unlike a binary gate, a 1pp change in x always produces a
    proportionally small change in the output — no cliffs.
    """
    z = k * (x - midpoint)
    # Clamp to prevent overflow
    z = max(-500.0, min(500.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def log_decay_cap(revenue_billions: float,
                  base: float = 0.80,
                  decay_rate: float = 0.005,
                  floor: float = 0.15) -> float:
    """Size-dependent growth cap: tightens continuously with scale.

    cap = base × exp(-decay_rate × revenue_B) + floor

    Examples (with defaults):
      $1B  → ~79%     $30B  → ~69%     $100B → ~54%
      $200B → ~41%    $500B → ~23%

    No bands, no cliffs. Every additional $1B of revenue slightly
    tightens the cap — the relationship is smooth and monotonic.
    """
    return base * math.exp(-decay_rate * max(0, revenue_billions)) + floor


def z_score(value: float, sector: str, metric: str) -> float:
    """Sector-relative z-score: how many stdevs from the sector median.

    z = (value - sector_median) / sector_stdev

    A company with 15% operating margin in semiconductors (median ~22%,
    stdev ~8%) has z = -0.875. The same 15% in retail (median ~5%,
    stdev ~3%) has z = +3.33. The sigmoid then operates on z rather
    than the raw value — automatically calibrating to sector norms.

    Returns 0.0 if sector stats are unavailable (neutral assumption).
    """
    stats = get_sector_stats(sector)
    metric_stats = stats.get(metric, {})
    median = metric_stats.get("median")
    stdev = metric_stats.get("stdev")

    if median is None or stdev is None or stdev <= 0:
        return 0.0

    return (value - median) / stdev


# ═══════════════════════════════════════════════════════════════════════
# Composite scoring: routing, margins, multiples
# ═══════════════════════════════════════════════════════════════════════

def continuous_routing_score(
    ebitda_yield: float,
    sector: str = "default",
    archetype: str | None = None,
    has_margin_expansion: bool = False,
) -> float:
    """Continuous P/S routing score replacing the stepped transition zone.

    Returns a value in [0, 1] where:
      0.0 = pure EV/EBITDA mode (solidly profitable)
      1.0 = pure P/S mode (structurally pre-profit)
      0.0-1.0 = blend weight (P/S portion)

    Uses sector-relative z-score of EBITDA yield fed through a sigmoid.
    The sigmoid midpoint shifts based on archetype:
      - Cyclical: shift left (lower yield is "normal" at trough)
      - Transformational: shift right (may never have positive EBITDA)
      - Default: no shift

    Margin expansion story acts as a strong pull toward EV/EBITDA
    (reduces P/S weight) but does NOT create a binary gate.
    """
    # Sector-relative EBITDA yield
    z = z_score(ebitda_yield, sector, "ebitda_yield")

    # Archetype midpoint shift (one parameter per archetype, not 396)
    ARCHETYPE_SHIFTS = {
        "cyclical": -0.8,        # Lower yield is normal at trough
        "special_situation": -0.5,
        "garp": 0.0,
        "compounder": 0.3,       # Expect higher yields
        "transformational": 0.6,  # May never have positive EBITDA → P/S is ok
    }
    archetype_lower = (archetype or "").lower()
    midpoint_shift = ARCHETYPE_SHIFTS.get(archetype_lower, 0.0)

    # Sigmoid: negative z (below-sector yield) → higher P/S weight
    # k=2 gives a smooth transition across ~2 standard deviations
    # Midpoint at 0 + archetype shift
    raw_score = sigmoid(z, midpoint=midpoint_shift, k=-2.0)

    # Margin expansion pull: reduce P/S weight by up to 60%
    # This is a damper, not a binary gate. Even with strong margin
    # expansion, a deeply negative EBITDA yield still gets some P/S weight.
    if has_margin_expansion:
        raw_score *= 0.4  # Keep 40% of the P/S signal

    return max(0.0, min(1.0, raw_score))


def continuous_margin_expansion(
    current_margin: float,
    growth_rate: float,
    sector: str = "default",
) -> float:
    """Continuous EBITDA margin expansion (pp) replacing banded steps.

    Expansion = base_expansion + leverage_coeff × max(0, growth - sector_median_growth)

    The expansion scales with how far above sector-average growth
    the company is — faster growers get more operating leverage.
    Capped by distance to sector ceiling (can't expand past 85%).

    Returns expansion in percentage points (e.g., 0.06 = 6pp).
    """
    stats = get_sector_stats(sector)
    sector_growth_median = stats.get("revenue_growth", {}).get("median", 0.10)
    sector_margin_median = stats.get("ebitda_margin", {}).get("median", 0.20)

    # Base expansion: every company gets at least 2pp of margin expansion
    # over a 3-year forecast horizon (cost optimization, scale effects)
    base_expansion = 0.02

    # Leverage coefficient: how much extra margin per 1pp of above-sector growth
    # Calibrated so that 30pp above-sector growth → ~8pp extra expansion
    leverage_coeff = 0.25

    excess_growth = max(0.0, growth_rate - sector_growth_median)
    growth_expansion = leverage_coeff * excess_growth

    # Total expansion, soft-capped at 12pp
    raw_expansion = base_expansion + growth_expansion
    expansion = raw_expansion * sigmoid(raw_expansion, midpoint=0.12, k=-30.0) + \
                0.12 * (1.0 - sigmoid(raw_expansion, midpoint=0.12, k=-30.0))
    # Simplified: just use a smooth min
    expansion = min(0.12, raw_expansion)

    # Distance-to-ceiling damper: expansion shrinks as margin approaches 85%
    ceiling = 0.85
    headroom = max(0.0, ceiling - current_margin)
    expansion = min(expansion, headroom * 0.8)  # Can use 80% of remaining headroom

    return max(0.005, expansion)  # At least 0.5pp expansion


def continuous_margin_target(
    current_margin: float,
    growth_rate: float,
    sector: str = "default",
    guided_margin: float | None = None,
) -> float:
    """Compute EBITDA margin target using continuous expansion.

    Replaces the banded: >60% → X, >40% → Y, >15% → Z, etc.
    """
    expansion = continuous_margin_expansion(current_margin, growth_rate, sector)
    target = current_margin + expansion

    # Forward-guidance blend (if available)
    if guided_margin is not None and 0 < guided_margin < 0.85:
        # 60% guidance, 40% historical-derived (same weights as current engine)
        # Only blend if guidance differs materially from current (>2pp)
        if abs(guided_margin - current_margin) > 0.02:
            target = guided_margin * 0.6 + target * 0.4

    return max(0.05, min(0.85, target))


def continuous_multiple_cap(
    moat_score: float = 5.0,
    tam_growth: float = 0.05,
    revenue_billions: float = 1.0,
    sector: str = "default",
    metric: str = "ev_ebitda",
) -> tuple[float, float]:
    """Continuous EV/EBITDA (or EV/FCF) cap and floor.

    Replaces the stepped: 45x/55x/60x/70x by moat tier.

    Returns (floor, cap) tuple.

    Cap formula:
      base_cap (from sector) × moat_quality_multiplier × tam_boost
      with log-decay compression for very large companies.

    Floor formula:
      sector_median × moat_quality_floor_factor
    """
    stats = get_sector_stats(sector)
    metric_stats = stats.get(metric, {})
    sector_median = metric_stats.get("median", 20.0)
    sector_stdev = metric_stats.get("stdev", 10.0)

    # Base cap: sector median + 2 stdevs (covers ~95% of sector)
    base_cap = sector_median + 2.0 * sector_stdev

    # Moat quality multiplier: sigmoid centered at moat_score=5
    # Low moat (0-3) → ~0.7x base cap
    # Mid moat (4-6) → ~1.0x base cap
    # High moat (7-9) → ~1.3x base cap
    # Elite moat (10) → ~1.4x base cap
    moat_mult = 0.7 + 0.7 * sigmoid(moat_score, midpoint=5.0, k=0.8)

    # TAM growth boost: fast-growing TAMs support higher terminal multiples
    # Smooth function: 0% boost at TAM growth=5%, up to 15% boost at TAM growth=30%+
    tam_boost = 1.0 + 0.15 * sigmoid(tam_growth, midpoint=0.15, k=20.0)

    # Size compression: very large companies get lower caps (harder to grow into multiples)
    size_factor = log_decay_cap(revenue_billions, base=0.3, decay_rate=0.003, floor=0.7)

    cap = base_cap * moat_mult * tam_boost * size_factor
    # Absolute ceiling: no multiple above 80x regardless of context
    cap = min(80.0, max(10.0, cap))

    # Floor: sector median × moat floor factor
    # High moat companies shouldn't re-rate below sector median
    moat_floor_factor = 0.5 + 0.5 * sigmoid(moat_score, midpoint=5.0, k=0.6)
    floor = sector_median * moat_floor_factor
    floor = max(5.0, min(floor, cap - 2.0))  # Floor must be below cap

    return (floor, cap)


def continuous_growth_cap(
    revenue_billions: float,
    moat_type: str = "narrow",
    moat_durability: str = "stable",
    tam_growth: float = 0.05,
) -> float:
    """Continuous Y1 growth cap replacing banded 0.20/0.35/0.55/0.80.

    Uses log-decay anchored by moat and TAM context.
    """
    # Base cap from log-decay on revenue scale
    base_cap = log_decay_cap(revenue_billions, base=0.80, decay_rate=0.005, floor=0.15)

    # Wide-moat companies sustain higher growth longer
    moat_type_lower = (moat_type or "narrow").lower()
    moat_dur_lower = (moat_durability or "stable").lower()

    if moat_type_lower == "wide" and moat_dur_lower == "strengthening":
        base_cap = min(1.20, base_cap * 1.25 + 0.10)
    elif moat_type_lower == "wide":
        base_cap = min(1.00, base_cap * 1.15 + 0.05)

    # TAM tailwind: fast-growing markets add 10pp headroom
    if isinstance(tam_growth, (int, float)) and tam_growth >= 0.20:
        base_cap = min(1.20, base_cap + 0.10)

    return base_cap


# ═══════════════════════════════════════════════════════════════════════
# Projection score: continuous sigmoid replacements
# ═══════════════════════════════════════════════════════════════════════

def projection_score_revenue_growth(rev_growth: float) -> tuple[float, str]:
    """Continuous revenue growth contribution to projection score.

    Replaces stepped: ≥40% → +0.30, ≥25% → +0.20, ≥15% → +0.10, etc.

    Uses sigmoid centered at 15% growth (the "mid-cycle normal" neutral point).
    Range: approximately [-0.25, +0.35] — same dynamic range as the old steps
    but smooth.
    """
    # Sigmoid: rising from ~-0.25 at 0% growth to ~+0.35 at 50%+ growth
    # Midpoint at 15% (neutral), k=8 gives smooth transition
    score = -0.25 + 0.60 * sigmoid(rev_growth, midpoint=0.15, k=8.0)

    # Label for UI
    pct = rev_growth * 100
    if rev_growth >= 0.40:
        label = f"Revenue growth {pct:.0f}% YoY (hypergrowth)"
    elif rev_growth >= 0.25:
        label = f"Revenue growth {pct:.0f}% YoY (high)"
    elif rev_growth >= 0.15:
        label = f"Revenue growth {pct:.0f}% YoY (above-peer)"
    elif rev_growth >= 0.05:
        label = f"Revenue growth {pct:.0f}% YoY (moderate)"
    else:
        label = f"Revenue growth {pct:.0f}% YoY (flat/declining)"

    return (score, label)


def projection_score_forward_pe(fwd_pe: float) -> tuple[float, str]:
    """Continuous forward PE contribution to projection score.

    Replaces stepped: ≥50x → +0.20, ≥35x → +0.10, <15x → -0.20, etc.

    Uses sigmoid centered at 25x (midpoint between value and growth).
    Range: approximately [-0.25, +0.25].
    """
    # Sigmoid: rising from ~-0.25 at PE=5 to ~+0.25 at PE=60+
    score = -0.25 + 0.50 * sigmoid(fwd_pe, midpoint=25.0, k=0.12)

    if fwd_pe >= 50:
        label = f"Forward PE {fwd_pe:.1f}x (market pricing future)"
    elif fwd_pe >= 35:
        label = f"Forward PE {fwd_pe:.1f}x (growth premium)"
    elif fwd_pe >= 20:
        label = f"Forward PE {fwd_pe:.1f}x (reasonable growth)"
    elif fwd_pe >= 15:
        label = f"Forward PE {fwd_pe:.1f}x (muted growth premium)"
    else:
        label = f"Forward PE {fwd_pe:.1f}x (value multiple)"

    return (score, label)


# ═══════════════════════════════════════════════════════════════════════
# Scenario width adaptation (minimal, archetype-based)
# ═══════════════════════════════════════════════════════════════════════

def adaptive_scenario_offsets(
    archetype: str | None = None,
    base_offsets: dict | None = None,
) -> dict[str, dict[str, float]]:
    """Adjust scenario offsets by archetype.

    Cyclicals get wider down-scenarios (deeper troughs).
    Compounders get tighter scenarios (more predictable).
    Others keep base offsets.

    This is a minimal Phase 4 implementation that doesn't require
    earnings surprise data — just archetype classification.
    """
    from target_engine import SCENARIO_OFFSETS
    base = {k: dict(v) for k, v in SCENARIO_OFFSETS.items()}

    archetype_lower = (archetype or "").lower()

    # Archetype-specific width adjustments
    ARCHETYPE_WIDTHS = {
        "cyclical": {
            "downside": {"rev_growth_y1_mult": 0.82, "ev_ebitda_multiple_mult": 0.65},
            "upside": {"rev_growth_y1_mult": 1.15, "ev_ebitda_multiple_mult": 1.20},
        },
        "compounder": {
            "downside": {"rev_growth_y1_mult": 0.92, "ev_ebitda_multiple_mult": 0.80},
            "upside": {"rev_growth_y1_mult": 1.08, "ev_ebitda_multiple_mult": 1.10},
        },
        "transformational": {
            "downside": {"rev_growth_y1_mult": 0.80, "ev_ebitda_multiple_mult": 0.60},
            "upside": {"rev_growth_y1_mult": 1.18, "ev_ebitda_multiple_mult": 1.25},
        },
    }

    adjustments = ARCHETYPE_WIDTHS.get(archetype_lower, {})
    for scenario, overrides in adjustments.items():
        for key, value in overrides.items():
            if key in base[scenario]:
                base[scenario][key] = value

    return base


# ═══════════════════════════════════════════════════════════════════════
# Layer 2: Input-Stability Tracking (EMA)
# ═══════════════════════════════════════════════════════════════════════

class InputStabilityTracker:
    """Exponential moving average tracker for volatile LLM-derived parameters.

    Stable inputs (sector, market_cap, TTM financials) change quarterly at most.
    Volatile inputs (moat_score, archetype, TAM estimate, guided growth) can
    change every pipeline run because they come from LLM calls.

    This tracker:
    1. Maintains an EMA of each volatile parameter
    2. Alerts (returns WARNING) when a parameter jumps >2σ from its trailing average
    3. Returns the smoothed value for use in sigmoid parameterization

    State is stored in a JSON file (no Supabase dependency for this).
    """

    VOLATILE_PARAMS = {
        "moat_score", "moat_durability", "archetype",
        "tam_size_usd", "tam_growth_rate", "guided_rev_growth_y1",
        "guided_op_margin", "business_quality_score",
    }

    ALPHA = 0.3  # EMA smoothing factor (0.3 = recent values weighted ~30%)

    def __init__(self, state_path: str | None = None):
        self._state_path = Path(state_path) if state_path else (
            Path(__file__).resolve().parent.parent / "data" / ".input_stability_state.json"
        )
        self._state: dict[str, dict] = {}
        self._load_state()

    def _load_state(self):
        try:
            if self._state_path.exists():
                with open(self._state_path) as f:
                    self._state = json.load(f)
        except Exception:
            self._state = {}

    def _save_state(self):
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_path, "w") as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            print(f"  [stability] WARNING: Could not save state: {e}")

    def update(self, ticker: str, param: str, value: float) -> dict:
        """Update EMA for a parameter and return stability report.

        Returns:
          {
            "raw": <current value>,
            "smoothed": <EMA value>,
            "alert": True/False (>2σ jump),
            "message": "..." (if alert),
          }
        """
        key = f"{ticker}:{param}"
        state = self._state.get(key, {})

        if not state:
            # First observation — initialize
            self._state[key] = {
                "ema": value,
                "ema_var": 0.0,  # variance EMA
                "count": 1,
            }
            self._save_state()
            return {"raw": value, "smoothed": value, "alert": False}

        old_ema = state["ema"]
        old_var = state.get("ema_var", 0.0)
        count = state.get("count", 1)

        # Update EMA
        new_ema = self.ALPHA * value + (1 - self.ALPHA) * old_ema

        # Update variance EMA (for 2σ detection)
        deviation = value - old_ema
        new_var = self.ALPHA * (deviation ** 2) + (1 - self.ALPHA) * old_var

        # 2σ alert check (need at least 3 observations for meaningful σ)
        alert = False
        message = ""
        if count >= 3:
            sigma = math.sqrt(max(0, new_var))
            if sigma > 0 and abs(deviation) > 2.0 * sigma:
                alert = True
                message = (
                    f"[stability] {ticker} {param}: jumped from EMA {old_ema:.3f} "
                    f"to {value:.3f} (Δ={deviation:+.3f}, σ={sigma:.3f}, "
                    f"{abs(deviation)/sigma:.1f}σ)"
                )
                print(f"  WARNING {message}")

        # Save updated state
        self._state[key] = {
            "ema": new_ema,
            "ema_var": new_var,
            "count": count + 1,
        }
        self._save_state()

        return {
            "raw": value,
            "smoothed": new_ema,
            "alert": alert,
            "message": message,
        }

    def get_smoothed(self, ticker: str, param: str, fallback: float = 0.0) -> float:
        """Get the current smoothed (EMA) value for a parameter."""
        key = f"{ticker}:{param}"
        state = self._state.get(key, {})
        return state.get("ema", fallback)

    def is_volatile(self, param: str) -> bool:
        """Check if a parameter is classified as volatile."""
        return param in self.VOLATILE_PARAMS


# Global tracker instance
_stability_tracker: InputStabilityTracker | None = None


def get_stability_tracker() -> InputStabilityTracker:
    """Get or create the global stability tracker."""
    global _stability_tracker
    if _stability_tracker is None:
        _stability_tracker = InputStabilityTracker()
    return _stability_tracker


# ═══════════════════════════════════════════════════════════════════════
# Context builder: assemble sigmoid parameters from company data
# ═══════════════════════════════════════════════════════════════════════

def build_adaptive_context(
    ticker: str,
    sector: str,
    archetype: str | None,
    moat_score: float = 5.0,
    moat_type: str = "narrow",
    moat_durability: str = "stable",
    tam_growth: float = 0.05,
    revenue_billions: float = 1.0,
    ebitda_yield: float = 0.0,
    growth_rate: float = 0.15,
    guided_op_margin: float | None = None,
    ebitda_margin_target: float = 0.25,
    forward: dict | None = None,
) -> dict:
    """Build the full adaptive context for a stock.

    This is the central integration point: it combines sector z-scores,
    archetype shifts, moat quality, and size scaling into a single
    context dict that the engine uses to parameterize all its scoring
    functions.

    Returns a dict with all computed adaptive parameters.
    """
    forward = forward or {}
    tracker = get_stability_tracker()

    # Track volatile inputs through EMA
    stability_reports = {}
    if moat_score != 5.0:  # Don't track defaults
        stability_reports["moat_score"] = tracker.update(ticker, "moat_score", moat_score)
        moat_score = stability_reports["moat_score"]["smoothed"]
    if tam_growth != 0.05:
        stability_reports["tam_growth"] = tracker.update(ticker, "tam_growth_rate", tam_growth)
        tam_growth = stability_reports["tam_growth"]["smoothed"]

    # Detect margin expansion story (continuous, not binary)
    has_guided_margin = isinstance(guided_op_margin, (int, float)) and guided_op_margin > 0
    margin_expansion_signal = 0.0
    if has_guided_margin:
        margin_expansion_signal += 0.5
    if ebitda_margin_target > 0.20:
        margin_expansion_signal += 0.3
    if growth_rate > 0.20:
        margin_expansion_signal += 0.2
    has_margin_expansion = margin_expansion_signal >= 0.3  # Softer threshold

    # Routing score (continuous)
    routing_score = continuous_routing_score(
        ebitda_yield=ebitda_yield,
        sector=sector,
        archetype=archetype,
        has_margin_expansion=has_margin_expansion,
    )

    # Growth cap (continuous)
    growth_cap = continuous_growth_cap(
        revenue_billions=revenue_billions,
        moat_type=moat_type,
        moat_durability=moat_durability,
        tam_growth=tam_growth,
    )

    # Multiple cap/floor (continuous)
    ev_ebitda_floor, ev_ebitda_cap = continuous_multiple_cap(
        moat_score=moat_score,
        tam_growth=tam_growth,
        revenue_billions=revenue_billions,
        sector=sector,
        metric="ev_ebitda",
    )
    ev_fcf_floor, ev_fcf_cap = continuous_multiple_cap(
        moat_score=moat_score,
        tam_growth=tam_growth,
        revenue_billions=revenue_billions,
        sector=sector,
        metric="ev_fcf",
    )

    # Margin expansion (continuous)
    margin_expansion_pp = continuous_margin_expansion(
        current_margin=max(0, ebitda_yield * 10),  # rough proxy if we don't have margin
        growth_rate=growth_rate,
        sector=sector,
    )

    # Scenario offsets (archetype-adapted)
    scenario_offsets = adaptive_scenario_offsets(archetype=archetype)

    return {
        "routing_score": routing_score,
        "growth_cap": growth_cap,
        "ev_ebitda_floor": ev_ebitda_floor,
        "ev_ebitda_cap": ev_ebitda_cap,
        "ev_fcf_floor": ev_fcf_floor,
        "ev_fcf_cap": ev_fcf_cap,
        "margin_expansion_pp": margin_expansion_pp,
        "has_margin_expansion": has_margin_expansion,
        "margin_expansion_signal": margin_expansion_signal,
        "scenario_offsets": scenario_offsets,
        "sector": sector,
        "archetype": archetype,
        "moat_score_smoothed": moat_score,
        "tam_growth_smoothed": tam_growth,
        "stability_reports": stability_reports,
        # Sigmoid params for logging (prediction_logger needs these)
        "sigmoid_params": {
            "routing_midpoint": 0.0,  # Will be adjusted by archetype
            "routing_k": -2.0,
            "sector": sector,
            "archetype_shift": (archetype or "").lower(),
            "margin_expansion_signal": margin_expansion_signal,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Margin expansion detection (continuous replacement for binary guard)
# ═══════════════════════════════════════════════════════════════════════

def has_margin_expansion_story(
    ttm_ebitda: float,
    guided_op_margin: float | None,
    ebitda_margin_target: float,
    growth_rate: float = 0.0,
) -> tuple[bool, float, str]:
    """Continuous margin-expansion detection replacing the binary guard.

    Returns:
      (is_expansion, signal_strength, detail_string)

    signal_strength is 0.0-1.0:
      0.0 = no evidence of margin expansion
      1.0 = overwhelming evidence

    The boolean is_expansion is True when signal_strength >= 0.3
    (much softer than the old "guided_op > 15% AND ebitda_target > 20%").
    """
    signal = 0.0
    details = []

    if ttm_ebitda > 0:
        signal += 0.15
        details.append("positive TTM EBITDA")

    if isinstance(guided_op_margin, (int, float)) and guided_op_margin > 0:
        # Continuous: more guided margin = stronger signal
        guided_contribution = min(0.40, guided_op_margin * 1.5)  # 10% margin → 0.15, 25% → 0.375
        signal += guided_contribution
        details.append(f"guided op margin {guided_op_margin:.0%}")

    if ebitda_margin_target > 0.10:
        # Continuous: higher target = stronger signal
        target_contribution = min(0.30, (ebitda_margin_target - 0.10) * 1.5)
        signal += target_contribution
        details.append(f"EBITDA target {ebitda_margin_target:.0%}")

    if growth_rate > 0.15:
        # High growth implies operating leverage opportunity
        growth_contribution = min(0.15, (growth_rate - 0.15) * 0.5)
        signal += growth_contribution
        details.append(f"growth {growth_rate:.0%}")

    signal = min(1.0, signal)
    is_expansion = signal >= 0.3
    detail_str = ", ".join(details) if details else "no margin expansion signals"

    return (is_expansion, signal, detail_str)
