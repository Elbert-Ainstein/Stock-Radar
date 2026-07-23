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

# The clock the Step-12 table was written for: the ~12-18-month thesis horizon
# (midpoint 1.25y) of the trade the system was born from (the memory-cycle
# capture). 2026-07-02 lesson L1: this clock was previously INVISIBLE — the
# same table clamped 3-year theses (robotics-class) to no-buy not because the
# market was expensive but because the ruler was wrong for the object.
DEFAULT_HORIZON_YEARS = 1.25
# Sanity bounds for per-name horizons; outside -> fall back to default, loudly.
MIN_HORIZON_YEARS, MAX_HORIZON_YEARS = 0.25, 10.0

# (inclusive lower bound of risk_adj_ev_ratio, max conviction, max position %)
# Mirrors the Step-12 table in scripts/prompts/thesis_v3.md verbatim AT THE
# DEFAULT HORIZON; the prompt's "LOW–MEDIUM" band (1.00–1.10) is encoded as
# max MEDIUM / 15%. For other horizons the thresholds are annualized-return-
# equivalent: t^(h/1.25) — so a 1.3x ratio on an 18-month clock and a 2.5x on
# a 3-year clock are judged by the same annualized bar.
CLAMP_TABLE = (
    (1.25, "HIGH", 35.0),
    (1.10, "MEDIUM", 25.0),
    (1.00, "MEDIUM", 15.0),
    (0.95, "LOW", 10.0),
    (float("-inf"), "BROKEN", 0.0),
)


def horizon_adjusted_table(horizon_years: float) -> tuple:
    """Scale the clamp-table ratio thresholds to a thesis horizon —
    CONSERVATIVE-ONLY until the thesis prompt is horizon-aware.

    A threshold t (a total-return ratio over the DEFAULT horizon) represents
    the annualized bar t^(1/1.25); the equivalent total-return threshold over
    h years is t^(h/1.25). At h == DEFAULT_HORIZON_YEARS this is the identity,
    so the default path is byte-identical to the original table.

    2026-07-02 review finding (confirmed): thesis_v3.md Step 6 still pins
    risk_adj_target to a 12-18-MONTH target date, so the ratio's numerator is
    NOT yet on the configured clock. Two-sided scaling would therefore loosen
    the BROKEN edge against a mismatched number (a 15-month EV 8% below spot
    escaping the kill band because the gate pretends the clock is 3y). Until
    the prompt carries the horizon (L3 prompt batch), every scaled threshold
    is floored at its native value — a configured clock can only make the
    gate STRICTER, never looser. Full two-sided honesty unlocks with the
    prompt change; see docs/design/HORIZON_DISCOVERY_TYPEA_2026-07-02.md L1.
    """
    exp = horizon_years / DEFAULT_HORIZON_YEARS
    return tuple(
        (lower if lower == float("-inf")
         else max(round(lower ** exp, 6), lower),  # conservative-only
         conv, pos)
        for lower, conv, pos in CLAMP_TABLE
    )

# Recomputed-vs-emitted ratio differences above this are reported as a
# discrepancy (a rounding difference of ±0.005 is honest arithmetic).
RATIO_DISCREPANCY_TOLERANCE = 0.005


def clamp_for_ratio(ratio: float, horizon_years: float = DEFAULT_HORIZON_YEARS) -> tuple[str, float]:
    """Return (max_conviction, max_position_pct) for a risk_adj_ev_ratio,
    judged on the given thesis clock (annualized-equivalent thresholds)."""
    table = (CLAMP_TABLE if horizon_years == DEFAULT_HORIZON_YEARS
             else horizon_adjusted_table(horizon_years))
    for lower, conviction, position in table:
        if ratio >= lower:
            return conviction, position
    return "BROKEN", 0.0  # unreachable; -inf bound catches everything


def _as_float(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # reject NaN


def enforce_trade_gate(parsed: dict, spot,
                       horizon_years: float | None = None) -> tuple[dict, dict | None]:
    """Recompute the ratio and clamp the trade verdict downward per the table,
    judged on the thesis's OWN clock (lesson L1, 2026-07-02).

    Horizon precedence (2026-07-02 review fix — the original order let the
    MODEL choose its own clock): the horizon_years ARG (operator config) wins;
    a parsed["thesis_horizon_years"] field is honored only when no operator
    horizon was supplied (re-enforcement of an already-gated row). A
    model-emitted horizon that conflicts with the config is IGNORED and
    flagged. Out-of-bounds horizons fall back to the default, flagged. The
    enforcement record carries horizon_source — the gate never has an
    invisible opinion about time, including where the time came from.

    Returns (new_parsed, enforcement) — enforcement is None when nothing was
    recomputed or clamped, else a dict describing exactly what changed:
    {ratio_emitted, ratio_recomputed, ratio_used, ratio_discrepancy,
     horizon_years, annualized_return, conviction_before/after,
     position_before/after, clamped}. parsed is copied, never mutated.
    """
    out = dict(parsed or {})

    operator_h = _as_float(horizon_years)
    parsed_h = _as_float(out.get("thesis_horizon_years"))
    model_horizon_ignored = None
    if operator_h is not None:
        h, horizon_source = operator_h, "config"
        if parsed_h is not None and abs(parsed_h - operator_h) > 1e-9:
            # The model emitted its own clock; the hard gate does not take
            # timing instructions from the thing it exists to constrain.
            model_horizon_ignored = parsed_h
    elif parsed_h is not None:
        h, horizon_source = parsed_h, "row"  # re-enforcing an already-gated row
    else:
        h, horizon_source = DEFAULT_HORIZON_YEARS, "default"
    horizon_fallback = False
    if not (MIN_HORIZON_YEARS <= h <= MAX_HORIZON_YEARS):
        h, horizon_fallback, horizon_source = DEFAULT_HORIZON_YEARS, True, "default"
    out["thesis_horizon_years"] = h  # every verdict states its clock

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

    max_conviction, max_position = clamp_for_ratio(ratio_used, h)

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
    if (not clamped and recomputed is None and not significant_discrepancy
            and model_horizon_ignored is None):
        return out, None

    enforcement = {
        "ratio_emitted": emitted,
        "ratio_recomputed": recomputed,
        "ratio_used": ratio_used,
        "ratio_discrepancy": discrepancy if significant_discrepancy else None,
        "horizon_years": h,
        "horizon_source": horizon_source,
        "model_horizon_ignored": model_horizon_ignored,
        "horizon_fallback": horizon_fallback,
        "annualized_return": (round(ratio_used ** (1.0 / h) - 1.0, 4)
                              if ratio_used > 0 else None),
        "max_conviction": max_conviction,
        "max_position_pct": max_position,
        "conviction_before": conviction_before,
        "conviction_after": conviction_after,
        "position_before": position_before,
        "position_after": position_after,
        "clamped": clamped,
    }
    return out, enforcement


# ── L4 zero-result auto-diagnosis (2026-07-02): tape vs ruler ──────────────────

LOW_ESCAPE_THRESHOLD = 0.95  # native-clock ratio bound of the BROKEN band


def is_actionable(conviction) -> bool:
    """A verdict the operator could act on (anything better than BROKEN)."""
    return str(conviction or "").upper() in ("LOW", "MEDIUM", "HIGH")


def horizon_to_clear_low(ratio) -> float | None:
    """Shortest thesis horizon (years) at which `ratio` escapes the BROKEN
    band under TWO-SIDED annualized scaling (0.95^(h/1.25) <= ratio), or None
    if no clock within MAX_HORIZON_YEARS clears it.

    Diagnostic only: the live gate scales conservative-only until the thesis
    prompt is horizon-aware, so this answers "is the clamp a clock artifact
    in principle?", not "what would today's gate do?" (2026-07-02 review fix:
    the old >=0.95 short-circuit returned the default clock for ratios that
    truly clear on SHORTER clocks, misrouting gate_artifact_analysis.)"""
    import math
    r = _as_float(ratio)
    if r is None or r <= 0:
        return None
    if r >= 1.0:
        return MIN_HORIZON_YEARS  # any clock clears a >=1x ratio
    h = DEFAULT_HORIZON_YEARS * math.log(r) / math.log(LOW_ESCAPE_THRESHOLD)
    h = max(h, MIN_HORIZON_YEARS)
    return round(h, 2) if h <= MAX_HORIZON_YEARS else None


def gate_artifact_analysis(entries: list[dict]) -> str:
    """When a sweep produces ZERO actionable verdicts, answer the question the
    6/6-BROKEN incident never got: is everything expensive, or is the ruler
    wrong? (Lesson L4: the engine must never end a run with a silent shrug.)

    entries: [{ticker, ratio, horizon_years, conviction}, ...]. Pure; returns
    a multi-line report for the run log.
    """
    lines = ["[gate-artifact] ZERO ACTIONABLE VERDICTS — diagnosing tape vs ruler:"]
    ruler_suspects, tape_calls, not_gate, data_problems = 0, 0, 0, 0
    for e in sorted(entries, key=lambda x: str(x.get("ticker", ""))):
        ticker = e.get("ticker", "?")
        r = _as_float(e.get("ratio"))
        h = _as_float(e.get("horizon_years")) or DEFAULT_HORIZON_YEARS
        if r is None or r <= 0:
            data_problems += 1
            lines.append(f"  {ticker}: no usable ratio — data/parse problem, not a market read")
            continue
        ann = r ** (1.0 / h) - 1.0
        clears_at = horizon_to_clear_low(r)
        if clears_at is None:
            tape_calls += 1
            verdict = "no clock within 10y clears this — the tape is expensive on this name"
        elif clears_at <= h:
            # The ratio clears the BROKEN band at its own clock, so THIS gate
            # did not produce the non-actionable verdict (2026-07-02 review
            # fix: the old wording blamed an 'upper band', which cannot make
            # a verdict non-actionable — the cause is upstream).
            not_gate += 1
            verdict = ("ratio clears the gate at its own clock — the non-actionable "
                       "verdict came from the model/kill path or a missing conviction "
                       "field, NOT the ratio clamp; inspect the thesis output")
        else:
            ruler_suspects += 1
            verdict = (f"would escape BROKEN on a >= {clears_at}y clock once the thesis "
                       f"prompt is horizon-aware — RULER SUSPECT (is {h}y right for this thesis?)")
        lines.append(f"  {ticker}: ratio {r} @ {h}y ({ann:+.1%}/yr) — {verdict}")
    diagnosed = ruler_suspects + tape_calls + not_gate
    if diagnosed == 0:
        lines.append(
            f"[gate-artifact] SUMMARY: no diagnosable entries ({data_problems} data/parse "
            "problem(s)) — this sweep failed upstream of the gate; fix data before reading the market."
        )
    elif ruler_suspects and ruler_suspects >= tape_calls:
        lines.append(
            f"[gate-artifact] SUMMARY: {ruler_suspects}/{diagnosed} diagnosed names are ruler-suspect — "
            "review config/thesis_horizons.json (and the prompt-clock work) before concluding the market is expensive."
        )
    else:
        lines.append(
            f"[gate-artifact] SUMMARY: predominantly a tape call ({tape_calls} expensive vs "
            f"{ruler_suspects} ruler-suspect, {not_gate} not-gate-caused) — the clamps look honest; "
            "consider discovery mode (STALK), not force-buying."
        )
    return "\n".join(lines)


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
    h = enforcement.get("horizon_years")
    if h is not None:
        ann = enforcement.get("annualized_return")
        clock = f"judged on {h}y clock ({enforcement.get('horizon_source', '?')})"
        if ann is not None:
            clock += f" ({ann:+.1%}/yr annualized)"
        if enforcement.get("model_horizon_ignored") is not None:
            clock += (f" [MODEL-EMITTED horizon {enforcement['model_horizon_ignored']}y "
                      f"IGNORED — the gate does not take timing from the model]")
        if enforcement.get("horizon_fallback"):
            clock += " [configured horizon out of bounds — default used]"
        parts.append(clock)
    return "; ".join(parts) if parts else "no change"
