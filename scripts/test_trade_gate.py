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
