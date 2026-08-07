"""THE other regression: the off-by-one grade-formula bug — plus the v1.2.1
methodology (CONSTITUTION §III): seven factors, 0-100 scores, letter bands,
and the moat-answer-required-for-A rule. Scores are keyed by NAME; any
misalignment is an error, never a silent shift."""
import pytest

from engine.grades import composite, grade_sheet, letter

FACTORS = {"moat_durability": 0.25, "growth": 0.20, "valuation": 0.15,
           "profitability": 0.15, "evidence_revisions": 0.10,
           "momentum_risk": 0.10, "cycle_risk": 0.05}
SCORES = {"moat_durability": 80, "growth": 70, "valuation": 60,
          "profitability": 75, "evidence_revisions": 65,
          "momentum_risk": 55, "cycle_risk": 70}


def test_composite_hand_computed():
    # .25*80 + .20*70 + .15*60 + .15*75 + .10*65 + .10*55 + .05*70
    # = 20 + 14 + 9 + 11.25 + 6.5 + 5.5 + 3.5 = 69.75
    assert composite(SCORES, FACTORS) == 69.75


def test_letter_bands_exact_edges():
    assert letter(91.5) == "A"
    assert letter(91.49) == "A-"
    assert letter(88.5) == "A-"
    assert letter(85.5) == "B+"
    assert letter(81.5) == "B"
    assert letter(78.5) == "B-"
    assert letter(75.5) == "C+"
    assert letter(71.5) == "C"
    assert letter(71.49) == "D"
    assert letter(69.75) == "D"


def test_reordering_cannot_shift_anything():
    """The exact spreadsheet failure: same data, different row order. Keyed
    math must be order-blind; the old positional math was not."""
    reordered_scores = dict(reversed(list(SCORES.items())))
    reordered_factors = dict(reversed(list(FACTORS.items())))
    assert composite(reordered_scores, FACTORS) == 69.75
    assert composite(SCORES, reordered_factors) == 69.75

    # Demonstrate the bug the keyed design kills: positional zip on the
    # reordered dict gives a DIFFERENT (wrong) number.
    positional_wrong = round(
        sum(w * s for w, s in zip(FACTORS.values(), reordered_scores.values())), 2)
    assert positional_wrong != 69.75, "if equal, the fixture is degenerate"


def test_misalignment_is_an_error_never_a_shift():
    with pytest.raises(ValueError, match="mismatch"):
        composite({**SCORES, "vibes": 90}, FACTORS)          # unknown factor
    short = dict(SCORES)
    short.pop("cycle_risk")
    with pytest.raises(ValueError, match="missing"):
        composite(short, FACTORS)                            # missing factor
    with pytest.raises(ValueError):
        composite(SCORES, {})                                # no methodology
    with pytest.raises(ValueError, match="out of range"):
        composite({**SCORES, "growth": 130}, FACTORS)        # not 0-100
    with pytest.raises(ValueError, match="sum to 1.00"):
        composite(SCORES, {**FACTORS, "moat_durability": 0.50})  # broken weights


def test_a_grade_requires_moat_answer(machine):
    """§III: every A/A- requires the written one-line moat answer. A SEED
    placeholder does not count."""
    import yaml
    p = machine / "config" / "grades.yaml"
    data = yaml.safe_load(p.read_text())
    # Push MU into A territory but leave its SEED_REPLACE moat answer.
    data["seats"]["MU"]["scores"] = {k: 95 for k in FACTORS}
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    sheet = grade_sheet(machine)
    assert sheet["seats"]["MU"]["letter"] == "A"
    assert any("MU" in v and "moat answer" in v for v in sheet["violations"])


def test_track_z_seat_rejected_from_c_rubric(machine):
    """§I.7: grading a Z on the C rubric kills it falsely — the sheet must
    refuse and say so, not compute a meaningless number."""
    import yaml
    p = machine / "config" / "grades.yaml"
    data = yaml.safe_load(p.read_text())
    data["seats"]["ZSEAT"] = {"track": "Z",
                              "scores": {k: 50 for k in FACTORS}}
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    sheet = grade_sheet(machine)
    assert "ZSEAT" not in sheet["seats"]
    assert any("ZSEAT" in v and "fingerprints" in v for v in sheet["violations"])


def test_grade_sheet_runs_on_seed_config(machine):
    sheet = grade_sheet(machine)
    assert sheet["version"] == "1.2.1"
    assert set(sheet["seats"]) == {"INTC", "MU", "SNDK", "0981.HK"}
    for seat in sheet["seats"].values():
        assert 0 <= seat["composite"] <= 100
        assert seat["letter"] in ("A", "A-", "B+", "B", "B-", "C+", "C", "D")
