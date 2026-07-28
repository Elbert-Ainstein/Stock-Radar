"""Tests for run_parameters.py — L4 parameter block + zero-result diagnosis."""
from __future__ import annotations

import json
import math

import run_parameters as rp
from trade_gate import DEFAULT_HORIZON_YEARS, horizon_adjusted_table


def _build(**over):
    kw = dict(
        ticker="LITE", prompt_version="v3.4.4", model="claude-opus-4-8",
        temperature=0.3, max_tokens=16000, spot=783.25, spot_source="live",
        horizon_config=None, horizon_used=1.25, horizon_fallback=None,
        archetype="transformational", dcf_role="downside_floor",
        allowlist_size=41, ir_domain_present=True, memory_chars=1234,
        web_search_max_uses=8,
    )
    kw.update(over)
    return rp.build_thesis_run_parameters(**kw)


# ─── parameter block ─────────────────────────────────────────────────

def test_block_is_json_serializable():
    blob = json.dumps(_build())  # -inf in the raw table would raise here
    assert "thesis_run_parameters_v1" in blob


def test_broken_band_lower_bound_serialized_as_none():
    table = _build()["clamp_table_post_scaling"]
    assert table[-1][0] is None and table[-1][1] == "BROKEN"
    assert all(row[0] is not None for row in table[:-1])


def test_table_matches_trade_gate_scaling():
    got = _build(horizon_used=3.0)["clamp_table_post_scaling"]
    want = horizon_adjusted_table(3.0)
    for g, w in zip(got, want):
        assert g[1] == w[1] and g[2] == w[2]
        if g[0] is not None:
            assert abs(g[0] - w[0]) < 1e-9


def test_horizon_defaults_when_unset():
    p = _build(horizon_used=None)
    assert p["horizon"]["used_years"] == DEFAULT_HORIZON_YEARS
    assert p["horizon"]["config_years"] is None


def test_dcf_role_routing_pinned_to_real_config():
    # Owner-tagged config (2026-07-02): LITE transformational, SNDK cyclical.
    arch, role = rp.load_archetype_and_dcf_role("LITE")
    assert arch == "transformational" and role == "downside_floor"
    arch, role = rp.load_archetype_and_dcf_role("SNDK")
    assert arch == "cyclical" and role == "primary"
    arch, role = rp.load_archetype_and_dcf_role("NOSUCH")
    assert arch is None and role == "primary"


# ─── horizon_to_reach (the "is the ruler wrong?" solver) ─────────────

def test_low_threshold_derived_from_table_by_name():
    from trade_gate import CLAMP_TABLE
    assert rp._LOW_THRESHOLD == next(l for l, c, _ in CLAMP_TABLE if c == "LOW")
    assert rp._low_bound_at(1.25) == rp._LOW_THRESHOLD


def test_ratio_at_or_above_one_clears_any_clock():
    assert rp.horizon_to_reach(1.2, 0.95) == 0.0
    assert rp.horizon_to_reach(1.0, 0.95) == 0.0


def test_near_bar_ratio_needs_the_formula_not_a_raw_compare():
    # 0.96 ≥ 0.95 raw, but on a sub-default clock the scaled bar is HIGHER
    # (0.95^(0.5/1.25) ≈ 0.98) — the solver must return the true minimal
    # clock (~0.995y), not 0.0 "clears at any clock" (review major).
    h = rp.horizon_to_reach(0.96, 0.95)
    assert abs(h - round(DEFAULT_HORIZON_YEARS * math.log(0.96) / math.log(0.95), 2)) < 1e-9
    assert h > 0.5  # in particular, NOT clearable on a half-year clock


def test_sub_min_solution_collapses_to_zero():
    # 0.99 solves to ~0.245y, below the 0.25y bound → any in-bounds clock.
    assert rp.horizon_to_reach(0.99, 0.95) == 0.0


def test_below_native_bar_no_clock_helps():
    # Conservative-only floor: 0.90 is below the native 0.95 bar, and long
    # clocks never lower the bar (the two-sided formula's ~2.57y answer was
    # a promise the enforced table would not honor — confirmed defect).
    assert rp.horizon_to_reach(0.90, 0.95) is None
    # At/above the native bar the sub-default formula still applies:
    # 0.96 clears once the (short-clock-raised) bar drops to it, ~0.65y.
    h = rp.horizon_to_reach(0.96, 0.95)
    assert abs(h - DEFAULT_HORIZON_YEARS * math.log(0.96) / math.log(0.95)) < 0.01


def test_deep_ratio_no_horizon_fixes_it():
    # The 2026-07-08 campaign case: LITE ratio 0.5681 needs a ~13.8y clock — out of bounds.
    assert rp.horizon_to_reach(0.5681, 0.95) is None


def test_above_one_thresholds_never_reachable_from_below():
    assert rp.horizon_to_reach(0.99, 1.25) is None


def test_garbage_inputs():
    assert rp.horizon_to_reach(None, 0.95) is None
    assert rp.horizon_to_reach(0, 0.95) is None
    assert rp.horizon_to_reach(0.9, 0) is None
    assert rp.horizon_to_reach("garbage", 0.95) is None


def test_horizon_fallback_derived_when_enforcement_absent():
    # The gate's early-return paths drop the fallback flag; the builder must
    # derive it from the config value itself (review finding).
    p = _build(horizon_config=15.0, horizon_used=1.25, horizon_fallback=None)
    assert p["horizon"]["fallback"] is True
    p = _build(horizon_config=3.0, horizon_used=3.0, horizon_fallback=None)
    assert p["horizon"]["fallback"] is False
    # No config entry → nothing to flag; enforcement value wins when present.
    p = _build(horizon_config=None, horizon_fallback=None)
    assert p["horizon"]["fallback"] is None
    p = _build(horizon_config=15.0, horizon_fallback=True)
    assert p["horizon"]["fallback"] is True


# ─── diagnose_verdict ────────────────────────────────────────────────

def _row(ticker="PLTR", conviction="BROKEN", strategic="HIGH", pos=0,
         ratio=0.87, horizon=None, spot=100.0):
    return {"ticker": ticker, "conviction": conviction,
            "strategic_conviction": strategic, "position_size_pct": pos,
            "risk_adj_ev_ratio": ratio, "thesis_horizon_years": horizon,
            "spot_at_run": spot}


def test_actionable_row_short_circuits():
    d = rp.diagnose_verdict(_row(conviction="MEDIUM", pos=20, ratio=1.17))
    assert d["actionable"] is True
    assert "killed_by" not in d


def test_trade_gate_kill_names_bands_and_prices():
    d = rp.diagnose_verdict(_row(ratio=0.87, spot=100.0))
    assert d["actionable"] is False
    assert "trade gate" in d["killed_by"]
    joined = " ".join(d["what_would_change"])
    # Ratio each band needs + the implied risk-adj target at spot 100.
    assert "LOW/10% needs ratio ≥ 0.95" in joined and "≥ 95" in joined
    assert "HIGH/35% needs ratio ≥ 1.25" in joined
    # The L1 question under the conservative-only floor: 0.87 is below the
    # native bar, so no clock fixes it — and the diagnosis says so instead
    # of promising one.
    assert "no in-bounds horizon fixes this ratio" in joined
    assert "clock would make it LOW-actionable" not in joined


def test_deep_ratio_says_market_not_ruler():
    d = rp.diagnose_verdict(_row(ratio=0.5681))
    assert "no in-bounds horizon fixes this ratio" in " ".join(d["what_would_change"])


def test_kill_gate_route_by_archetype():
    # LITE is transformational in the real config → relax route exists at 0.87.
    d = rp.diagnose_verdict(_row(ticker="LITE", ratio=0.87))
    assert any("kill-gate relax route exists" in c for c in d["what_would_change"])
    # Below the 0.60 floor the route is named but not met.
    d = rp.diagnose_verdict(_row(ticker="LITE", ratio=0.55))
    assert any("floor not met" in c for c in d["what_would_change"])
    # PLTR is compounder → no ratio-floor route; message stays honest that
    # pre-revenue routing exists but isn't knowable from the persisted row.
    d = rp.diagnose_verdict(_row(ticker="PLTR", ratio=0.87))
    assert any("no ratio-floor relax route" in c for c in d["what_would_change"])
    assert any("pre-revenue" in c for c in d["what_would_change"])


def test_structural_break_no_price_fixes():
    d = rp.diagnose_verdict(_row(strategic="BROKEN"))
    assert d["killed_by"].startswith("structural")
    assert any("no price or horizon fixes" in c for c in d["what_would_change"])


def test_missing_ratio_branch():
    d = rp.diagnose_verdict(_row(ratio=None))
    assert "no risk_adj_ev_ratio" in d["killed_by"]


def test_string_ratio_is_judged_not_disowned():
    # trade_gate._as_float coerces string ratios and the gate judges them —
    # the diagnosis must not claim "gate could not judge" (review finding).
    d = rp.diagnose_verdict(_row(ratio="0.80"))
    assert "trade gate" in d["killed_by"]
    assert "no risk_adj_ev_ratio" not in d["killed_by"]


def test_model_emitted_refusal_distinguished_from_gate_clamp():
    # Ratio clears the LOW bar but the model itself emitted 0% — the gate
    # never upgrades, and the diagnosis must not blame the gate.
    d = rp.diagnose_verdict(_row(ratio=0.97, pos=0))
    assert "model-emitted verdict" in d["killed_by"]


def test_longer_clock_never_loosens_the_bar():
    # Conservative-only floor: on a 3y clock the LOW bar STAYS 0.95 (the
    # prompt pins targets to 12-18mo; loosening was a confirmed defect).
    # Ratio 0.90 remains gate-killed and the diagnosis must not promise a
    # clock that the enforced table will not honor.
    d = rp.diagnose_verdict(_row(ratio=0.90, horizon=3.0))
    assert "trade gate" in d["killed_by"] and "0.95" in d["killed_by"]
    assert any("no in-bounds horizon" in c for c in d["what_would_change"])
    assert not any("clock would make it" in c for c in d["what_would_change"])


# ─── sweep ───────────────────────────────────────────────────────────

def test_sweep_zero_actionable_flags_and_formats():
    rows = [_row(ticker="PLTR"), _row(ticker="CELH", ratio=0.72)]
    rep = rp.diagnose_sweep(rows)
    assert rep["zero_actionable"] is True
    assert len(rep["diagnoses"]) == 2
    text = rp.format_sweep(rep)
    assert "ZERO-RESULT" in text and "PLTR" in text and "→" in text


def test_sweep_mixed_lists_only_refused():
    rows = [_row(ticker="PLTR"),
            _row(ticker="LITE", conviction="MEDIUM", pos=20, ratio=1.2)]
    rep = rp.diagnose_sweep(rows)
    assert rep["zero_actionable"] is False
    assert rep["n_actionable"] == 1
    assert [d["ticker"] for d in rep["diagnoses"]] == ["PLTR"]


def test_sweep_empty():
    rep = rp.diagnose_sweep([])
    assert rep["zero_actionable"] is False and rep["n_names"] == 0
