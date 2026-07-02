"""Unit tests for consensus.py — the self-consistency mode-of-N aggregator (P1).

Pure functions, no network/DB. Run: pytest scripts/test_consensus.py -v
"""

import consensus as cn


# ── env helper ──────────────────────────────────────────────────────────────────

def test_self_consistency_n_default_is_one(monkeypatch):
    monkeypatch.delenv("SELF_CONSISTENCY_N", raising=False)
    assert cn.self_consistency_n() == 1


def test_self_consistency_n_reads_int(monkeypatch):
    monkeypatch.setenv("SELF_CONSISTENCY_N", "5")
    assert cn.self_consistency_n() == 5


def test_self_consistency_n_clamps_and_degrades(monkeypatch):
    # 0, negative, and garbage all degrade to today's single-sample behavior
    monkeypatch.setenv("SELF_CONSISTENCY_N", "0")
    assert cn.self_consistency_n() == 1
    monkeypatch.setenv("SELF_CONSISTENCY_N", "-3")
    assert cn.self_consistency_n() == 1
    monkeypatch.setenv("SELF_CONSISTENCY_N", "abc")
    assert cn.self_consistency_n() == 1


# ── median ───────────────────────────────────────────────────────────────────────

def test_median_odd_even_and_garbage():
    assert cn._median([3, 1, 2]) == 2.0                 # odd -> middle
    assert cn._median([1, 2, 3, 4]) == 2.5              # even -> mean of middle two
    assert cn._median(["131", 200.0, None, True]) == 165.5  # coerce strings, skip None/bool
    assert cn._median([None, "garbage"]) is None        # nothing numeric -> None
    assert cn._median([]) is None


# ── aggregate_samples: the core mode-of-N contract ──────────────────────────────

def test_empty_returns_empty():
    assert cn.aggregate_samples([]) == {}
    assert cn.aggregate_samples([None, "x"]) == {}      # non-dicts filtered out


def test_single_sample_is_a_noop():
    s = {"verdict": "OVERVALUED", "confidence": "HIGH", "target_low": 100, "target_high": 200,
         "reasoning_bullets": ["a", "b"]}
    out = cn.aggregate_samples([s])
    # every original field preserved, verdict/targets untouched
    assert out["verdict"] == "OVERVALUED"
    assert out["target_low"] == 100 and out["target_high"] == 200
    assert out["reasoning_bullets"] == ["a", "b"]
    # only the trivially-stable fingerprint fields are added
    assert out["consistency"] == 1.0
    assert out["n_samples"] == 1


def test_modal_verdict_and_median_targets():
    # 3 OVERVALUED vs 2 UNDERVALUED -> modal OVERVALUED, consistency 3/5
    samples = [
        {"verdict": "OVERVALUED", "confidence": "HIGH", "target_low": 90, "target_high": 110},
        {"verdict": "OVERVALUED", "confidence": "HIGH", "target_low": 100, "target_high": 130},
        {"verdict": "OVERVALUED", "confidence": "MEDIUM", "target_low": 110, "target_high": 120},
        {"verdict": "UNDERVALUED", "confidence": "LOW", "target_low": 300, "target_high": 400},
        {"verdict": "UNDERVALUED", "confidence": "LOW", "target_low": 320, "target_high": 420},
    ]
    out = cn.aggregate_samples(samples)
    assert out["verdict"] == "OVERVALUED"
    assert out["consistency"] == 0.6           # 3 of 5
    assert out["n_samples"] == 5
    assert out["confidence"] == "HIGH"         # modal confidence among ALL samples
    # medians taken ONLY across the 3 OVERVALUED samples (90/100/110 -> 100; 110/120/130 -> 120)
    assert out["target_low"] == 100
    assert out["target_high"] == 120


def test_tie_is_deterministic_first_seen():
    # 2 vs 2: modal_consistency breaks ties by first insertion order
    samples = [
        {"verdict": "REGIME_UPSIDE", "confidence": "HIGH", "target_low": 10, "target_high": 20},
        {"verdict": "REGIME_DOWNSIDE", "confidence": "LOW", "target_low": 5, "target_high": 8},
        {"verdict": "REGIME_UPSIDE", "confidence": "HIGH", "target_low": 12, "target_high": 22},
        {"verdict": "REGIME_DOWNSIDE", "confidence": "LOW", "target_low": 6, "target_high": 9},
    ]
    out = cn.aggregate_samples(samples)
    assert out["verdict"] == "REGIME_UPSIDE"   # first-seen wins the tie
    assert out["consistency"] == 0.5           # 2 of 4
    assert out["target_low"] == 11             # median of the two UPSIDE lows (10, 12)


def test_all_different_consistency_is_one_over_n():
    samples = [
        {"verdict": "OVERVALUED", "confidence": "HIGH", "target_low": 1, "target_high": 2},
        {"verdict": "FAIRLY_VALUED", "confidence": "MEDIUM", "target_low": 3, "target_high": 4},
        {"verdict": "UNDERVALUED", "confidence": "LOW", "target_low": 5, "target_high": 6},
    ]
    out = cn.aggregate_samples(samples)
    assert out["verdict"] == "OVERVALUED"      # first-seen
    assert out["consistency"] == round(1 / 3, 3)
    # only the modal-verdict cohort (the single OVERVALUED sample) feeds the band
    assert out["target_low"] == 1 and out["target_high"] == 2


def test_model_c_no_verdict_uses_confidence_consistency():
    # Adversarial model C emits no verdict; consistency falls back to confidence
    samples = [
        {"confidence": "LOW", "reasoning_bullets": ["bear x"]},
        {"confidence": "LOW", "reasoning_bullets": ["bear y"]},
        {"confidence": "MEDIUM", "reasoning_bullets": ["bear z"]},
    ]
    out = cn.aggregate_samples(samples)
    assert "verdict" not in out                # no spurious verdict key invented
    assert out["confidence"] == "LOW"          # modal confidence
    assert out["consistency"] == round(2 / 3, 3)   # confidence stability, not verdict
    assert out["n_samples"] == 3


# ── wiring into run_socratic.run_round_1_parallel (no network; run_one_model mocked) ──

def test_run_round_1_noop_when_n_is_1(monkeypatch):
    monkeypatch.delenv("SELF_CONSISTENCY_N", raising=False)
    import threading
    import run_socratic as rs

    calls, lock = [], threading.Lock()

    def fake(role, ctx, allowed):
        with lock:
            calls.append(role)
        return {"role": role, "parsed": {"verdict": f"V_{role}", "confidence": "HIGH"},
                "text": "t", "input_tokens": 1, "output_tokens": 2,
                "web_search_count": 0, "prompt_version": "v1", "model_used": "m"}

    monkeypatch.setattr(rs, "run_one_model", fake)
    out = rs.run_round_1_parallel({"ticker": "TEST"}, [])

    assert sorted(calls) == ["a", "b", "c"]                 # exactly one call per model
    # parsed returned untouched — no aggregation fields injected at N=1
    assert out["a"]["parsed"] == {"verdict": "V_a", "confidence": "HIGH"}
    assert "consistency" not in out["b"]["parsed"]
    assert "n_samples" not in out["a"]


def test_run_round_1_aggregates_when_n_gt_1(monkeypatch):
    monkeypatch.setenv("SELF_CONSISTENCY_N", "3")
    import itertools
    import threading
    import run_socratic as rs

    idx = {r: itertools.count() for r in ("a", "b", "c")}
    n_calls, lock = {"n": 0}, threading.Lock()
    # B is the noisy model: 2× DOWNSIDE, 1× NO_SHIFT -> modal DOWNSIDE, consistency 2/3
    plans = {
        "a": [{"verdict": "OVERVALUED", "confidence": "HIGH", "target_low": 90, "target_high": 110}] * 3,
        "b": [{"verdict": "REGIME_DOWNSIDE", "confidence": "MEDIUM", "target_low": 80, "target_high": 100},
              {"verdict": "REGIME_DOWNSIDE", "confidence": "MEDIUM", "target_low": 82, "target_high": 102},
              {"verdict": "NO_REGIME_SHIFT", "confidence": "LOW", "target_low": 120, "target_high": 140}],
        "c": [{"confidence": "LOW"}, {"confidence": "LOW"}, {"confidence": "MEDIUM"}],
    }

    def fake(role, ctx, allowed):
        with lock:
            n_calls["n"] += 1
        i = next(idx[role])
        return {"role": role, "parsed": dict(plans[role][i]),
                "text": "t", "input_tokens": 10, "output_tokens": 20,
                "web_search_count": 1, "prompt_version": "v1", "model_used": "m"}

    monkeypatch.setattr(rs, "run_one_model", fake)
    out = rs.run_round_1_parallel({"ticker": "TEST"}, [])

    assert n_calls["n"] == 9                                # 3 models × 3 samples
    # B consensus: modal DOWNSIDE, consistency 2/3, median band over the 2 DOWNSIDE samples
    assert out["b"]["parsed"]["verdict"] == "REGIME_DOWNSIDE"
    assert out["b"]["parsed"]["consistency"] == round(2 / 3, 3)
    assert out["b"]["parsed"]["n_samples"] == 3
    assert out["b"]["parsed"]["target_low"] == 81          # median of 80, 82 (NO_SHIFT excluded)
    assert out["b"]["input_tokens"] == 30                  # tokens summed across all 3 samples
    # A unanimous -> consistency 1.0
    assert out["a"]["parsed"]["consistency"] == 1.0
