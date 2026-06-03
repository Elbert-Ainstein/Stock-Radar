"""Unit tests for checkpoint_seal.py — pure functions, no network/DB.

Run: pytest scripts/test_checkpoint_seal.py -v
"""

from datetime import date
from pathlib import Path

import checkpoint_seal as cs


# ── confidence / direction primitives ──────────────────────────────────────────

def test_confidence_score_mapping():
    assert cs.confidence_score("HIGH") == 1.0
    assert cs.confidence_score("medium") == 0.66
    assert cs.confidence_score("Low") == 0.33
    assert cs.confidence_score(None) == 0.5
    assert cs.confidence_score("garbage") == 0.5


def test_verdict_direction_real_model_enums():
    # Model A (fundamentals)
    assert cs.verdict_direction("OVERVALUED") == -1
    assert cs.verdict_direction("UNDERVALUED") == 1
    assert cs.verdict_direction("FAIRLY_VALUED") == 0
    # Model B (regime)
    assert cs.verdict_direction("REGIME_UPSIDE") == 1
    assert cs.verdict_direction("REGIME_DOWNSIDE") == -1
    assert cs.verdict_direction("NO_REGIME_SHIFT") == 0
    # Chinese + unknown
    assert cs.verdict_direction("低估") == 1
    assert cs.verdict_direction("高估") == -1
    assert cs.verdict_direction("公允价值") == 0
    assert cs.verdict_direction("something_else") is None
    assert cs.verdict_direction(None) is None


def test_live_lite_shape_a_b_directional_c_no_verdict():
    # The real round_1 shape: A overvalued, B regime_downside, C adversarial (no verdict).
    r = {"a": {"verdict": "OVERVALUED", "confidence": "HIGH"},
         "b": {"verdict": "REGIME_DOWNSIDE", "confidence": "MEDIUM"},
         "c": {"confidence": "LOW"}}  # C emits no verdict
    # A and B both bearish -> they agree on direction
    assert cs.direction_agreement(r) == 1.0
    assert cs.directional_conflict(r) is False
    # dissent needs 3 recognised verdicts; only A/B vote -> None
    assert cs.dissenting_model(r) is None
    # conviction scoped to A,B confidences (HIGH, MEDIUM) -> mean 0.83 × 1.0
    conv = cs.conviction_proxy(r)
    assert conv == round(((1.0 + 0.66) / 2) * 1.0, 3)
    # C's LOW confidence must NOT pull conviction down (it's excluded)
    assert conv > 0.7


def test_directional_conflict_states():
    # A overvalued (-1) vs B regime_upside (+1) -> conflict
    assert cs.directional_conflict(_r("OVERVALUED", "HIGH", "REGIME_UPSIDE", "HIGH", None, "LOW")) is True
    # only one recognised verdict -> None
    assert cs.directional_conflict(_r("OVERVALUED", "HIGH", "garbage", "HIGH", None, "LOW")) is None


# ── agreement / conviction proxy ────────────────────────────────────────────────

def _r(va, ca, vb, cb, vc, cc):
    return {"a": {"verdict": va, "confidence": ca},
            "b": {"verdict": vb, "confidence": cb},
            "c": {"verdict": vc, "confidence": cc}}


def test_direction_agreement_unanimous_two_one_none():
    assert cs.direction_agreement(_r("低估", "HIGH", "低估", "HIGH", "低估", "HIGH")) == 1.0
    assert cs.direction_agreement(_r("低估", "HIGH", "低估", "HIGH", "高估", "LOW")) == round(2/3, 3)
    # all different directions -> modal count 1 of 3
    assert cs.direction_agreement(_r("低估", "HIGH", "高估", "HIGH", "公允价值", "LOW")) == round(1/3, 3)
    # no recognised verdicts -> 0.0
    assert cs.direction_agreement(_r("x", "HIGH", "y", "HIGH", "z", "LOW")) == 0.0


def test_direction_agreement_mixed_recognised():
    # 2 recognised (both upside) + 1 unrecognised -> agreement among recognised = 1.0
    assert cs.direction_agreement(_r("低估", "HIGH", "低估", "HIGH", "garbage", "LOW")) == 1.0
    # 2 recognised, opposite directions + 1 unrecognised -> 0.5
    assert cs.direction_agreement(_r("低估", "HIGH", "高估", "HIGH", "garbage", "LOW")) == 0.5


def test_conviction_proxy_range_and_value():
    # unanimous HIGH -> mean_conf 1.0 * agreement 1.0 = 1.0
    assert cs.conviction_proxy(_r("低估", "HIGH", "低估", "HIGH", "低估", "HIGH")) == 1.0
    # split lowers it
    val = cs.conviction_proxy(_r("低估", "HIGH", "高估", "LOW", "公允价值", "MEDIUM"))
    assert 0.0 <= val < 1.0
    # nothing -> 0
    assert cs.conviction_proxy({"a": {}, "b": {}, "c": {}}) == 0.0


def test_dissenting_model():
    # c dissents from an a/b upside majority
    assert cs.dissenting_model(_r("低估", "HIGH", "低估", "HIGH", "高估", "LOW")) == "c"
    # unanimous -> none
    assert cs.dissenting_model(_r("低估", "HIGH", "低估", "HIGH", "低估", "HIGH")) is None
    # all different -> none
    assert cs.dissenting_model(_r("低估", "HIGH", "高估", "HIGH", "公允价值", "LOW")) is None


def test_unresolved_questions_filters_judgment_only():
    dis = [
        {"type": "research", "question": "what is FY26 rev?"},
        {"type": "judgment", "question": "is the cycle turning?"},
        {"type": "judgment", "question": "is OCS priced in?"},
        {"type": "judgment"},  # no question -> skipped
    ]
    assert cs.unresolved_questions(dis) == ["is the cycle turning?", "is OCS priced in?"]
    assert cs.unresolved_questions(None) == []


def test_reasoning_fingerprint_shape_and_proxy_label():
    fp = cs.reasoning_fingerprint(
        _r("低估", "HIGH", "低估", "HIGH", "高估", "LOW"),
        [{"type": "judgment", "question": "cycle?"}],
    )
    assert fp["dissenting_model"] == "c"
    assert fp["unresolved_questions"] == ["cycle?"]
    assert fp["model_confidences"] == {"a": "HIGH", "b": "HIGH", "c": "LOW"}
    assert fp["conviction_source"] == "proxy"
    assert 0.0 <= fp["conviction"] <= 1.0


# ── cohort key ──────────────────────────────────────────────────────────────────

def test_cohort_key_stable_and_sensitive():
    pv = {"model_a": "v1", "model_b": "v1", "model_c": "v1", "corpus_callosum": "v1", "research_question": "v1"}
    k1 = cs.compute_cohort_key(pv, "filehash_AAAA")
    # stable for identical inputs
    assert cs.compute_cohort_key(pv, "filehash_AAAA") == k1
    # ignores non-judgment prompt keys (research_question change -> same key)
    pv_research = {**pv, "research_question": "v2"}
    assert cs.compute_cohort_key(pv_research, "filehash_AAAA") == k1
    # judgment prompt change -> different key
    pv_judge = {**pv, "model_b": "v2"}
    assert cs.compute_cohort_key(pv_judge, "filehash_AAAA") != k1
    # judgment FILE change -> different key
    assert cs.compute_cohort_key(pv, "filehash_BBBB") != k1


# ── date-pinned price pick (the P0 grading fix) ─────────────────────────────────

def test_close_on_or_after_exact_and_gap():
    series = [("2026-06-05", 100.0), ("2026-06-08", 110.0), ("2026-06-09", 111.0)]
    # exact trading day
    assert cs.close_on_or_after(series, date(2026, 6, 8)) == (110.0, "2026-06-08")
    # target on a weekend (06-06/07 missing) -> next trading day, date reported
    assert cs.close_on_or_after(series, date(2026, 6, 6)) == (110.0, "2026-06-08")
    # unsorted input still works
    assert cs.close_on_or_after(list(reversed(series)), date(2026, 6, 6)) == (110.0, "2026-06-08")
    # nothing on/after target -> None (no silent first-row fallback)
    assert cs.close_on_or_after(series, date(2026, 6, 20)) is None


def test_close_on_or_after_skips_bad_format_and_accepts_objects():
    from datetime import datetime as _dt
    # a non-ISO row ('6/8/2026') must be SKIPPED, not silently mis-compared
    series = [("6/8/2026", 999.0), ("2026-06-08", 110.0), ("2026-06-09", 111.0)]
    assert cs.close_on_or_after(series, date(2026, 6, 8)) == (110.0, "2026-06-08")
    # datetime objects in the series are accepted
    series2 = [(_dt(2026, 6, 8, 16, 0), 110.0), (_dt(2026, 6, 9), 111.0)]
    assert cs.close_on_or_after(series2, date(2026, 6, 8)) == (110.0, "2026-06-08")
    # all rows unparseable -> None (never a wrong-date price)
    assert cs.close_on_or_after([("6/8/2026", 999.0)], date(2026, 6, 8)) is None


# ── file hash + snapshot ────────────────────────────────────────────────────────

def test_file_content_hash_changes_with_content(tmp_path):
    (tmp_path / "scripts").mkdir()
    f = tmp_path / "scripts" / "analyst.py"
    f.write_text("a = 1\n")
    h1 = cs.file_content_hash(tmp_path, ["analyst.py"])
    f.write_text("a = 2\n")
    h2 = cs.file_content_hash(tmp_path, ["analyst.py"])
    assert h1 != h2
    # missing file uses a sentinel (does not raise) and differs from present
    h_missing = cs.file_content_hash(tmp_path, ["nope.py"])
    assert isinstance(h_missing, str) and len(h_missing) == 16


def test_build_seal_snapshot_cohort_break_logic():
    base = dict(
        ticker="lite", run_id="soc-1", ref_price=900.0,
        target_low=600.0, target_high=1500.0, target_base=None,
        round_1=_r("低估", "HIGH", "低估", "HIGH", "高估", "LOW"),
        disagreements=[{"type": "judgment", "question": "cycle?"}],
        prompt_versions={"model_a": "v1"}, socratic_analysis_id=1,
        system_version="abc1234", cohort_key="KEY_NEW",
    )
    # first seal ever (no prev) -> not a break
    snap = cs.build_seal_snapshot(prev_cohort_key=None, **base)
    assert snap["version_cohort_break"] is False
    assert snap["ticker"] == "LITE"
    assert snap["current_price"] == 900.0  # ref_price sealed
    assert snap["reasoning_fingerprint"]["conviction_source"] == "proxy"
    # same cohort as prev -> not a break
    assert cs.build_seal_snapshot(prev_cohort_key="KEY_NEW", **base)["version_cohort_break"] is False
    # different cohort -> break
    assert cs.build_seal_snapshot(prev_cohort_key="KEY_OLD", **base)["version_cohort_break"] is True
