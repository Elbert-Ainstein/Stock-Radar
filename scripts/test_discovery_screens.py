"""Tests for discovery_screens.py (L2 slice 1) and hypotheses.py (L7)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import discovery_screens as ds
import hypotheses as hyp
from run_checkpoint import is_gradeable_seal
from trade_gate import enforce_trade_gate


# ─── S1: anomaly that survives verification ──────────────────────────

SNDK_WARNINGS = [
    "TRAJECTORY ANOMALY (advisory): 1Q26 revenue $5.95B is 2.7x the trailing "
    "4Q avg $2.23B (threshold: 2.0x for this revenue scale).",
    "SUSPECT DATA: 1Q26 revenue $5.95B is 3.5x same-quarter-last-year $1.70B.",
]


def test_s1_fires_on_verified_anomaly():
    s1 = ds.screen_s1(SNDK_WARNINGS, fetch_succeeded=True)
    assert s1 and s1["screen"] == "S1"
    assert len(s1["evidence"]) == 2


def test_s1_requires_successful_fetch():
    # A failed fetch = EDGAR rejected or unusable data: the anomaly did NOT
    # survive verification.
    assert ds.screen_s1(SNDK_WARNINGS, fetch_succeeded=False) is None


def test_s1_no_anomaly_no_pass():
    assert ds.screen_s1(["OVERRIDE: provider fallback engaged"]) is None
    assert ds.screen_s1([]) is None


def test_s1_edgar_unavailable_is_not_survival():
    # finance_data is FAIL-OPEN when EDGAR itself is unreachable (foreign
    # filer, no CIK, network): the fetch succeeds with anomalies intact plus
    # an unavailability marker. That anomaly was never verified — no pass.
    warnings = SNDK_WARNINGS + [
        "EDGAR cross-check unavailable for 6082.HK (no CIK) — provider data "
        "accepted without SEC verification"]
    assert ds.screen_s1(warnings, fetch_succeeded=True) is None


# ─── S3: smart money before analysts ─────────────────────────────────

ADDS = [{"manager": "coatue", "kind": "new_position",
         "tag": "13f_coatue_2026Q1_new_position"}]


def test_13f_tag_parser_matches_gen2_artifact():
    # discovery_13f.upsert_candidate writes `source` as a comma-joined tag
    # STRING — parse the real shape, not an imagined jsonb.
    adds = ds.parse_13f_source_tags(
        "news_seed, 13f_druckenmiller_2026Q1_new_position, 13f_coatue_2026Q1_increase")
    assert len(adds) == 2
    assert adds[0]["manager"] == "druckenmiller" and adds[0]["kind"] == "new_position"
    assert adds[1]["manager"] == "coatue" and adds[1]["kind"] == "increase"
    assert ds.parse_13f_source_tags(None) == []
    assert ds.parse_13f_source_tags("news_seed, insider_buy") == []


def test_s3_fires_on_adds_with_low_coverage():
    s3 = ds.screen_s3(ADDS, analyst_coverage=0)
    assert s3 and s3["screen"] == "S3"
    assert "coverage 0" in s3["summary"]


def test_s3_unknown_coverage_is_not_zero_coverage():
    assert ds.screen_s3(ADDS, analyst_coverage=None) is None


def test_s3_high_coverage_no_pass():
    assert ds.screen_s3(ADDS, analyst_coverage=12) is None


def test_s3_no_adds_no_pass():
    assert ds.screen_s3([], analyst_coverage=0) is None


# ─── trigger derivation ──────────────────────────────────────────────

def test_operator_trigger_wins():
    trig, src = ds.derive_trigger_price(
        thesis_row={"risk_adj_target": 100}, operator_trigger=38.5)
    assert trig == 38.5 and src == "operator"


def test_thesis_actionability_trigger():
    # risk_adj_target 95 on the default clock: gate stops saying BROKEN when
    # spot <= 95/0.95 = 100.
    trig, src = ds.derive_trigger_price(thesis_row={"risk_adj_target": 95.0})
    assert abs(trig - 100.0) < 0.01 and src == "thesis_actionability"


def test_thesis_trigger_respects_the_clock():
    # On a 3y clock the LOW bound is 0.95^(3/1.25) ≈ 0.8840 → higher trigger.
    trig, _ = ds.derive_trigger_price(
        thesis_row={"risk_adj_target": 95.0, "thesis_horizon_years": 3.0})
    assert trig > 100.0


def test_no_trigger_derivable_is_stated_not_invented():
    trig, src = ds.derive_trigger_price(thesis_row=None, operator_trigger=None)
    assert trig is None and src == "none_derivable"


# ─── acceptance: the SNDK-at-$38.50 shape (design doc L2) ────────────

def test_sndk_shape_passes_s1_s3_into_stalk_while_allocation_refuses():
    """The design-doc acceptance: a backtest-style dry run shows the
    SNDK-at-$38.50 shape passing S1+S3 into STALK with a trigger, while the
    allocation gate still (correctly) refuses to size it that day."""
    s1 = ds.screen_s1(SNDK_WARNINGS)
    s3 = ds.screen_s3(ADDS, analyst_coverage=1)
    trig, src = ds.derive_trigger_price(operator_trigger=38.5)
    stalk = ds.assemble_stalk("SNDK", screens=[s1, s3], spot=55.0,
                              trigger_price=trig, trigger_source=src,
                              now=datetime(2026, 7, 8, tzinfo=timezone.utc))
    assert stalk["stance"] == "STALK"
    assert stalk["screens_passed"] == ["S1", "S3"]
    assert stalk["trigger_price"] == 38.5
    # STALK is a stance, never a conviction, never a size.
    assert "conviction" not in stalk and "position_size_pct" not in stalk
    # Meanwhile the ALLOCATION gate, fed the same day's numbers, still
    # refuses — discovery and allocation are different machines.
    parsed, record = enforce_trade_gate(
        {"risk_adj_target": 40.0, "conviction": "HIGH", "position_size_pct": 25},
        spot=55.0)
    assert parsed["conviction"] == "BROKEN" and parsed["position_size_pct"] == 0.0


def test_no_screens_no_stalk():
    assert ds.assemble_stalk("SNDK", screens=[], spot=55.0,
                             trigger_price=38.5, trigger_source="operator") is None


# ─── seal discipline (L8) ────────────────────────────────────────────

def test_stalk_seal_is_recorded_but_never_gradeable():
    stalk = ds.assemble_stalk("SNDK", screens=[ds.screen_s1(SNDK_WARNINGS)],
                              spot=55.0, trigger_price=38.5,
                              trigger_source="operator",
                              now=datetime(2026, 7, 8, tzinfo=timezone.utc))
    row = ds.stalk_seal_row(stalk)
    assert row["run_id"].startswith("stalk-sndk-")
    assert "reasoning_fingerprint" not in row  # never masquerades as socratic
    # Pinned against the REAL grader filter: the socratic calibration loop
    # must classify this row as not gradeable.
    ok, reason = is_gradeable_seal(row)
    assert ok is False and reason == "not_socratic"


def test_stalk_seal_evidence_survives_coercion_to_db_row():
    """Pinned through the REAL persistence layer: prediction_logger._coerce_row
    whitelists columns — the first cut carried evidence in a 'notes' key that
    was silently dropped client-side (review finding). The payload must ride
    a whitelisted column and the COERCED row must still be ungradeable."""
    from prediction_logger import _coerce_row
    stalk = ds.assemble_stalk("SNDK", screens=[ds.screen_s1(SNDK_WARNINGS)],
                              spot=55.0, trigger_price=38.5,
                              trigger_source="operator")
    coerced = _coerce_row(ds.stalk_seal_row(stalk))
    ci = coerced.get("context_inputs") or {}
    assert ci.get("kind") == "stalk_emission"
    assert ci.get("screens_passed") == ["S1"]
    assert ci.get("trigger_source") == "operator"
    assert coerced.get("target_base") == 38.5
    ok, reason = is_gradeable_seal(coerced)
    assert ok is False and reason == "not_socratic"


# ─── trigger breach check (pure; used by refresh_prices) ─────────────

def test_trigger_breach_detection():
    stalks = [{"ticker": "SNDK", "trigger_price": 38.5},
              {"ticker": "LITE", "trigger_price": 500.0},
              {"ticker": "NOPX", "trigger_price": None}]
    quotes = {"SNDK": 38.4, "LITE": 700.0}
    breaches = ds.check_trigger_breach(stalks, quotes)
    assert [b["ticker"] for b in breaches] == ["SNDK"]
    assert breaches[0]["price"] == 38.4


def test_breach_requires_quote():
    assert ds.check_trigger_breach([{"ticker": "SNDK", "trigger_price": 38.5}], {}) == []


# ─── L7 hypotheses ───────────────────────────────────────────────────

HYPOTHESIS_MD = """---
status: active
tickers: [LITE, RKLB]
horizon_years: 3.0
---

## Claim

Two-wave robotics demand hits optics before the market reprices it.
"""


def test_hypothesis_parse_and_ticker_filter():
    h = hyp.parse_hypothesis(HYPOTHESIS_MD, name="two-wave-robotics")
    assert h["status"] == "active" and h["tickers"] == ["LITE", "RKLB"]
    assert hyp.active_for_ticker("LITE", [h]) == [h]
    assert hyp.active_for_ticker("SNDK", [h]) == []


def test_template_status_never_injected():
    h = hyp.parse_hypothesis(HYPOTHESIS_MD.replace("status: active",
                                                   "status: template"), name="t")
    assert hyp.active_for_ticker("LITE", [h]) == []


def test_block_empty_without_active_hypotheses():
    assert hyp.format_hypotheses_block("LITE", []) == ""


def test_block_frames_falsification():
    h = hyp.parse_hypothesis(HYPOTHESIS_MD, name="two-wave-robotics")
    block = hyp.format_hypotheses_block("LITE", [h])
    assert "FALSIFICATION" in block
    assert "two-wave-robotics" in block
    assert "3.0y clock" in block


def test_malformed_hypothesis_skipped_not_fatal():
    assert hyp.parse_hypothesis("no frontmatter at all", name="bad") is None
    assert hyp.parse_hypothesis("---\n[1,2,3]\n---\nbody", name="list") is None


def test_comma_separated_tickers_without_brackets():
    # `tickers: LITE, RKLB` parses as one YAML string — must split, or the
    # hypothesis silently never matches any ticker (review finding).
    h = hyp.parse_hypothesis(
        HYPOTHESIS_MD.replace("tickers: [LITE, RKLB]", "tickers: LITE, RKLB"),
        name="commas")
    assert h["tickers"] == ["LITE", "RKLB"]


def test_bracket_tokens_in_body_neutralized():
    # Hypothesis bodies are injected BEFORE later placeholder fills — a
    # literal [VERIFIED_FINANCIALS] would macro-expand inside operator prose
    # (the socratic fill() splice class; review finding).
    md = HYPOTHESIS_MD + "\nCheck against [VERIFIED_FINANCIALS] and [PRICE]."
    h = hyp.parse_hypothesis(md, name="brackets")
    assert "[VERIFIED_FINANCIALS]" not in h["body"]
    assert "(VERIFIED_FINANCIALS)" in h["body"]
    assert "[PRICE]" not in h["body"]


def test_repo_template_parses_and_is_inert():
    text = (Path(hyp.HYPOTHESES_DIR) / "TEMPLATE.md").read_text(encoding="utf-8")
    h = hyp.parse_hypothesis(text, name="TEMPLATE")
    assert h is not None and h["status"] == "template"
    assert hyp.active_for_ticker("LITE", [h]) == []
