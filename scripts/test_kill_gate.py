"""D1 — archetype-routed kill gate tests (pure; no network).

Exhaustive over archetype × ratio band. This suite validates the ROUTING LOGIC.
(The live LITE run is only a wiring check — it does NOT prove 0.60 is the right
transformational floor; that's a calibration question for the feedback loop.)

Run: pytest scripts/test_kill_gate.py -v
"""

import kill_gate as kg


def _parsed(conviction="BROKEN", strategic="HIGH", ratio=0.78, pos=0.0, triggers=None):
    return {
        "conviction": conviction,
        "strategic_conviction": strategic,
        "risk_adj_ev_ratio": ratio,
        "position_size_pct": pos,
        "kill_triggers": triggers if triggers is not None else ["gross margin < 40% for 2Q"],
    }


# ── transformational: routed at the 0.60 floor ──────────────────────────────────

def test_transformational_above_floor_relaxes():
    out, ov = kg.apply_kill_gate(_parsed(ratio=0.78), "transformational")
    assert ov is not None
    assert out["conviction"] == "LOW"
    assert out["position_size_pct"] == 5.0
    # structured override is machine-readable
    assert ov["raw_verdict"] == "BROKEN" and ov["routed_verdict"] == "LOW"
    assert ov["risk_adj_ev_ratio"] == 0.78 and ov["archetype_floor"] == 0.60
    assert out["kill_gate_override"] == ov
    # prose note also appended for humans
    assert any("kill_gate_override" in t for t in out["kill_triggers"])


def test_transformational_below_floor_still_broken():
    out, ov = kg.apply_kill_gate(_parsed(ratio=0.55), "transformational")
    assert ov is None
    assert out["conviction"] == "BROKEN"  # 0.55 < 0.60 -> still killed


def test_transformational_at_floor_boundary_relaxes():
    out, ov = kg.apply_kill_gate(_parsed(ratio=0.60), "transformational")
    assert ov is not None  # >= floor


# ── non-routed archetypes: strict no-op (behaviour unchanged) ───────────────────

def test_cyclical_unchanged():
    out, ov = kg.apply_kill_gate(_parsed(ratio=0.78), "cyclical")
    assert ov is None and out["conviction"] == "BROKEN"


def test_garp_unchanged_even_high_ratio():
    out, ov = kg.apply_kill_gate(_parsed(ratio=0.88), "garp")
    assert ov is None and out["conviction"] == "BROKEN"


def test_none_archetype_unchanged():
    out, ov = kg.apply_kill_gate(_parsed(ratio=0.78), None)
    assert ov is None


# ── pre-revenue: gate disabled regardless of archetype/ratio ────────────────────

def test_pre_revenue_disables_gate():
    out, ov = kg.apply_kill_gate(_parsed(ratio=0.40), "garp", pre_revenue=True)
    assert ov is not None
    assert ov["archetype_floor"] is None
    assert "pre-revenue" in ov["reason"]
    assert out["conviction"] == "LOW"


# ── guards: never un-break a real thesis break / non-kill ───────────────────────

def test_real_thesis_break_not_relaxed():
    # strategic also BROKEN -> genuine break, never routed
    out, ov = kg.apply_kill_gate(_parsed(strategic="BROKEN", ratio=0.78), "transformational")
    assert ov is None and out["conviction"] == "BROKEN"


def test_non_broken_conviction_untouched():
    out, ov = kg.apply_kill_gate(_parsed(conviction="HIGH", ratio=0.78), "transformational")
    assert ov is None and out["conviction"] == "HIGH"


def test_missing_ratio_untouched():
    p = _parsed(ratio=None)
    out, ov = kg.apply_kill_gate(p, "transformational")
    assert ov is None


def test_does_not_mutate_input():
    p = _parsed(ratio=0.78)
    out, ov = kg.apply_kill_gate(p, "transformational")
    assert p["conviction"] == "BROKEN"  # original untouched
    assert out is not p


# ── helpers ─────────────────────────────────────────────────────────────────────

def test_pre_revenue_detection():
    assert kg.is_pre_revenue(5_000_000) is True
    assert kg.is_pre_revenue(50_000_000) is False
    assert kg.is_pre_revenue(None) is False


def test_archetype_kill_floor():
    assert kg.archetype_kill_floor("transformational") == 0.60
    assert kg.archetype_kill_floor("Transformational") == 0.60
    assert kg.archetype_kill_floor("cyclical") is None
    assert kg.archetype_kill_floor(None) is None
