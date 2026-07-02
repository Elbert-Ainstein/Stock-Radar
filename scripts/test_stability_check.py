"""Stability-harness aggregation tests — PURE, no network/LLM.

Run: pytest scripts/test_stability_check.py -v
"""

import stability_check as sc


# ── modal_consistency ───────────────────────────────────────────────────────────

def test_modal_consistency():
    assert sc.modal_consistency(["x", "x", "x"]) == ("x", 1.0)
    assert sc.modal_consistency(["x", "x", "y"]) == ("x", round(2 / 3, 3))
    assert sc.modal_consistency([]) == (None, 0.0)
    assert sc.modal_consistency([None, None]) == (None, 0.0)
    # Nones are ignored in the denominator
    assert sc.modal_consistency(["x", None, "x"]) == ("x", 1.0)


# ── summarize_condition (uses net_direction over A/B) ───────────────────────────

def _runs(a, b, n):
    return [{"a": a, "b": b, "c": None} for _ in range(n)]


def test_summarize_stable_down():
    s = sc.summarize_condition(_runs("OVERVALUED", "REGIME_DOWNSIDE", 5))
    assert s["n"] == 5
    assert s["per_model"]["a"]["modal"] == "OVERVALUED" and s["per_model"]["a"]["consistency"] == 1.0
    assert s["modal_lean"] == "down" and s["lean_consistency"] == 1.0


def test_summarize_noisy_model():
    runs = [{"a": "OVERVALUED", "b": "REGIME_DOWNSIDE", "c": None},
            {"a": "UNDERVALUED", "b": "REGIME_DOWNSIDE", "c": None},
            {"a": "OVERVALUED", "b": "REGIME_UPSIDE", "c": None}]
    s = sc.summarize_condition(runs)
    assert s["per_model"]["a"]["consistency"] == round(2 / 3, 3)   # A flips
    assert s["lean_consistency"] < 1.0                              # lean unstable


# ── compare_conditions: signal vs noise vs inconclusive ─────────────────────────

def test_compare_signal_when_lean_changes_and_both_stable():
    off = sc.summarize_condition(_runs("OVERVALUED", "REGIME_DOWNSIDE", 5))   # lean down, cons 1.0
    on = sc.summarize_condition(_runs("UNDERVALUED", "REGIME_UPSIDE", 5))     # lean up,   cons 1.0
    c = sc.compare_conditions(off, on)
    assert c["chain_changed_lean"] is True and "signal" in c["verdict"]


def test_compare_no_effect_when_lean_same_and_stable():
    off = sc.summarize_condition(_runs("OVERVALUED", "REGIME_DOWNSIDE", 5))
    on = sc.summarize_condition(_runs("OVERVALUED", "REGIME_DOWNSIDE", 5))
    c = sc.compare_conditions(off, on)
    assert c["chain_changed_lean"] is False and "no effect" in c["verdict"]


def test_compare_inconclusive_when_noisy():
    # off is noisy (lean flips run-to-run) -> can't attribute any change
    off = sc.summarize_condition([
        {"a": "OVERVALUED", "b": "REGIME_DOWNSIDE", "c": None},
        {"a": "UNDERVALUED", "b": "REGIME_UPSIDE", "c": None},
        {"a": "FAIRLY_VALUED", "b": "NO_REGIME_SHIFT", "c": None},
    ])
    on = sc.summarize_condition(_runs("UNDERVALUED", "REGIME_UPSIDE", 3))
    c = sc.compare_conditions(off, on)
    assert "inconclusive" in c["verdict"]


def test_render_report_smoke():
    off = sc.summarize_condition(_runs("OVERVALUED", "REGIME_DOWNSIDE", 3))
    on = sc.summarize_condition(_runs("UNDERVALUED", "REGIME_UPSIDE", 3))
    out = sc.render_report("LITE", off, on, sc.compare_conditions(off, on))
    assert "stability: LITE" in out and "chain OFF" in out and "CHAIN EFFECT:" in out


# ── --price plumbing (no network; build_context + round_1 mocked) ───────────────

def test_run_stability_pins_price_via_override(monkeypatch):
    import run_socratic as rs

    seen = []

    def fake_build_context(ticker, *, include_chain=True, spot_override=None, **kw):
        seen.append({"include_chain": include_chain, "spot_override": spot_override})
        return {"ticker": ticker.upper(), "spot_raw": spot_override or 0.0}

    def fake_round_1(ctx, allowed):
        return {"a": {"parsed": {"verdict": "OVERVALUED"}},
                "b": {"parsed": {"verdict": "REGIME_DOWNSIDE"}},
                "c": {"parsed": {}}}

    monkeypatch.setattr(rs, "build_context", fake_build_context)
    monkeypatch.setattr(rs, "run_round_1_parallel", fake_round_1)

    sc.run_stability("LITE", k=1, price=800.0)

    # both conditions (chain off, then on) were built at the SAME pinned price
    assert [s["spot_override"] for s in seen] == [800.0, 800.0]
    assert [s["include_chain"] for s in seen] == [False, True]
