"""Tests for lessons L4/L5/L7 (2026-07-02 —
docs/design/HORIZON_DISCOVERY_TYPEA_2026-07-02.md):

L4: zero-result auto-diagnosis (tape vs ruler) — the 6/6-BROKEN incident must
    never again end in a silent shrug.
L5: kill triggers must be dated external signposts; archetype signpost
    templates cover every archetype.
L7: human-hypothesis intake loader.

Run: pytest scripts/test_lessons_l4_l5.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from kill_condition_eval import (
    ARCHETYPE_KILL_GUIDANCE,
    ARCHETYPE_KILL_TEMPLATES,
    lint_kill_triggers,
)
from registries import ALL_ARCHETYPES
from trade_gate import (
    DEFAULT_HORIZON_YEARS,
    gate_artifact_analysis,
    horizon_to_clear_low,
    is_actionable,
)


# ── L4: tape-vs-ruler math ──────────────────────────────────────────────────────

def test_horizon_to_clear_low():
    # 0.90 escapes the BROKEN band once the clock reaches ~2.57y
    assert horizon_to_clear_low(0.90) == pytest.approx(2.57, abs=0.02)
    # 0.55 (the LITE-shaped clamp) never clears within 10y — a tape call
    assert horizon_to_clear_low(0.55) is None
    # already above the native edge -> clears at the default clock
    assert horizon_to_clear_low(0.97) == DEFAULT_HORIZON_YEARS
    # garbage in, None out
    assert horizon_to_clear_low(None) is None
    assert horizon_to_clear_low(-1) is None


def test_is_actionable():
    assert is_actionable("MEDIUM") and is_actionable("low") and is_actionable("HIGH")
    assert not is_actionable("BROKEN") and not is_actionable(None) and not is_actionable("")


def test_gate_artifact_analysis_separates_tape_from_ruler():
    """A 6/6-BROKEN-shaped sweep: one deep clamp (tape), one shallow clamp
    that a longer clock would clear (ruler suspect)."""
    entries = [
        {"ticker": "LITE", "ratio": 0.55, "horizon_years": 1.25, "conviction": "BROKEN"},
        {"ticker": "ACHR", "ratio": 0.90, "horizon_years": 1.25, "conviction": "BROKEN"},
    ]
    report = gate_artifact_analysis(entries)
    assert "ZERO ACTIONABLE VERDICTS" in report
    assert "LITE" in report and "tape is expensive" in report
    assert "ACHR" in report and "RULER SUSPECT" in report and "2.57y" in report
    assert "SUMMARY" in report


def test_gate_artifact_analysis_all_tape():
    entries = [
        {"ticker": "A", "ratio": 0.50, "horizon_years": 1.25, "conviction": "BROKEN"},
        {"ticker": "B", "ratio": 0.45, "horizon_years": 3.0, "conviction": "BROKEN"},
    ]
    report = gate_artifact_analysis(entries)
    assert "predominantly a tape call" in report
    assert "STALK" in report  # points at discovery mode, not force-buying


def test_gate_artifact_analysis_handles_missing_ratio():
    report = gate_artifact_analysis([{"ticker": "X", "ratio": None, "conviction": "BROKEN"}])
    assert "data/parse problem" in report


# ── L5: signpost linter + templates ─────────────────────────────────────────────

def test_vague_triggers_flagged():
    warnings = lint_kill_triggers([
        "Competition intensifies in the optical module market",
        "Sentiment deteriorates",
    ])
    assert len(warnings) == 2
    assert "vibe phrase" in warnings[0]


def test_numberless_trigger_flagged():
    warnings = lint_kill_triggers(["Gross margin compresses materially"])
    assert len(warnings) == 1
    assert "no number/date" in warnings[0]


def test_dated_signpost_triggers_pass():
    warnings = lint_kill_triggers([
        "GM <40% for 2 consecutive quarters",
        "FAA certification decision slips past 2027-Q2",
        "NRR below 110% on two consecutive prints",
        "Capacity financing >$500M fails to close by year-end",
    ])
    assert warnings == []


def test_templates_cover_every_archetype():
    for arch in ALL_ARCHETYPES:
        assert arch in ARCHETYPE_KILL_TEMPLATES, arch
        assert arch in ARCHETYPE_KILL_GUIDANCE, arch
        assert "Signpost" in ARCHETYPE_KILL_TEMPLATES[arch]


def test_empty_triggers_no_warnings():
    assert lint_kill_triggers(None) == []
    assert lint_kill_triggers([]) == []


# ── L7: hypothesis intake loader ────────────────────────────────────────────────

def test_hypothesis_loader_roundtrip(tmp_path, monkeypatch):
    import run_thesis
    monkeypatch.setattr(run_thesis, "REPO_ROOT", tmp_path)
    hyp_dir = tmp_path / "data" / "hypotheses"
    hyp_dir.mkdir(parents=True)
    (hyp_dir / "LITE.md").write_text("# Hypothesis: optics is the next bottleneck")
    assert "next bottleneck" in run_thesis._load_hypothesis("lite")
    assert run_thesis._load_hypothesis("PLTR") is None


def test_hypothesis_template_exists_and_demands_falsifiability():
    template = (Path(__file__).resolve().parent.parent / "data" / "hypotheses" / "TEMPLATE.md").read_text()
    assert "Kill conditions" in template
    assert "S1" in template and "S6" in template
    assert "falsif" in template.lower() or "FALSIFY" in template
