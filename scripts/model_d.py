"""
model_d.py — Optionality / TAM valuation lens (the "buy the vision" frame).

The target engine values proven, near-term earnings with a margin of safety — the
"forty-years-ago" frame (buy a real, working company). That frame structurally
undervalues genuine regime-shift names whose value lives in the right tail: you're
buying a *vision* and underwriting the probability it's realized.

Model D is the complementary lens. It values a name as a probability-weighted set
of TAM-capture paths, with real weight on the right-tail "vision realized" scenario.
It produces an *optionality-adjusted target* that sits ALONGSIDE the engine target —
never replacing it. The two bracket the truth:
    engine target   = the floor / discipline   ("prove it to me")
    Model D target  = the ceiling / vision      ("how big can this get × P(it happens)")

The Baillie-Gifford insight this encodes: a 30% shot at a 5x is worth more than a
near-certain base case, and the conservative engine, by weighting base/bear, misses
it. Model D makes that right-tail value explicit and auditable — it does NOT inflate
a single number; every scenario states its TAM, capture, margin, multiple, and
probability, so the optimism is decomposed, not hand-waved.

Pure + unit-tested. NOT wired into the live pipeline — that's a separate, reviewed
step (it must route by archetype and never silently override the engine's floor).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VisionScenario:
    """One TAM-capture path. All economics are at the forecast horizon."""
    label: str
    prob: float          # 0..1 — probability this path is the one that plays out
    tam_usd: float       # total addressable market at horizon, in $
    capture: float       # company's share of TAM, 0..1
    net_margin: float    # terminal net margin, 0..1
    exit_pe: float       # P/E applied to terminal net earnings


def scenario_value_per_share(s: VisionScenario, shares: float,
                             discount_rate: float, years: float) -> float:
    """Per-share present value if scenario `s` is realized.

    Raises ValueError on nonsensical inputs (a valuation must fail loud, not return
    a silently-wrong number). Equity value is floored at 0 — a loss-making terminal
    means the equity is worthless to a holder, not negative.
    """
    if shares <= 0:
        raise ValueError("shares must be > 0")
    if discount_rate <= -1.0:
        raise ValueError("discount_rate must be > -1.0 (1 + r must be positive)")
    if years < 0:
        raise ValueError("years must be >= 0")
    revenue = s.tam_usd * s.capture
    earnings = revenue * s.net_margin
    equity_value = max(0.0, earnings * s.exit_pe)
    pv = equity_value / ((1.0 + discount_rate) ** years)
    return pv / shares


def optionality_value(scenarios: list[VisionScenario], shares: float,
                      discount_rate: float = 0.12, years: float = 5.0,
                      prob_tolerance: float = 0.01) -> dict:
    """Probability-weighted optionality target across vision scenarios.

    Probabilities MUST sum to ~1.0 — otherwise the target is silently scaled and
    the function raises ValueError. This forces the caller to provide a COMPLETE
    scenario set including the downside/zero outcome (a vision valuation that omits
    the failure case is the bias this lens exists to prevent). Empty list -> zeros.

    Returns the weighted per-share target, the per-scenario breakdown, `prob_total`,
    `top_scenario`, and `vision_ev_share`: the fraction of total expected value
    contributed by the highest-VALUE scenario — i.e. how much of your EV rides on
    the best-case (vision) path. It is LOW when that path is low-probability, which
    is itself informative (the EV is carried by the base, not the dream).
    """
    if not scenarios:
        return {"optionality_target": 0.0, "prob_total": 0.0, "scenarios": [],
                "vision_ev_share": None, "top_scenario": None,
                "discount_rate": discount_rate, "years": years}
    prob_total = sum(s.prob for s in scenarios)
    if abs(prob_total - 1.0) > prob_tolerance:
        raise ValueError(
            f"scenario probabilities must sum to 1.0 (got {prob_total:.3f}); "
            f"include all outcomes, including the downside/zero case"
        )
    rows = []
    weighted = 0.0
    for s in scenarios:
        vps = scenario_value_per_share(s, shares, discount_rate, years)
        contrib = vps * s.prob
        weighted += contrib
        rows.append({
            "label": s.label,
            "prob": round(s.prob, 3),
            "value_per_share": round(vps, 2),
            "contribution": round(contrib, 2),
        })
    top = max(rows, key=lambda r: r["value_per_share"])
    vision_ev_share = round(top["contribution"] / weighted, 3) if weighted > 0 else None
    return {
        "optionality_target": round(weighted, 2),
        "prob_total": round(prob_total, 3),
        "scenarios": rows,
        "top_scenario": top["label"],
        "vision_ev_share": vision_ev_share,
        "discount_rate": discount_rate,
        "years": years,
    }


def bracket(engine_target: float | None, model_d: dict,
            *, floor_horizon_years: float = 1.25) -> dict:
    """Frame the two lenses together: engine = floor, Model D = vision ceiling.

    2026-07-02 frame fix (audit gap e): vision_ceiling is a t=0 PRESENT VALUE
    (terminal equity discounted over `years` at `discount_rate`), while the
    engine floor (risk_adj_target) is an UNDISCOUNTED ~12-18-month forward
    price. Ratio-ing them raw deflated the vision lens by roughly the
    multi-year discount factor — the LITE '0.8x inverted bracket' datum
    (2026-06-26) was substantially this artifact (~1.4x like-for-like).

    The headline `vision_over_floor_x` is now like-for-like: the floor is
    discounted to t=0 over `floor_horizon_years` (default 1.25 = midpoint of
    the 12-18mo thesis horizon) at the SAME rate the vision PV used. The raw
    inputs and the old frame-mismatched ratio stay in the record for audit.
    """
    opt = model_d.get("optionality_target")
    rate = model_d.get("discount_rate", 0.12)
    # Always include the keys (None when the floor is missing or zero —
    # 0 is falsy, so it must be checked explicitly, not lumped with None).
    out = {
        "engine_floor": engine_target,
        "vision_ceiling": opt,
        "vision_over_floor_x": None,       # like-for-like (headline)
        "engine_floor_pv": None,
        "floor_horizon_years": floor_horizon_years,
        "vision_over_floor_x_raw": None,   # pre-2026-07-02 frame-mismatched ratio
    }
    if engine_target is not None and engine_target > 0 and opt is not None:
        floor_pv = engine_target / ((1.0 + rate) ** floor_horizon_years)
        out["engine_floor_pv"] = round(floor_pv, 2)
        out["vision_over_floor_x"] = round(opt / floor_pv, 2) if floor_pv > 0 else None
        out["vision_over_floor_x_raw"] = round(opt / engine_target, 2)
    return out
