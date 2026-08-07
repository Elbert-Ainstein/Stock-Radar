"""Imported research evidence — the supremacy clause in code.

Evidence informs the doors; it never fires, sizes, or decides. It is always
dated, and undated/aged research is rendered STALE rather than trusted."""
from engine.consults import write_consult
from engine.evidence import (evidence_dir, evidence_markdown, load_evidence,
                             type_a_defense_note)
from engine.fetch import PriceRow, append_rows
from engine.rules import Verdict, adjudicate

FRESH = """---
source: stock-radar thesis v3.4.4
as_of: {today}
strategic_conviction: HIGH
risk_adj_target: 142.5
---

# LITE — thesis of record

## Kill signposts
- certification decision slips past 2027-Q2
"""


def _write(machine, ticker, text):
    evidence_dir(machine).mkdir(parents=True, exist_ok=True)
    (evidence_dir(machine) / f"{ticker}.md").write_text(text, encoding="utf-8")


def test_no_evidence_is_none_not_an_error(machine):
    assert load_evidence("LITE", machine) is None
    assert evidence_markdown(None) == ""


def test_fresh_evidence_parses_and_is_not_stale(machine):
    from datetime import date
    _write(machine, "LITE", FRESH.format(today=date.today().isoformat()))
    ev = load_evidence("LITE", machine)
    assert ev["meta"]["strategic_conviction"] == "HIGH"
    assert ev["stale"] is False and ev["age_days"] == 0
    md = evidence_markdown(ev)
    assert "NOT a verdict" in md and "STALE" not in md


def test_old_research_is_marked_stale(machine):
    _write(machine, "LITE", FRESH.format(today="2020-01-01"))
    ev = load_evidence("LITE", machine)
    assert ev["stale"] is True
    assert "STALE" in evidence_markdown(ev)


def test_undated_research_is_stale_and_warned(machine):
    _write(machine, "LITE", "---\nsource: somewhere\n---\n\nbody")
    ev = load_evidence("LITE", machine)
    assert ev["stale"] is True
    assert any("undated" in w for w in ev["warnings"])


def test_malformed_frontmatter_degrades_loudly(machine):
    _write(machine, "LITE", "---\n[unclosed\n---\n\nbody")
    ev = load_evidence("LITE", machine)
    assert ev["meta"] == {} and ev["warnings"]
    assert "⚠" in evidence_markdown(ev)


def test_type_a_note_only_for_live_structural_conviction():
    assert "Type A" in type_a_defense_note({"meta": {"strategic_conviction": "HIGH"}})
    assert type_a_defense_note({"meta": {"strategic_conviction": "BROKEN"}}) == ""
    assert type_a_defense_note({"meta": {}}) == ""
    assert type_a_defense_note(None) == ""


def test_consult_attaches_evidence_beneath_the_facts(flip_machine):
    """A fired wire's ticket carries the research as dated evidence, and the
    settled facts still come first."""
    from datetime import date
    _write(flip_machine, "INTC", FRESH.format(today=date.today().isoformat()))
    append_rows("INTC", [PriceRow(ticker="INTC", date="2026-07-27", close=92.52,
                                  settled=True, source="test")], flip_machine)
    adjudicate("settled", root=flip_machine)
    ticket = next(iter((flip_machine / "consults").glob("OPEN_intc-92*.md")))
    body = ticket.read_text(encoding="utf-8")
    assert body.index("Evidence (provenance") < body.index("Imported research")
    assert "certification decision slips past 2027-Q2" in body
    assert "Type A note" in body and "must cite that thesis" in body
    assert "Supremacy clause" in body


def test_premarket_brief_surfaces_stale_research(flip_machine):
    """Aging research is visible daily — before a wire fires on top of it."""
    from passes import premarket
    _write(flip_machine, "INTC", FRESH.format(today="2020-01-01"))
    assert premarket.run(offline=True, root=flip_machine) == 0
    text = (flip_machine / "out" / "premarket.html").read_text(encoding="utf-8")
    assert "Imported research" in text and "STALE" in text and "2020-01-01" in text
    from engine import log as logmod
    assert "evidence_stale" in [r["event"] for r in logmod.read(flip_machine)]


def test_close_brief_omits_the_research_section(flip_machine):
    """The close pass doesn't read evidence — the brief must not imply it did
    (absent key => section omitted, same rule as the monitors)."""
    from passes import close as closepass
    _write(flip_machine, "INTC", FRESH.format(today="2020-01-01"))
    closepass.run(offline=True, root=flip_machine)
    text = (flip_machine / "out" / "close.html").read_text(encoding="utf-8")
    assert "Imported research" not in text


def test_consult_without_evidence_is_unchanged(flip_machine):
    append_rows("INTC", [PriceRow(ticker="INTC", date="2026-07-27", close=92.52,
                                  settled=True, source="test")], flip_machine)
    adjudicate("settled", root=flip_machine)
    body = next(iter((flip_machine / "consults").glob("OPEN_intc-92*.md"))).read_text()
    assert "Imported research" not in body and "law 1" in body
