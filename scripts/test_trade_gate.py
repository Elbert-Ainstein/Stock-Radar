"""Unit tests for trade_gate.py — code-side enforcement of the Step-12
risk-adj-EV clamp — plus the run_thesis truncation-guard predicate.

Run: pytest scripts/test_trade_gate.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from trade_gate import clamp_for_ratio, enforce_trade_gate, format_enforcement
from run_thesis import thesis_output_usable


# ── clamp table (thesis_v3.md Step 12, verbatim bands) ─────────────────────────

@pytest.mark.parametrize("ratio,conviction,position", [
    (0.55, "BROKEN", 0.0),
    (0.87, "BROKEN", 0.0),    # the COHR case cited in the prompt
    (0.949, "BROKEN", 0.0),
    (0.95, "LOW", 10.0),
    (0.99, "LOW", 10.0),
    (1.00, "MEDIUM", 15.0),
    (1.09, "MEDIUM", 15.0),
    (1.10, "MEDIUM", 25.0),
    (1.24, "MEDIUM", 25.0),
    (1.25, "HIGH", 35.0),
    (2.00, "HIGH", 35.0),
])
def test_clamp_table(ratio, conviction, position):
    assert clamp_for_ratio(ratio) == (conviction, position)


# ── the audit's failure scenario: gamed/slipped ratio ───────────────────────────

def test_gamed_ratio_is_recomputed_and_clamped():
    """Model emits ratio 0.97 / LOW / 10% but the numbers imply 436/787 = 0.554:
    the verdict must clamp to BROKEN/0% and the discrepancy must be reported."""
    parsed = {"risk_adj_target": 436.0, "risk_adj_ev_ratio": 0.97,
              "conviction": "LOW", "position_size_pct": 10,
              "strategic_conviction": "HIGH"}
    out, tg = enforce_trade_gate(parsed, spot=787.0)
    assert out["risk_adj_ev_ratio"] == pytest.approx(0.554, abs=1e-3)
    assert out["conviction"] == "BROKEN"
    assert out["position_size_pct"] == 0.0
    assert out["strategic_conviction"] == "HIGH"  # Type A never touched
    assert tg["clamped"] is True
    assert tg["ratio_discrepancy"] is not None and tg["ratio_discrepancy"] > 0.4
    assert "RATIO DISCREPANCY" in format_enforcement(tg)
    assert parsed["conviction"] == "LOW"  # input never mutated


def test_honest_high_ratio_untouched():
    parsed = {"risk_adj_target": 1100.0, "risk_adj_ev_ratio": 1.18,
              "conviction": "MEDIUM", "position_size_pct": 25}
    out, tg = enforce_trade_gate(parsed, spot=932.0)  # 1100/932 = 1.1803
    assert out["conviction"] == "MEDIUM"
    assert out["position_size_pct"] == 25
    assert tg is not None and tg["clamped"] is False  # ratio recomputed, no clamp
    assert tg["ratio_discrepancy"] is None            # 1.1803 vs 1.18 is honest rounding


def test_gate_never_upgrades():
    """Ratio 1.30 allows HIGH — but a model that said LOW stays LOW (downward only)."""
    parsed = {"risk_adj_target": 130.0, "conviction": "LOW", "position_size_pct": 5}
    out, _ = enforce_trade_gate(parsed, spot=100.0)
    assert out["conviction"] == "LOW"
    assert out["position_size_pct"] == 5


def test_position_clamped_even_when_conviction_within_table():
    """Ratio 0.97 caps position at 10% even if conviction is already LOW."""
    parsed = {"risk_adj_target": 97.0, "conviction": "LOW", "position_size_pct": 30}
    out, tg = enforce_trade_gate(parsed, spot=100.0)
    assert out["conviction"] == "LOW"
    assert out["position_size_pct"] == 10.0
    assert tg["clamped"] is True


def test_emitted_ratio_binding_when_recompute_impossible():
    """No spot / no target -> the emitted ratio still drives the clamp
    (the table is directional, not advisory)."""
    parsed = {"risk_adj_ev_ratio": 0.87, "conviction": "MEDIUM", "position_size_pct": 20}
    out, tg = enforce_trade_gate(parsed, spot=None)
    assert out["conviction"] == "BROKEN"
    assert out["position_size_pct"] == 0.0
    assert tg["ratio_recomputed"] is None


def test_nothing_to_enforce_is_a_noop():
    parsed = {"conviction": "HIGH", "position_size_pct": 30}
    out, tg = enforce_trade_gate(parsed, spot=100.0)
    assert tg is None
    assert out["conviction"] == "HIGH"


def test_garbage_inputs_never_raise():
    for spot in (None, 0, -5, "nan", "abc"):
        out, _ = enforce_trade_gate({"risk_adj_target": "x", "risk_adj_ev_ratio": "y",
                                     "conviction": 7}, spot)
        assert isinstance(out, dict)


# ── horizon-aware clamp (lesson L1, 2026-07-02) ─────────────────────────────────

from trade_gate import (
    DEFAULT_HORIZON_YEARS,
    horizon_adjusted_table,
)


def test_default_horizon_is_identity():
    """At the table's native clock the scaled table is byte-identical —
    the L1 change must not move any existing verdict."""
    for (a, ca, pa), (b, cb, pb) in zip(
        horizon_adjusted_table(DEFAULT_HORIZON_YEARS),
        (
            (1.25, "HIGH", 35.0),
            (1.10, "MEDIUM", 25.0),
            (1.00, "MEDIUM", 15.0),
            (0.95, "LOW", 10.0),
            (float("-inf"), "BROKEN", 0.0),
        ),
    ):
        assert (ca, pa) == (cb, pb)
        assert a == b or abs(a - b) < 1e-9


def test_same_ratio_different_clock_different_verdict():
    """The lesson's own example: 1.3x is HIGH-grade on the native ~15-month
    clock but only MEDIUM-grade money on a 3-year clock (~9%/yr)."""
    assert clamp_for_ratio(1.30) == ("HIGH", 35.0)
    assert clamp_for_ratio(1.30, horizon_years=3.0) == ("MEDIUM", 25.0)


def test_long_clock_big_ratio_compares_honestly():
    """2.5x over 3 years (~36%/yr) clears the HIGH bar (1.25^(3/1.25) ~= 1.71)."""
    assert clamp_for_ratio(2.50, horizon_years=3.0) == ("HIGH", 35.0)


def test_long_clock_never_loosens_broken_edge():
    """CONSERVATIVE-ONLY scaling (2026-07-02 review fix): the thesis prompt
    still pins risk_adj_target to a 12-18-month date, so a configured clock
    may only TIGHTEN the gate — 0.90x stays BROKEN at every horizon until the
    prompt is horizon-aware (two-sided honesty unlocks with the L3 batch)."""
    assert clamp_for_ratio(0.90) == ("BROKEN", 0.0)
    assert clamp_for_ratio(0.90, horizon_years=3.0) == ("BROKEN", 0.0)
    assert clamp_for_ratio(0.949, horizon_years=10.0) == ("BROKEN", 0.0)
    # Short clocks tighten the upper bands instead of loosening them:
    assert clamp_for_ratio(1.20, horizon_years=0.5) == ("MEDIUM", 25.0)


def test_config_clock_beats_model_emitted_clock():
    """2026-07-02 review fix: the hard gate must not take timing instructions
    from the model it exists to constrain. A model-emitted horizon that
    conflicts with the operator's is IGNORED and flagged."""
    parsed = {"risk_adj_target": 70.0, "conviction": "HIGH",
              "position_size_pct": 35, "thesis_horizon_years": 10.0}
    out, tg = enforce_trade_gate(parsed, spot=100.0, horizon_years=1.25)
    assert tg["horizon_years"] == 1.25
    assert tg["horizon_source"] == "config"
    assert tg["model_horizon_ignored"] == 10.0
    assert out["conviction"] == "BROKEN" and out["position_size_pct"] == 0.0
    assert "IGNORED" in format_enforcement(tg)


def test_enforce_reads_horizon_and_states_the_clock():
    parsed = {"risk_adj_target": 130.0, "conviction": "HIGH",
              "position_size_pct": 35, "thesis_horizon_years": 3.0}
    out, tg = enforce_trade_gate(parsed, spot=100.0)
    # ratio 1.3 on a 3y clock -> MEDIUM/25 (would be untouched on the default)
    assert out["conviction"] == "MEDIUM"
    assert out["position_size_pct"] == 25.0
    assert tg["horizon_years"] == 3.0
    assert tg["annualized_return"] == pytest.approx(1.3 ** (1 / 3) - 1, abs=1e-4)
    assert "3.0y clock" in format_enforcement(tg)
    assert out["thesis_horizon_years"] == 3.0  # persisted with the verdict


def test_enforce_default_clock_unchanged_behavior():
    parsed = {"risk_adj_target": 130.0, "conviction": "HIGH", "position_size_pct": 35}
    out, tg = enforce_trade_gate(parsed, spot=100.0)
    assert out["conviction"] == "HIGH"          # 1.3 >= 1.25 at the native clock
    assert tg["horizon_years"] == DEFAULT_HORIZON_YEARS
    assert out["thesis_horizon_years"] == DEFAULT_HORIZON_YEARS


def test_out_of_bounds_horizon_falls_back_loudly():
    parsed = {"risk_adj_target": 130.0, "conviction": "HIGH",
              "position_size_pct": 35, "thesis_horizon_years": 50.0}
    out, tg = enforce_trade_gate(parsed, spot=100.0)
    assert tg["horizon_years"] == DEFAULT_HORIZON_YEARS
    assert tg["horizon_fallback"] is True
    assert "out of bounds" in format_enforcement(tg)


# ── truncation-guard predicate (sprint 2.4) ─────────────────────────────────────

def test_truncated_or_empty_output_rejected():
    assert thesis_output_usable(None) is False
    assert thesis_output_usable({}) is False
    assert thesis_output_usable({"thesis_target": None, "conviction": None}) is False
    assert thesis_output_usable({"currency": "USD"}) is False


def test_real_verdict_accepted():
    assert thesis_output_usable({"thesis_target": 1300}) is True
    assert thesis_output_usable({"conviction": "BROKEN"}) is True
    assert thesis_output_usable({"risk_adj_target": 436}) is True
