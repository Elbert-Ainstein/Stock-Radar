"""Model D scenario parser tests — PURE, no network/LLM.

The parser is the safety boundary: it must reject anything malformed and must
enforce a complete (sums-to-1, downside-included) scenario set, so a generated
vision valuation can't quietly omit the failure case.

Run: pytest scripts/test_model_d_generate.py -v
"""

import pytest

import model_d_generate as g
from model_d import optionality_value


def _ok():
    return {"scenarios": [
        {"label": "vision", "prob": 0.3, "tam_usd": 60e9, "capture": 0.18, "net_margin": 0.30, "exit_pe": 38},
        {"label": "base", "prob": 0.45, "tam_usd": 40e9, "capture": 0.20, "net_margin": 0.28, "exit_pe": 32},
        {"label": "downside", "prob": 0.25, "tam_usd": 25e9, "capture": 0.10, "net_margin": 0.20, "exit_pe": 20},
    ]}


def test_parse_valid_dict_and_bare_list():
    sc = g.parse_vision_scenarios(_ok())
    assert len(sc) == 3 and sc[0].label == "vision"
    # parsed scenarios flow straight into the pure math
    r = optionality_value(sc, shares=105e6, discount_rate=0.12, years=3)
    assert r["optionality_target"] > 0 and r["prob_total"] == 1.0
    # bare list form also accepted
    assert len(g.parse_vision_scenarios(_ok()["scenarios"])) == 3


def test_missing_field_raises():
    bad = _ok()
    del bad["scenarios"][0]["exit_pe"]
    with pytest.raises(ValueError):
        g.parse_vision_scenarios(bad)


def test_out_of_range_raises():
    for field, val in [("prob", 1.5), ("capture", 1.4)]:
        bad = _ok()
        bad["scenarios"][0][field] = val
        # (probs may no longer sum to 1 either, but the range check should fire)
        with pytest.raises(ValueError):
            g.parse_vision_scenarios(bad)
    neg = _ok()
    neg["scenarios"][0]["exit_pe"] = -5
    with pytest.raises(ValueError):
        g.parse_vision_scenarios(neg)


def test_prob_sum_enforced():
    bad = _ok()
    bad["scenarios"][2]["prob"] = 0.05   # now sums to 0.80
    with pytest.raises(ValueError):
        g.parse_vision_scenarios(bad)


def test_empty_or_wrong_shape_raises():
    with pytest.raises(ValueError):
        g.parse_vision_scenarios({"scenarios": []})
    with pytest.raises(ValueError):
        g.parse_vision_scenarios({"nope": 1})
    with pytest.raises(ValueError):
        g.parse_vision_scenarios([{"label": "x"}])  # missing numeric fields


# ── JSON extraction from model prose ────────────────────────────────────────────

def test_should_run_model_d_gates_transformational_only():
    assert g.should_run_model_d("transformational") is True
    assert g.should_run_model_d("Transformational") is True
    assert g.should_run_model_d("cyclical") is False
    assert g.should_run_model_d("garp") is False
    assert g.should_run_model_d(None) is False
    assert g.should_run_model_d("") is False


def test_extract_json_variants():
    payload = '{"scenarios": [{"label": "a"}]}'
    assert g._extract_json(f"prose before ```json\n{payload}\n``` after") == {"scenarios": [{"label": "a"}]}
    assert g._extract_json(f"here it is: {payload} thanks") == {"scenarios": [{"label": "a"}]}
    assert g._extract_json("no json here") is None
