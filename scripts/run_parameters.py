#!/usr/bin/env python3
"""
run_parameters.py — Lesson L4: the engine must never have an invisible opinion.

Two pieces (docs/design/HORIZON_DISCOVERY_TYPEA_2026-07-02.md, L4):

1. `build_thesis_run_parameters()` — one JSON blob per thesis run stating every
   parameter the verdict was judged under: model/prompt/temperature, spot and
   its source, the horizon clock (config vs used vs fallback-flagged), the
   POST-SCALING clamp table, archetype + dcf_role, allowlist size, memory size.
   Logged with the run and persisted to `theses.run_parameters`
   (supabase/2026-07-08_theses_run_parameters.sql; strip-and-retry safe
   pre-migration). The `[trade_gate]`/`[kill_gate]` log lines were the start —
   this is the formalization.

2. `diagnose_verdict()` / `diagnose_sweep()` — zero-result auto-diagnosis.
   For each non-actionable name: WHICH gate killed it and WHAT parameter would
   have to change — the ratio each clamp band needs (and the risk-adj target
   price that implies at the current spot), the horizon clock that would flip
   it to actionable (or "no horizon fixes this"), and whether a kill-gate
   relax route exists for its archetype. Answers "is everything expensive, or
   is my ruler wrong?" instead of a silent shrug — the 6/6-BROKEN incident is
   the case this exists for. The 2026-07-08 backtest campaign supplied the
   calibration: deep sub-0.95 ratios are target-bound (no clock fixes them),
   band-edge ratios are clock-bound.

Pure math + config reads; no Supabase imports (the CLI lazy-imports the client
only for `--diagnose` against live rows).

Usage:
    python scripts/run_parameters.py --diagnose            # latest thesis per ticker
    python scripts/run_parameters.py --diagnose --all      # even when some are actionable
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trade_gate import (  # noqa: E402  (pure module)
    CLAMP_TABLE,
    DEFAULT_HORIZON_YEARS,
    MIN_HORIZON_YEARS,
    MAX_HORIZON_YEARS,
    horizon_adjusted_table,
)

HERE = Path(__file__).resolve().parent
ARCHETYPE_CONFIG = HERE.parent / "config" / "ticker_archetype_overrides.json"

# The trade gate's actionability edge: below the LOW band's lower bound the
# verdict is BROKEN/0%. Derived from the table BY BAND NAME (not position,
# not a copied literal) so a Step-12 retune cannot leave this module solving
# against a stale bar.
_LOW_THRESHOLD = next(lower for lower, conv, _pos in CLAMP_TABLE if conv == "LOW")


def _low_bound_at(horizon_years: float) -> float:
    """LOW band lower bound on the given clock, found by name."""
    return next(lower for lower, conv, _pos in horizon_adjusted_table(horizon_years)
                if conv == "LOW")


def _as_num(value) -> Optional[float]:
    """Numeric coercion matching trade_gate._as_float semantics: the closing
    JSON can carry numbers as strings and the gate judges those — the
    diagnosis must not disown a kill the gate actually made."""
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN → None


def load_archetype_and_dcf_role(ticker: str) -> tuple[Optional[str], str]:
    """Operator archetype tag + dcf_role for the parameter block.

    dcf_role mirrors the engine's default routing (transformational →
    downside_floor, everything else → primary) unless the config's object
    form pins it explicitly. Reads the config directly so this module stays
    import-light (no target_engine import for a logging concern).
    """
    archetype: Optional[str] = None
    dcf_role: Optional[str] = None
    try:
        cfg = json.loads(ARCHETYPE_CONFIG.read_text(encoding="utf-8"))
        val = cfg.get(ticker.upper())
        if isinstance(val, str):
            archetype = val.lower()
        elif isinstance(val, dict):
            a = val.get("archetype")
            archetype = a.lower() if isinstance(a, str) else None
            r = val.get("dcf_role")
            dcf_role = r.lower() if isinstance(r, str) else None
    except Exception:
        pass
    if dcf_role is None:
        dcf_role = "downside_floor" if archetype == "transformational" else "primary"
    return archetype, dcf_role


def _serializable_table(horizon_years: float) -> list[list]:
    """Post-scaling clamp table as JSON-safe rows [lower, conviction, max_pos].
    The catch-all band's -inf lower bound becomes None (JSON has no inf)."""
    return [
        [None if lower == float("-inf") else lower, conv, pos]
        for lower, conv, pos in horizon_adjusted_table(horizon_years)
    ]


def build_thesis_run_parameters(*, ticker: str, prompt_version: str, model: str,
                                temperature: float, max_tokens: int,
                                spot: float, spot_source: str,
                                horizon_config: Optional[float],
                                horizon_used: Optional[float],
                                horizon_fallback: Optional[bool],
                                archetype: Optional[str], dcf_role: str,
                                allowlist_size: int, ir_domain_present: bool,
                                memory_chars: int,
                                web_search_max_uses: int) -> dict:
    """Assemble the L4 parameter block for one thesis run. Pure; JSON-safe."""
    h = horizon_used if horizon_used else DEFAULT_HORIZON_YEARS
    # The enforcement record carries the fallback flag only when the gate had
    # something to enforce — on its early-return paths (no usable ratio) a
    # genuinely-fired out-of-bounds fallback would arrive here as None and
    # read as "no fallback". Derive it from the config value independently
    # (review finding, 2026-07-08).
    if horizon_fallback is None and horizon_config is not None:
        horizon_fallback = not (MIN_HORIZON_YEARS <= horizon_config <= MAX_HORIZON_YEARS)
    return {
        "schema": "thesis_run_parameters_v1",
        "model": model,
        "prompt_version": prompt_version,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "spot": spot,
        "spot_source": spot_source,          # "live" | "eod_provider"
        "horizon": {
            "config_years": horizon_config,   # config/thesis_horizons.json entry (None = unset)
            "used_years": h,
            "fallback": horizon_fallback,     # True = configured value was out of bounds
            "bounds": [MIN_HORIZON_YEARS, MAX_HORIZON_YEARS],
        },
        "clamp_table_post_scaling": _serializable_table(h),
        "archetype": archetype,
        "dcf_role": dcf_role,
        "tools": "web_search",
        "web_search_max_uses": web_search_max_uses,
        "allowlist_size": allowlist_size,
        "ir_domain_present": ir_domain_present,
        "memory_chars": memory_chars,         # 0 = no prior memory injected
    }


# ─── Zero-result diagnosis ───────────────────────────────────────────

def horizon_to_reach(ratio: float, threshold: float) -> Optional[float]:
    """Smallest horizon (years) at which `ratio` clears the annualized-
    equivalent sub-1 `threshold` (thresholds scale as t^(h/1.25), lesson L1).

    ratio >= threshold^(h/1.25)  →  h >= 1.25·ln(ratio)/ln(threshold)

    Returns 0.0 when any in-bounds clock clears it (h ≤ MIN bound — note a
    ratio like 0.96 does NOT clear the bar on a sub-default clock, so the
    early "already clears" answer must come from this formula, not from a
    raw ratio-vs-0.95 comparison), a positive number of years when only a
    long-enough clock flips it, and None when no in-bounds horizon does.

    Scope: this solves the LOW-actionability question only. Thresholds ≥ 1
    (MEDIUM/HIGH bands) TIGHTEN as the clock lengthens — reaching those is
    a target problem, not a clock problem — so they return None here.
    """
    ratio = _as_num(ratio)
    if ratio is None or ratio <= 0 or threshold <= 0:
        return None
    if threshold >= 1.0:
        return None  # out of scope: the bar rises with horizon (see docstring)
    if ratio >= 1.0:
        return 0.0  # a ≥1x ratio clears any sub-1 bar on every clock
    h = DEFAULT_HORIZON_YEARS * math.log(ratio) / math.log(threshold)
    if h <= MIN_HORIZON_YEARS:
        return 0.0
    return round(h, 2) if h <= MAX_HORIZON_YEARS else None


def diagnose_verdict(row: dict) -> dict:
    """Gate-artifact analysis for one thesis verdict (dict of persisted fields:
    ticker, conviction, strategic_conviction, position_size_pct,
    risk_adj_ev_ratio, thesis_horizon_years, spot_at_run, kill_gate_override).

    Returns {actionable: bool, killed_by, what_would_change: [...], ...}.
    """
    ticker = str(row.get("ticker") or "?")
    conviction = str(row.get("conviction") or "").upper()
    strategic = str(row.get("strategic_conviction") or "").upper()
    position = _as_num(row.get("position_size_pct")) or 0.0
    ratio = _as_num(row.get("risk_adj_ev_ratio"))
    h = _as_num(row.get("thesis_horizon_years"))
    h = h if h and h > 0 else DEFAULT_HORIZON_YEARS
    spot = _as_num(row.get("spot_at_run"))
    spot = spot if spot and spot > 0 else None
    archetype, _ = load_archetype_and_dcf_role(ticker)

    out: dict[str, Any] = {"ticker": ticker, "actionable": position > 0,
                           "conviction": conviction, "strategic": strategic,
                           "position_pct": position, "ratio": ratio,
                           "horizon_years": h, "archetype": archetype}
    if out["actionable"]:
        return out

    changes: list[str] = []
    if strategic == "BROKEN":
        # L3 doctrine: a structural break gets a cap no price can lift.
        out["killed_by"] = "structural (strategic_conviction=BROKEN)"
        changes.append("no price or horizon fixes a structural break — "
                       "the thesis itself must change")
    elif ratio is None:
        out["killed_by"] = "no risk_adj_ev_ratio available (gate could not judge)"
        changes.append("run produced no ratio — check risk_adj_target/spot in the closing JSON")
    else:
        scaled_low = _low_bound_at(h)  # LOW band lower bound at this clock, by name
        out["killed_by"] = (
            f"trade gate: ratio {ratio} < {scaled_low} (LOW threshold on the {h}y clock)"
            if ratio < scaled_low else
            f"model-emitted verdict (ratio {ratio} clears the {h}y LOW threshold {scaled_low})"
        )
        # What ratio each band needs at the CURRENT clock, and the risk-adj
        # target price that implies at the run's spot.
        for lower, conv, pos in horizon_adjusted_table(h):
            if lower is None or lower == float("-inf") or conv == "BROKEN":
                continue
            if ratio >= lower:
                continue
            need = (f"{conv}/{pos:.0f}% needs ratio ≥ {lower}"
                    + (f" (risk-adj target ≥ {lower * spot:.0f} at spot {spot:.0f})"
                       if spot else ""))
            changes.append(need)
        # Would a longer clock alone flip it to actionable? (the L1 question)
        h_flip = horizon_to_reach(ratio, _LOW_THRESHOLD)
        if h_flip is None:
            changes.append("no in-bounds horizon fixes this ratio — the market is "
                           "expensive for this target, the ruler is not the problem")
        elif h_flip > h:
            changes.append(f"a {h_flip}y clock would make it LOW-actionable "
                           f"(currently judged on {h}y) — is the ruler wrong for the object?")
        # Kill-gate relax route. Honest scope: pre-revenue names route
        # REGARDLESS of archetype (kill_gate.py disables the ratio floor for
        # them), but pre-revenue status is not in the persisted row — only
        # the archetype-floor route is knowable here.
        if archetype == "transformational":
            if ratio >= 0.60:
                changes.append("kill-gate relax route exists (transformational, ratio ≥ 0.60 floor) "
                               "— fires only when the trade gate says BROKEN and strategic isn't")
            else:
                changes.append(f"kill-gate floor not met (transformational floor 0.60, ratio {ratio})")
        else:
            changes.append(f"no ratio-floor relax route for archetype {archetype!r} "
                           f"(a pre-revenue name would route regardless — pre-revenue "
                           f"status is not knowable from the persisted row)")
    out["what_would_change"] = changes
    return out


def diagnose_sweep(rows: list[dict]) -> dict:
    """Sweep-level L4 diagnosis. `rows` = latest thesis verdict per ticker.
    Always returns the summary; per-name diagnoses attach whenever ANY name is
    non-actionable (the zero-actionable case is the loud one)."""
    diagnoses = [diagnose_verdict(r) for r in rows]
    n_actionable = sum(1 for d in diagnoses if d["actionable"])
    out = {
        "n_names": len(diagnoses),
        "n_actionable": n_actionable,
        "zero_actionable": bool(diagnoses) and n_actionable == 0,
        "diagnoses": [d for d in diagnoses if not d["actionable"]],
    }
    return out


def format_sweep(report: dict) -> str:
    lines = [f"gate diagnosis: {report['n_actionable']}/{report['n_names']} names actionable"]
    if report["zero_actionable"]:
        lines[0] += " — ZERO-RESULT: per-name gate artifacts below (L4)"
    for d in report["diagnoses"]:
        lines.append(f"  {d['ticker']}: {d['conviction']} (strategic {d['strategic'] or '?'}, "
                     f"ratio {d['ratio']}, {d['horizon_years']}y clock) — killed by {d.get('killed_by')}")
        for c in d.get("what_would_change", []):
            lines.append(f"    → {c}")
    return "\n".join(lines)


# ─── CLI (--diagnose reads the live latest-thesis-per-ticker set) ────

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="L4 run-parameter / gate-artifact tools")
    ap.add_argument("--diagnose", action="store_true",
                    help="diagnose the latest thesis verdict per ticker (Supabase)")
    ap.add_argument("--all", action="store_true",
                    help="show per-name diagnoses even when some names are actionable")
    ap.add_argument("--all-tickers", action="store_true",
                    help="include retired/non-watchlist tickers in the sweep")
    args = ap.parse_args()
    if not args.diagnose:
        ap.error("nothing to do — pass --diagnose")

    from utils import load_env
    load_env()
    from supabase_helper import get_client
    sb = get_client()
    # Structural columns selected optimistically; PostgREST rejects the whole
    # select if ANY column is missing, and the columns span three migration
    # vintages — so degrade in stages instead of all-or-nothing (the lib/data
    # lesson: a partially migrated DB must not read as fully pre-migration,
    # which here would mis-diagnose every name as "no ratio available").
    stages = [
        "ticker,run_at,conviction,strategic_conviction,position_size_pct,"
        "risk_adj_ev_ratio,thesis_horizon_years,spot_at_run,kill_gate_override",
        # without thesis_horizon_years (2026-07-02_theses_horizon.sql unapplied)
        "ticker,run_at,conviction,strategic_conviction,position_size_pct,"
        "risk_adj_ev_ratio,spot_at_run,kill_gate_override",
        # legacy only (2026-07-02_consolidated_pending.sql unapplied)
        "ticker,run_at,conviction,position_size_pct,spot_at_run",
    ]
    res = None
    for i, fields in enumerate(stages):
        try:
            res = sb.table("theses").select(fields).order("run_at", desc=True).limit(500).execute()
            break
        except Exception as e:
            print(f"[run_parameters] select stage {i + 1} failed — unapplied migration? "
                  f"Degrading column set: {e}", file=sys.stderr)
    if res is None:
        print("[run_parameters] all select stages failed", file=sys.stderr)
        sys.exit(1)
    latest: dict[str, dict] = {}
    for r in res.data or []:
        if r.get("ticker") and r["ticker"] not in latest:
            latest[r["ticker"]] = r
    # Filter to the ACTIVE watchlist: theses history contains retired tickers
    # whose stale verdicts would suppress the zero-actionable alarm.
    if not args.all_tickers:
        try:
            active = {s["ticker"] for s in
                      (sb.table("stocks").select("ticker").eq("active", True).execute().data or [])}
            if active:
                dropped = sorted(set(latest) - active)
                latest = {t: r for t, r in latest.items() if t in active}
                if dropped:
                    print(f"[run_parameters] ignoring non-watchlist tickers: "
                          f"{', '.join(dropped)} (pass --all-tickers to include)",
                          file=sys.stderr)
        except Exception as e:
            print(f"[run_parameters] stocks-table filter unavailable ({e}) — "
                  f"diagnosing all tickers", file=sys.stderr)
    report = diagnose_sweep(list(latest.values()))
    if args.all and not report["diagnoses"]:
        report["diagnoses"] = [diagnose_verdict(r) for r in latest.values()]
    print(format_sweep(report))


if __name__ == "__main__":
    main()
