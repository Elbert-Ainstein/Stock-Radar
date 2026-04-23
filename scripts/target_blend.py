"""
target_blend.py — Dynamic projection-vs-returns blend for price targets.

Problem we're solving:
  The same +5% event signal means different things for different companies.
  For a revolutionary projection-bet (AMD, LITE AI-infra), events ARE the
  leading evidence that the thesis is playing out — they should nearly fully
  flow into the target. For a mature returns-focused company (AAPL-style
  dividend aristocrat), events are mostly noise around established financials
  — quarterly fundamentals already reflect truth, events should be damped.

Design:
  1. `compute_projection_score()` puts a company on a 0.0 → 1.0 spectrum
     (pure returns/now → pure projection/future) using revenue growth,
     forward PE, user-set tags, and valuation method. Returns the score
     PLUS a structured breakdown of every contributor so the dashboard can
     render exactly why.

  2. `blend_targets()` derives an event_weight from the score and produces
     the final target:
         event_weight = 0.3 + 0.7 × projection_score    # range [0.3, 1.0]
         final_target = base × (1 + criteria_pct + event_weight × event_pct)
     Returns full breakdown (base, criteria component, raw event component,
     weighted event component, final) so the dashboard shows the deduction
     chain, not just a number.

Criteria weighting is NOT scaled here — the user already expresses criterion
importance through critical/important/monitoring tiers (handled in
analyst.evaluate_criteria). We only scale how much event flow adds on top.
"""
from __future__ import annotations


# ═══ Tuning knobs — change here, not inline in analyst ═══

# Projection-score contribution table. Each row: (condition, contribution_pts, label)
# Final score = clamp(0.5 + sum(contributions), 0.0, 1.0).
# 0.5 is the neutral baseline so a company with no strong signal sits mid-spectrum.
PROJECTION_BASELINE = 0.5

# event_weight linearly interpolates from 0.3 (pure returns) to 1.0 (pure projection).
EVENT_WEIGHT_MIN = 0.30
EVENT_WEIGHT_MAX = 1.00


# ═══ Projection-score computation ═══

def compute_projection_score(
    fundamentals_data: dict | None,
    quant_data: dict | None,
    stock_config: dict | None,
) -> dict:
    """Classify a company on the projection-vs-returns spectrum.

    Returns a dict:
      {
        "score": 0.0-1.0,
        "baseline": 0.5,
        "contributors": [
          {"label": "Revenue growth 34% YoY", "delta": +0.20, "source": "fundamentals"},
          ...
        ],
        "final_explanation": "baseline 0.50 + 0.20 + 0.15 − 0.05 = 0.80",
      }

    Score semantics:
      0.0 = pure returns/now (mature cash cow; events are noise)
      0.5 = balanced (default when signals are mixed or missing)
      1.0 = pure projection/future (revolutionary bet; events are leading indicators)
    """
    fundamentals_data = fundamentals_data or {}
    quant_data = quant_data or {}
    stock_config = stock_config or {}

    contributors: list[dict] = []

    # ── Signal 1: Revenue growth YoY ──
    # Strongest driver. Hypergrowth → projection. Flat → returns.
    # Scouts store this inconsistently:
    #   - fundamentals scout:  `revenue_growth_yoy` as fraction (0.34 → 34%)
    #   - quant scout:         `revenue_growth_pct` as percentage-point (34.1 → 34%)
    # Probe both; normalize to a fraction for thresholding.
    rev_growth = _as_float(fundamentals_data.get("revenue_growth_yoy"))
    rev_source = "fundamentals"
    if rev_growth is None:
        rg_pct = _as_float(quant_data.get("revenue_growth_pct"))
        if rg_pct is not None:
            rev_growth = rg_pct / 100.0
            rev_source = "quant"
    # Be defensive: if a value ≥ 1.5 was passed, caller used percentage-points.
    # Normalize so the thresholds stay correct regardless of source.
    if rev_growth is not None and abs(rev_growth) >= 1.5:
        rev_growth = rev_growth / 100.0
    if rev_growth is not None:
        if rev_growth >= 0.40:
            contributors.append({"label": f"Revenue growth {rev_growth*100:.0f}% YoY (hypergrowth)", "delta": +0.30, "source": rev_source})
        elif rev_growth >= 0.25:
            contributors.append({"label": f"Revenue growth {rev_growth*100:.0f}% YoY (high)", "delta": +0.20, "source": rev_source})
        elif rev_growth >= 0.15:
            contributors.append({"label": f"Revenue growth {rev_growth*100:.0f}% YoY (above-peer)", "delta": +0.10, "source": rev_source})
        elif rev_growth < 0.05:
            contributors.append({"label": f"Revenue growth {rev_growth*100:.0f}% YoY (flat/declining)", "delta": -0.20, "source": rev_source})
        elif rev_growth < 0.10:
            contributors.append({"label": f"Revenue growth {rev_growth*100:.0f}% YoY (sub-peer)", "delta": -0.10, "source": rev_source})
        # 10–15% band = no adjustment (mid-cycle normal)

    # ── Signal 2: Forward PE (market's own projection-pricing) ──
    # Market paying >50x forward is telling us it's pricing future. <15 = pricing reality.
    fwd_pe = _as_float(quant_data.get("forward_pe"))
    if fwd_pe is not None and fwd_pe > 0:
        if fwd_pe >= 50:
            contributors.append({"label": f"Forward PE {fwd_pe:.1f}x (market pricing future)", "delta": +0.20, "source": "quant"})
        elif fwd_pe >= 35:
            contributors.append({"label": f"Forward PE {fwd_pe:.1f}x (growth premium)", "delta": +0.10, "source": "quant"})
        elif fwd_pe < 15:
            contributors.append({"label": f"Forward PE {fwd_pe:.1f}x (value multiple)", "delta": -0.20, "source": "quant"})
        elif fwd_pe < 20:
            contributors.append({"label": f"Forward PE {fwd_pe:.1f}x (muted growth premium)", "delta": -0.10, "source": "quant"})
        # 20–35x band = no adjustment (normal growth-at-reasonable-price)

    # ── Signal 3: User-set tags in stocks table ──
    tags = stock_config.get("tags") or []
    tag_set = {str(t).lower() for t in tags if t}
    projection_tags = {"revolutionary", "hypergrowth", "ai_infrastructure", "pre_revenue", "platform", "share_taker", "disruptive"}
    returns_tags = {"value", "dividend_aristocrat", "mature", "cash_cow", "defensive", "utility"}
    hit_proj = sorted(tag_set & projection_tags)
    hit_ret = sorted(tag_set & returns_tags)
    if hit_proj:
        contributors.append({"label": f"User tags: {', '.join(hit_proj)}", "delta": +0.15, "source": "tags"})
    if hit_ret:
        contributors.append({"label": f"User tags: {', '.join(hit_ret)}", "delta": -0.15, "source": "tags"})

    # ── Signal 4: Valuation method hint ──
    # User picked PS → acknowledging revenue-multiple valuation (growth lens).
    # PE → earnings-multiple (maturity lens).
    vm = (stock_config.get("valuation_method") or "").lower()
    if vm == "ps":
        contributors.append({"label": "Valuation method: PS (revenue multiple)", "delta": +0.10, "source": "config"})
    elif vm == "pe":
        contributors.append({"label": "Valuation method: PE (earnings multiple)", "delta": -0.05, "source": "config"})

    # ── Signal 5: Data quality penalties ──
    # The projection score should reflect signal QUALITY, not just PRESENCE.
    # A company with comprehensive but unreliable guidance, or a moat
    # assessment Claude fabricated with high confidence, shouldn't score higher
    # than one with sparse but verified data.

    # 5a. Guidance accuracy: if the company has a history of missing guidance,
    # discount the forward projection weight (guidance is noise, not signal).
    guidance_beat_rate = _as_float(fundamentals_data.get("guidance_beat_rate"))
    if guidance_beat_rate is not None:
        if guidance_beat_rate < 0.40:
            contributors.append({
                "label": f"Poor guidance accuracy ({guidance_beat_rate:.0%} beat rate)",
                "delta": -0.15,
                "source": "fundamentals",
            })
        elif guidance_beat_rate < 0.55:
            contributors.append({
                "label": f"Below-average guidance accuracy ({guidance_beat_rate:.0%} beat rate)",
                "delta": -0.05,
                "source": "fundamentals",
            })

    # 5b. Moat assessment confidence: if multiple sources disagree on moat
    # score (high dispersion), the LLM assessment is unreliable — penalize
    # rather than rewarding the presence of a moat score.
    moat_dispersion = _as_float(fundamentals_data.get("moat_score_dispersion"))
    if moat_dispersion is not None and moat_dispersion > 0.25:
        contributors.append({
            "label": f"High moat-score dispersion ({moat_dispersion:.2f}) — assessment unreliable",
            "delta": -0.10,
            "source": "fundamentals",
        })

    # 5c. TAM estimate quality: if only one source provides TAM data,
    # the estimate is unanchored. Multiple sources with convergence = reliable.
    tam_source_count = fundamentals_data.get("tam_source_count")
    if isinstance(tam_source_count, int) and tam_source_count == 1:
        contributors.append({
            "label": "Single-source TAM estimate (unverifiable)",
            "delta": -0.05,
            "source": "fundamentals",
        })

    # Sum, clamp, build explanation.
    raw_score = PROJECTION_BASELINE + sum(c["delta"] for c in contributors)
    score = max(0.0, min(1.0, raw_score))

    parts = [f"baseline {PROJECTION_BASELINE:.2f}"]
    for c in contributors:
        sign = "+" if c["delta"] >= 0 else "−"
        parts.append(f"{sign} {abs(c['delta']):.2f} ({c['label']})")
    trail = " ".join(parts)
    if raw_score != score:
        trail += f" = {raw_score:+.2f} → clamped to {score:.2f}"
    else:
        trail += f" = {score:.2f}"

    return {
        "score": round(score, 3),
        "baseline": PROJECTION_BASELINE,
        "contributors": contributors,
        "raw_score": round(raw_score, 3),
        "final_explanation": trail,
    }


# ═══ Target blend ═══

def blend_targets(
    base_target: float,
    criteria_pct: float,
    event_pct: float,
    projection_score: float,
) -> dict:
    """Produce the final target as a transparent, auditable blend.

    Formula:
        event_weight = 0.30 + 0.70 × projection_score
        final_target = base × (1 + criteria_pct/100 + event_weight × event_pct/100)

    Returns a dict with the full deduction chain:
      {
        "base_target": 500,
        "criteria_pct": -2.5,
        "event_pct_raw": 11.5,
        "event_weight": 0.86,
        "event_pct_weighted": 9.89,
        "total_adjustment_pct": 7.39,
        "final_target": 537,
        "formula": "$500 × (1 + (−2.5%) + 0.86 × 11.5%) = $537",
      }

    All percentages are in percentage-point terms (e.g. 11.5 means 11.5%,
    not 0.115). Matches the convention already used in analyst.py.
    """
    base = float(base_target or 0)
    crit_pct = float(criteria_pct or 0)
    ev_raw = float(event_pct or 0)
    ps = max(0.0, min(1.0, float(projection_score or 0)))

    event_weight = EVENT_WEIGHT_MIN + (EVENT_WEIGHT_MAX - EVENT_WEIGHT_MIN) * ps
    ev_weighted = ev_raw * event_weight
    total_pct = crit_pct + ev_weighted
    final_target = round(base * (1 + total_pct / 100.0))

    # Human-readable formula string. Handle signs cleanly.
    def _fmt_pct(v: float) -> str:
        return f"{v:+.2f}%".replace("+", "+").replace("-", "−")

    formula = (
        f"${base:,.0f} × (1 + {_fmt_pct(crit_pct)} criteria "
        f"+ {event_weight:.2f} × {_fmt_pct(ev_raw)} events) = ${final_target:,.0f}"
    )

    return {
        "base_target": round(base),
        "criteria_pct": round(crit_pct, 2),
        "event_pct_raw": round(ev_raw, 2),
        "event_weight": round(event_weight, 3),
        "event_pct_weighted": round(ev_weighted, 2),
        "total_adjustment_pct": round(total_pct, 2),
        "final_target": final_target,
        "formula": formula,
    }


# ═══ Utilities ═══

def _as_float(v) -> float | None:
    """Best-effort numeric coercion. Returns None for missing/unparseable."""
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN guard
            return None
        return f
    except (TypeError, ValueError):
        return None


# ═══ CLI demo ═══

if __name__ == "__main__":
    import json
    print("── AMD (projection-heavy) ──")
    amd_ps = compute_projection_score(
        fundamentals_data={"revenue_growth_yoy": 0.34},
        quant_data={"forward_pe": 25.4},
        stock_config={"tags": ["revolutionary", "ai_infrastructure", "share_taker"], "valuation_method": "pe"},
    )
    print(json.dumps(amd_ps, indent=2))
    print(json.dumps(blend_targets(500, 0, 11.5, amd_ps["score"]), indent=2))

    print("\n── Hypothetical mature returns-heavy (KO-style) ──")
    ko_ps = compute_projection_score(
        fundamentals_data={"revenue_growth_yoy": 0.04},
        quant_data={"forward_pe": 22.0},
        stock_config={"tags": ["dividend_aristocrat", "defensive"], "valuation_method": "pe"},
    )
    print(json.dumps(ko_ps, indent=2))
    print(json.dumps(blend_targets(70, 0, 5.0, ko_ps["score"]), indent=2))

    print("\n── LITE (AI-infra growth) ──")
    lite_ps = compute_projection_score(
        fundamentals_data={"revenue_growth_yoy": 0.28},
        quant_data={"forward_pe": 38.0},
        stock_config={"tags": ["ai_infrastructure"], "valuation_method": "pe"},
    )
    print(json.dumps(lite_ps, indent=2))
    print(json.dumps(blend_targets(1500, 0, 2.6, lite_ps["score"]), indent=2))
