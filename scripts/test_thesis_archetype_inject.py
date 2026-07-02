"""Regression: the [ARCHETYPE_OVERRIDE] placeholder must be filled in the thesis
prompt (the bug that valued regime-shift names like mature companies).

Run: pytest scripts/test_thesis_archetype_inject.py -v
"""

import run_thesis as rt


def test_transformational_block_has_regime_guidance():
    b = rt._archetype_override_block("transformational")
    assert "transformational" in b
    assert "regime-shift comparables" in b and "NVDA peak" in b
    assert "carve-out ceiling" in b           # the +25% ceiling is disabled
    assert "tactical rigor" in b.lower()       # still demands rigor on inputs


def test_none_archetype_is_empty():
    assert rt._archetype_override_block(None) == ""
    assert rt._archetype_override_block("") == ""


def test_other_archetype_generic_block():
    b = rt._archetype_override_block("cyclical")
    assert "cyclical" in b and "ARCHETYPE OVERRIDE" in b


def test_placeholder_is_actually_replaced():
    body = "STEP4\n[ARCHETYPE_OVERRIDE]\nYOUR FRAMEWORK"
    # transformational -> filled, no literal placeholder remains
    filled = rt.fill_placeholders(body, archetype_override=rt._archetype_override_block("transformational"))
    assert "[ARCHETYPE_OVERRIDE]" not in filled
    assert "regime-shift comparables" in filled
    # None -> placeholder removed cleanly, no stray block text
    empty = rt.fill_placeholders(body, archetype_override=rt._archetype_override_block(None))
    assert "[ARCHETYPE_OVERRIDE]" not in empty
    assert "ARCHETYPE OVERRIDE" not in empty
