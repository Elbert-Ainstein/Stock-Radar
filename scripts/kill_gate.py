"""
kill_gate.py — D1: archetype-routed kill-rule post-processor.

The thesis kill rule (prompts/thesis_v3.md) clamps the TRADE-level conviction to
BROKEN / 0% whenever `risk_adj_ev_ratio < ~0.90`, uniformly for every stock. That
over-fires on regime-shift / transformational names, whose EV math is deliberately
conservative (and, post-V2, uses DCF-as-a-floor) — so a strong regime-shift bet can
be killed on cautious math alone.

A kill clamp is a HARD GATE: by the project's filter philosophy it must be
deterministic and ungameable, so it is enforced HERE in code, not in model prose.
This routes the threshold by archetype:

    cyclical / garp / compounder / special_situation : 0.90 (unchanged — no-op here)
    transformational (regime-shift)                  : 0.60 (wider)
    pre-revenue (≈zero TTM revenue)                  : gate disabled (no anchor)

`apply_kill_gate` ONLY relaxes a ratio-driven BROKEN whose underlying *thesis* is
intact (strategic_conviction != BROKEN). It NEVER un-breaks a genuinely broken
thesis, and is a strict no-op for non-transformational archetypes.

The override is emitted as STRUCTURED data (`kill_gate_override`), not only a prose
note, so the downstream checkpoint grader reads the routed verdict — not the raw
"BROKEN" — when it computes the reasoning fingerprint and grades the thesis.

NOTE: thesis-path only (run_thesis). The Socratic-path version reuses this module
and is a separate, deliberate step.
"""

from __future__ import annotations

from typing import Any, Optional

# The original uniform kill threshold (kept as the default floor for archetypes we
# do NOT route — so they behave exactly as before).
UNIFORM_KILL_THRESHOLD = 0.90

# Archetype-specific kill floors. Only archetypes listed here are routed; all
# others fall through to a strict no-op (preserving the prompt's behaviour).
_ARCHETYPE_KILL_FLOOR = {
    "transformational": 0.60,
}

# Pre-revenue: TTM revenue below this is treated as "no revenue anchor".
PRE_REVENUE_TTM_USD = 10_000_000.0

# What a relaxed (un-killed) trade becomes. Conservative by design: not BROKEN,
# but LOW conviction at the first-touch position size (per user_position_sizing_
# discipline). The judgment card / operator can size up from here.
RELAXED_CONVICTION = "LOW"
RELAXED_POSITION_PCT = 5.0


def is_pre_revenue(ttm_revenue: Optional[float]) -> bool:
    return ttm_revenue is not None and ttm_revenue < PRE_REVENUE_TTM_USD


def archetype_kill_floor(archetype: Optional[str]) -> Optional[float]:
    """The kill floor for an archetype, or None if this archetype isn't routed."""
    if not archetype:
        return None
    return _ARCHETYPE_KILL_FLOOR.get(archetype.lower())


def apply_kill_gate(parsed: dict, archetype: Optional[str],
                    pre_revenue: bool = False) -> tuple[dict, Optional[dict]]:
    """Route the kill rule by archetype.

    Returns (parsed_out, override_or_None). When an override fires, parsed_out is a
    COPY with `conviction`/`position_size_pct` relaxed, a structured
    `kill_gate_override` attached, and a human-readable line appended to
    `kill_triggers`. Otherwise parsed is returned unchanged and override is None.
    """
    conviction = str(parsed.get("conviction") or "").upper()
    strategic = str(parsed.get("strategic_conviction") or "").upper()
    ratio = parsed.get("risk_adj_ev_ratio")

    # Only act on a ratio-driven BROKEN whose thesis is still intact.
    if conviction != "BROKEN" or strategic == "BROKEN" or not isinstance(ratio, (int, float)):
        return parsed, None

    # Decide whether THIS archetype/ticker gets a relaxed gate.
    if pre_revenue:
        floor = None
        reason = "pre-revenue: ratio gate disabled (no revenue anchor)"
    else:
        floor = archetype_kill_floor(archetype)
        if floor is None:
            return parsed, None  # non-routed archetype -> behave exactly as the prompt
        if ratio < floor:
            return parsed, None  # still killed, even under the wider floor
        reason = f"archetype '{archetype}' floor {floor:.2f}: ratio {ratio:.2f} >= floor"

    override = {
        "raw_verdict": parsed.get("conviction"),
        "routed_verdict": RELAXED_CONVICTION,
        "raw_position_pct": parsed.get("position_size_pct"),
        "routed_position_pct": RELAXED_POSITION_PCT,
        "risk_adj_ev_ratio": float(ratio),
        "archetype": archetype,
        "archetype_floor": floor,           # None when pre-revenue (gate disabled)
        "uniform_threshold": UNIFORM_KILL_THRESHOLD,
        "reason": reason,
    }

    out = dict(parsed)
    out["conviction"] = RELAXED_CONVICTION
    out["position_size_pct"] = RELAXED_POSITION_PCT
    out["kill_gate_override"] = override
    triggers = list(out.get("kill_triggers") or [])
    triggers.append(
        f"[kill_gate_override] uniform gate said {override['raw_verdict']} at "
        f"{UNIFORM_KILL_THRESHOLD}; routed to {RELAXED_CONVICTION}/"
        f"{RELAXED_POSITION_PCT:.0f}% — {reason}."
    )
    out["kill_triggers"] = triggers
    return out, override
