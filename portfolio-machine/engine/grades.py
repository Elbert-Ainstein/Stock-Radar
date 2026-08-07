"""Composite grade math IN CODE — CONSTITUTION §III, methodology v1.2.1.

The structural fix for the off-by-one spreadsheet bug class: scores are keyed
by FACTOR NAME, never by position, so a reordered factor list cannot silently
misalign weights and scores — any mismatch is an ERROR, never a shift.

Also enforced here (machine appendix):
- letter bands (91.5/88.5/85.5/81.5/78.5/75.5/71.5, else D);
- every A/A- requires the seat's written one-line moat_answer — a violation
  is reported, loudly, per seat;
- grade CHANGES are proposals (config `proposals`), never silent re-scores —
  this module computes, it does not mutate seats.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .paths import ROOT, config_dir

SCORE_MIN, SCORE_MAX = 0.0, 100.0


def load_grades(root: Path = ROOT) -> dict:
    p = config_dir(root) / "grades.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def composite(scores: dict[str, float], factors: dict[str, float]) -> float:
    """Weighted composite keyed BY NAME (scores 0-100, weights fractions).
    Raises on any score/factor mismatch, out-of-range score, or degenerate
    weights — misalignment is an error, never a silent shift."""
    if not factors:
        raise ValueError("methodology has no factors")
    unknown = set(scores) - set(factors)
    missing = set(factors) - set(scores)
    if unknown or missing:
        raise ValueError(
            f"score/factor mismatch — unknown: {sorted(unknown)}, "
            f"missing: {sorted(missing)} (scores must cover exactly the "
            f"methodology factors; no positional alignment exists to hide behind)"
        )
    for name, s in scores.items():
        if not (SCORE_MIN <= float(s) <= SCORE_MAX):
            raise ValueError(f"score out of range 0-100: {name}={s}")
    total_w = sum(factors.values())
    if total_w <= 0:
        raise ValueError("factor weights must sum > 0")
    if abs(total_w - 1.0) > 0.001:
        raise ValueError(f"factor weights must sum to 1.00 (got {total_w}) — "
                         f"a partial rubric grades nothing")
    return round(sum(factors[n] * float(scores[n]) for n in factors), 2)


def letter(score: float, bands: dict[str, float] | None = None) -> str:
    """§III letter bands. Descending thresholds; below the last -> D."""
    default = {"A": 91.5, "A-": 88.5, "B+": 85.5, "B": 81.5,
               "B-": 78.5, "C+": 75.5, "C": 71.5}
    bands = bands or default
    for name, lo in sorted(bands.items(), key=lambda kv: -kv[1]):
        if score >= lo:
            return name
    return "D"


def grade_sheet(root: Path = ROOT) -> dict:
    """Composite + letter per Track-C seat, plus constitutional violations
    (loud, never silent): A/A- without a real moat_answer; Track-Z seats
    present in scores (wrong rubric — §I.7)."""
    data = load_grades(root)
    methodology = data.get("methodology") or {}
    factors = methodology.get("factors") or {}
    bands = methodology.get("letter_bands") or None
    out = {"version": methodology.get("version"), "seats": {}, "violations": []}
    for ticker, seat in (data.get("seats") or {}).items():
        track = seat.get("track", "C")
        if track == "Z":
            out["violations"].append(
                f"{ticker}: Track-Z seat carries C-rubric scores — grading a Z "
                f"on the C rubric kills it falsely (§I.7); use the seven "
                f"fingerprints (§IV) instead")
            continue
        comp = composite(seat.get("scores") or {}, factors)
        lt = letter(comp, bands)
        moat_answer = (seat.get("moat_answer") or "").strip()
        if lt in ("A", "A-") and (not moat_answer or moat_answer.startswith("SEED_REPLACE")):
            out["violations"].append(
                f"{ticker}: composite {comp} ({lt}) requires a written one-line "
                f"moat answer — 'if intelligence is free, what's left to pay "
                f"for?' (§III) — none on file")
        out["seats"][ticker] = {
            "composite": comp, "letter": lt, "track": track,
            "tier": seat.get("tier"),
        }
    return out
