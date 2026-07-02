"""trade_gate.py — deterministic, code-side enforcement of the Step-12
risk-adj-EV clamp (thesis_v3.md "RISK-ADJ-EV KILL RULE").

Until 2026-07-02 the clamp table lived only in prompt prose: the code never
recomputed `risk_adj_ev_ratio` (although both operands — risk_adj_target and
spot — are in hand at the call site) and never clamped conviction/position
downward, so a model arithmetic slip or optimistic self-report bypassed the
"HARD GATE" entirely (audit §4.2). This module makes the gate real:

  * recompute the ratio from risk_adj_target / spot,
  * log any discrepancy vs the LLM-emitted value,
  * clamp trade-level conviction and position_size_pct DOWNWARD per the table.

Deliberately relax-nothing: upgrades never happen here (kill_gate.py owns the
archetype-routed relax of a ratio-driven BROKEN, downstream of this clamp).
`strategic_conviction` (Type A, price-independent) is never touched.

Pure, no IO, never raises on bad input — a hard gate must not fail open via
an exception path.
"""

from __future__ import annotations

CONVICTION_RANK = {"BROKEN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}

# (inclusive lower bound of risk_adj_ev_ratio, max conviction, max position %)
# Mirrors the Step-12 table in scripts/prompts/thesis_v3.md verbatim; the
# prompt's "LOW–MEDIUM" band (1.00–1.10) is encoded as max MEDIUM / 15%.
CLAMP_TABLE = (
    (1.25, "HIGH", 35.0),
    (1.10, "MEDIUM", 25.0),
    (1.00, "MEDIUM", 15.0),
    (0.95, "LOW", 10.0),
    (float("-inf"), "BROKEN", 0.0),
)

# Recomputed-vs-emitted ratio differences above this are reported as a
# discrepancy (a rounding difference of ±0.005 is honest arithmetic).
RATIO_DISCREPANCY_TOLERANCE = 0.005


def clamp_for_ratio(ratio: float) -> tuple[str, float]:
    """Return (max_conviction, max_position_pct) for a risk_adj_ev_ratio."""
    for lower, conviction, position in CLAMP_TABLE:
        if ratio >= lower:
            return conviction, position
    return "BROKEN", 0.0  # unreachable; -inf bound catches everything


def _as_float(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # reject NaN


def enforce_trade_gate(parsed: dict, spot) -> tuple[dict, dict | None]:
    """Recompute the ratio and clamp the trade verdict downward per the table.

    Returns (new_parsed, enforcement) — enforcement is None when nothing was
    recomputed or clamped, else a dict describing exactly what changed:
    {ratio_emitted, ratio_recomputed, ratio_used, ratio_discrepancy,
     conviction_before/after, position_before/after, clamped}.
    parsed is copied, never mutated.
    """
    out = dict(parsed or {})

    emitted = _as_float(out.get("risk_adj_ev_ratio"))
    target = _as_float(out.get("risk_adj_target"))
    spot_f = _as_float(spot)

    recomputed = None
    if target is not None and target > 0 and spot_f is not None and spot_f > 0:
        recomputed = round(target / spot_f, 4)

    # The recomputed ratio is authoritative when available; the emitted one is
    # the fallback (still binding — the table is directional, not advisory).
    ratio_used = recomputed if recomputed is not None else emitted
    if ratio_used is None:
        return out, None  # nothing to enforce on (kill gate handles missing ratio)

    discrepancy = None
    if recomputed is not None and emitted is not None:
        discrepancy = round(abs(recomputed - emitted), 4)

    max_conviction, max_position = clamp_for_ratio(ratio_used)

    conviction_before = str(out.get("conviction") or "").upper() or None
    position_before = _as_float(out.get("position_size_pct"))

    clamped = False
    conviction_after = conviction_before
    if conviction_before in CONVICTION_RANK and (
        CONVICTION_RANK[conviction_before] > CONVICTION_RANK[max_conviction]
    ):
        conviction_after = max_conviction
        out["conviction"] = max_conviction
        clamped = True

    position_after = position_before
    if position_before is not None and position_before > max_position:
        position_after = max_position
        out["position_size_pct"] = max_position
        clamped = True

    # Persist the honest ratio (existing theses column — no new schema).
    if recomputed is not None:
        out["risk_adj_ev_ratio"] = recomputed

    significant_discrepancy = (
        discrepancy is not None and discrepancy > RATIO_DISCREPANCY_TOLERANCE
    )
    if not clamped and recomputed is None and not significant_discrepancy:
        return out, None

    enforcement = {
        "ratio_emitted": emitted,
        "ratio_recomputed": recomputed,
        "ratio_used": ratio_used,
        "ratio_discrepancy": discrepancy if significant_discrepancy else None,
        "max_conviction": max_conviction,
        "max_position_pct": max_position,
        "conviction_before": conviction_before,
        "conviction_after": conviction_after,
        "position_before": position_before,
        "position_after": position_after,
        "clamped": clamped,
    }
    return out, enforcement


def format_enforcement(enforcement: dict) -> str:
    """One-line human summary for the run log."""
    parts = []
    if enforcement.get("ratio_discrepancy") is not None:
        parts.append(
            f"RATIO DISCREPANCY: model said {enforcement['ratio_emitted']}, "
            f"math says {enforcement['ratio_recomputed']} "
            f"(risk_adj_target/spot) — using {enforcement['ratio_used']}"
        )
    elif enforcement.get("ratio_recomputed") is not None:
        parts.append(f"ratio recomputed {enforcement['ratio_recomputed']}")
    if enforcement.get("clamped"):
        parts.append(
            f"CLAMPED {enforcement['conviction_before']}/"
            f"{enforcement['position_before']}% -> "
            f"{enforcement['conviction_after']}/{enforcement['position_after']}% "
            f"(table max {enforcement['max_conviction']}/{enforcement['max_position_pct']}%)"
        )
    return "; ".join(parts) if parts else "no change"
