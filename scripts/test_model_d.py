"""Model D — optionality/TAM lens tests (pure, no network).

Hardened after a red-team pass: covers prob-sum enforcement, input validation,
equity floor, the vision_ev_share semantics, value monotonicity, order
independence, and bracket() edge cases — not just the happy path.

Run: pytest scripts/test_model_d.py -v
"""

import pytest

import model_d as md


def _s(label, prob, tam, capture, margin, pe):
    return md.VisionScenario(label=label, prob=prob, tam_usd=tam, capture=capture,
                             net_margin=margin, exit_pe=pe)


# ── scenario math ───────────────────────────────────────────────────────────────

def test_scenario_value_exact_no_discount():
    # 50B × .2 × .25 × 40 = 100B equity; /100M = $1000
    assert round(md.scenario_value_per_share(_s("m", 1, 50e9, .2, .25, 40), 100e6, 0.0, 0), 2) == 1000.0


def test_scenario_discounting_reduces_value():
    base = md.scenario_value_per_share(_s("x", 1, 50e9, .2, .25, 40), 100e6, 0.0, 5)
    disc = md.scenario_value_per_share(_s("x", 1, 50e9, .2, .25, 40), 100e6, 0.12, 5)
    assert disc < base
    assert round(disc, 2) == round(1000 / (1.12 ** 5), 2)


def test_equity_floored_at_zero_on_negative_margin():
    # loss-making terminal -> equity worthless (0), never negative
    assert md.scenario_value_per_share(_s("loss", 1, 50e9, .2, -0.1, 40), 100e6, 0.0, 0) == 0.0


def test_scenario_input_validation_raises():
    s = _s("x", 1, 50e9, .2, .25, 40)
    with pytest.raises(ValueError):
        md.scenario_value_per_share(s, shares=0, discount_rate=0.1, years=5)      # shares<=0
    with pytest.raises(ValueError):
        md.scenario_value_per_share(s, shares=100e6, discount_rate=-1.0, years=5)  # 1+r<=0
    with pytest.raises(ValueError):
        md.scenario_value_per_share(s, shares=100e6, discount_rate=0.1, years=-1)  # years<0


# ── probability enforcement (the critical fix) ──────────────────────────────────

def test_probs_must_sum_to_one():
    half = [_s("a", 0.25, 50e9, .2, .25, 40), _s("b", 0.25, 50e9, .1, .1, 20)]   # sum 0.5
    with pytest.raises(ValueError):
        md.optionality_value(half, 100e6, 0.0, 0)
    over = [_s("a", 0.6, 50e9, .2, .25, 40), _s("b", 0.6, 50e9, .1, .1, 20)]      # sum 1.2
    with pytest.raises(ValueError):
        md.optionality_value(over, 100e6, 0.0, 0)
    # within tolerance is fine
    ok = [_s("a", 0.5, 50e9, .2, .25, 40), _s("b", 0.5, 50e9, .1, .1, 20)]
    assert md.optionality_value(ok, 100e6, 0.0, 0)["optionality_target"] == 550.0


def test_empty_scenarios_returns_zeros():
    r = md.optionality_value([], 100e6)
    assert r["optionality_target"] == 0.0 and r["vision_ev_share"] is None and r["top_scenario"] is None


# ── weighting + vision_ev_share semantics ───────────────────────────────────────

def test_weighting_and_top_scenario():
    moon = _s("moon", 0.2, 50e9, .2, .25, 40)   # $1000/sh
    base = _s("base", 0.8, 50e9, .1, .1, 20)    # $100/sh
    r = md.optionality_value([moon, base], 100e6, 0.0, 0)
    assert r["optionality_target"] == 280.0        # .2*1000 + .8*100
    assert r["top_scenario"] == "moon"
    assert r["vision_ev_share"] == round(200 / 280, 3)   # 0.714 — EV is tail-led here


def test_vision_ev_share_low_when_top_is_low_prob():
    # honest case: highest-VALUE path is rare -> it carries little of the EV
    moon = _s("moon", 0.01, 50e9, .2, .25, 40)   # $1000/sh but 1% prob
    base = _s("base", 0.99, 50e9, .1, .1, 20)    # $100/sh
    r = md.optionality_value([moon, base], 100e6, 0.0, 0)
    # contrib moon=10, base=99, weighted=109 -> vision_ev_share≈0.092 (EV carried by base)
    assert r["top_scenario"] == "moon"
    assert r["vision_ev_share"] == round(10 / 109, 3)
    assert r["vision_ev_share"] < 0.15


# ── properties: monotonicity + order independence ───────────────────────────────

def test_monotonic_in_tam_and_horizon():
    v = lambda tam: md.scenario_value_per_share(_s("x", 1, tam, .2, .25, 40), 100e6, 0.1, 5)
    assert v(40e9) < v(50e9) < v(60e9)                       # TAM up -> value up
    d = lambda r: md.scenario_value_per_share(_s("x", 1, 50e9, .2, .25, 40), 100e6, r, 5)
    assert d(0.05) > d(0.12) > d(0.30)                       # discount up -> value down
    y = lambda yr: md.scenario_value_per_share(_s("x", 1, 50e9, .2, .25, 40), 100e6, 0.12, yr)
    assert y(2) > y(5) > y(8)                                # years up -> value down


def test_order_independent():
    a = _s("a", 0.3, 50e9, .2, .25, 40)
    b = _s("b", 0.7, 50e9, .1, .1, 20)
    assert md.optionality_value([a, b], 100e6, 0.0, 0)["optionality_target"] == \
           md.optionality_value([b, a], 100e6, 0.0, 0)["optionality_target"]


# ── bracket edge cases ──────────────────────────────────────────────────────────

def test_bracket_normal_and_edges():
    r = md.optionality_value([_s("v", 1.0, 50e9, .2, .25, 40)], 100e6, 0.0, 0)  # $1000
    assert md.bracket(600, r)["vision_over_floor_x"] == round(1000 / 600, 2)
    # engine_target = 0 (falsy) must NOT KeyError and must NOT divide -> None, key present
    z = md.bracket(0, r)
    assert z["vision_over_floor_x"] is None and z["engine_floor"] == 0 and z["vision_ceiling"] == 1000.0
    # engine_target None -> None, key present
    assert md.bracket(None, r)["vision_over_floor_x"] is None
