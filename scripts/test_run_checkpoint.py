"""Unit tests for run_checkpoint.py — pure grading + ripeness helpers, no network/DB.

Run: pytest scripts/test_run_checkpoint.py -v
"""

from datetime import date

import run_checkpoint as rc


# ── direction implied by the band vs ref ────────────────────────────────────────

def test_expected_direction_band_fallback():
    # LITE band straddles ref: mid 925 vs ref 938 = -1.4%, inside dead-band -> 'flat'
    # (this is exactly why the band rule is only a FALLBACK; the models said 'down')
    assert rc.expected_direction(570, None, 1280, 938) == "flat"
    # clearly above ref -> up
    assert rc.expected_direction(900, None, 1300, 800) == "up"
    # within dead-band -> flat
    assert rc.expected_direction(99, None, 101, 100) == "flat"
    # base wins over midpoint when present
    assert rc.expected_direction(10, 200, 400, 100) == "up"
    # missing data -> None
    assert rc.expected_direction(None, None, None, 100) is None
    assert rc.expected_direction(90, None, 110, None) is None


def test_directional_correct():
    # thesis down, stock fell -> correct
    assert rc.directional_correct("down", 938, 812) is True
    # thesis down, stock rose -> wrong
    assert rc.directional_correct("down", 938, 1100) is False
    # thesis up, barely moved (within eps) -> actual 'flat' != 'up' -> wrong
    assert rc.directional_correct("up", 100, 101) is False
    # unknown expectation -> None
    assert rc.directional_correct(None, 100, 120) is None


def test_band_label():
    assert rc.band_label(1300, 570, 1280) == "at/above high"
    assert rc.band_label(500, 570, 1280) == "at/below low"
    assert rc.band_label(900, 570, 1280) == "within band"
    assert rc.band_label(None, 570, 1280) is None


def test_return_pct():
    assert rc.return_pct(812, 938) == -13.43
    assert rc.return_pct(1100, 1000) == 10.0
    assert rc.return_pct(100, None) is None
    assert rc.return_pct(100, 0) is None


def test_grade_lite_prefers_model_lean():
    # With the sealed lean = 'down' (A & B bearish), direction comes from the models.
    seal = {"current_price": 938, "target_low": 570, "target_base": None, "target_high": 1280,
            "reasoning_fingerprint": {"directional_lean": "down"}}
    g = rc.grade(seal, 812.0)
    assert g["expected_direction"] == "down"
    assert g["direction_source"] == "models"
    assert g["directional_correct"] is True   # fell, as the models implied
    assert g["band"] == "within band"
    assert g["return_pct"] == -13.43


def test_grade_falls_back_to_band_without_lean():
    # No fingerprint lean (older seal or model conflict) -> band rule -> 'flat' for LITE
    seal = {"current_price": 938, "target_low": 570, "target_base": None, "target_high": 1280}
    g = rc.grade(seal, 812.0)
    assert g["expected_direction"] == "flat"
    assert g["direction_source"] == "band"


# ── seal source/integrity filter (2026-07-02) ───────────────────────────────────

def test_gradeable_socratic_seal_passes():
    seal = {"run_id": "soc-98", "current_price": 786.9, "target_low": 512.0,
            "target_base": None, "target_high": 1506.0, "reasoning_fingerprint": {}}
    assert rc.is_gradeable_seal(seal) == (True, "ok")


def test_legacy_pipeline_row_excluded_as_not_socratic():
    # The engine-path snapshot rows: pipeline run_id, empty fingerprint,
    # all-zero targets (the bug that motivated the filter).
    junk = {"run_id": "e2f1c0aa-run", "current_price": 0, "target_low": 0.0,
            "target_base": 0, "target_high": 0.0, "reasoning_fingerprint": {}}
    assert rc.is_gradeable_seal(junk) == (False, "not_socratic")


def test_legacy_row_with_real_targets_still_excluded():
    # Even a well-formed legacy row is not a Socratic seal — source filter, not
    # just a junk filter.
    row = {"run_id": "pipeline-2026-06-01", "current_price": 100.0,
           "target_low": 70.0, "target_base": 100.0, "target_high": 130.0}
    assert rc.is_gradeable_seal(row) == (False, "not_socratic")


def test_seal_with_zero_ref_price_excluded():
    seal = {"run_id": "soc-77", "current_price": 0, "target_low": 512.0,
            "target_high": 1506.0}
    assert rc.is_gradeable_seal(seal) == (False, "zero_ref_price")


def test_seal_with_no_band_excluded():
    seal = {"run_id": "soc-77", "current_price": 786.9, "target_low": None,
            "target_base": 0, "target_high": None}
    assert rc.is_gradeable_seal(seal) == (False, "no_target_band")


def test_quarantined_row_excluded_first():
    seal = {"run_id": "soc-98", "current_price": 786.9, "target_low": 512.0,
            "target_high": 1506.0, "quarantined": True}
    assert rc.is_gradeable_seal(seal) == (False, "quarantined")


def test_fingerprint_qualifies_when_run_id_used_fallback():
    # seal_socratic_prediction falls back to run_at when socratic_id is None;
    # a non-empty fingerprint still marks it as a genuine seal post-migration.
    seal = {"run_id": "2026-06-03T22:00:00+00:00", "current_price": 938.0,
            "target_low": 570.0, "target_high": 1280.0,
            "reasoning_fingerprint": {"directional_lean": "down"}}
    assert rc.is_gradeable_seal(seal) == (True, "ok")


# ── ripeness ────────────────────────────────────────────────────────────────────

def test_ripe_horizons():
    sealed = "2026-06-03T22:00:00+00:00"
    # 31 days later: only T+30 ripe
    assert rc.ripe_horizons(sealed, date(2026, 7, 4)) == [(30, date(2026, 7, 3))]
    # 95 days later: all three ripe
    got = rc.ripe_horizons(sealed, date(2026, 9, 6))
    assert [h for h, _ in got] == [30, 60, 90]
    # same day: nothing ripe
    assert rc.ripe_horizons(sealed, date(2026, 6, 3)) == []
    # unparseable sealed_at -> empty, no raise
    assert rc.ripe_horizons("not-a-date", date(2026, 7, 4)) == []
