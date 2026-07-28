"""THE regression: two-phase verdicts (law 2), encoded from the two real
incidents — INTC $91.63 provisional -> $92.52 settled, and MU $899.85
provisional -> $900.20 settled. Two verdict flips in two days.

A snapshot evaluation must NEVER: open a consult, change wire status, or
append wire history — no matter what the number says. Only the settled row
adjudicates. Also encodes law 3: a conflict-flagged settled row cannot
adjudicate at all.
"""
from datetime import date

import yaml

from engine.fetch import PriceRow, append_rows
from engine.rules import adjudicate, load_tripwires
from engine import log as logmod


def _snapshot(ticker, close):
    return PriceRow(ticker=ticker, date=date.today().isoformat(), close=close,
                    settled=False, source="test-snapshot")


def _settled(ticker, d, close, conflict=False):
    return PriceRow(ticker=ticker, date=d, close=close, settled=True,
                    source="test-settled", conflict=conflict)


def _wire_status(machine, wire_id):
    data = load_tripwires(machine)
    return next(w for w in data["tripwires"] if w["id"] == wire_id)


def test_intc_provisional_no_fire_settled_fires(machine):
    """INTC wire >= 92.00: the $91.63 same-day close says nothing; the
    settled $92.52 print is what fires."""
    # Evening: provisional close BELOW the wire — and even if it were above,
    # snapshot mode may not act (asserted in the MU test below).
    verdicts = adjudicate("snapshot", root=machine,
                          snapshot_rows={"INTC": _snapshot("INTC", 91.63)})
    v = next(x for x in verdicts if x.wire_id == "intc-92-flip-example")
    assert v.provisional is True and v.fired is False
    assert not list((machine / "consults").glob("OPEN_*")), "snapshot opened a consult"
    assert _wire_status(machine, "intc-92-flip-example")["status"] == "armed"

    # Next morning: the settled row lands at 92.52 — NOW it adjudicates.
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], machine)
    verdicts = adjudicate("settled", root=machine)
    v = next(x for x in verdicts if x.wire_id == "intc-92-flip-example")
    assert v.provisional is False and v.fired is True
    tickets = list((machine / "consults").glob("OPEN_intc-92-flip-example_*.md"))
    assert len(tickets) == 1, "settled fire must open exactly one consult"
    wire = _wire_status(machine, "intc-92-flip-example")
    assert wire["status"] == "fired"
    assert wire["history"] and wire["history"][-1]["event"] == "fired"
    body = tickets[0].read_text()
    assert "92.52" in body and "law 1" in body  # evidence + constitutional note


def test_mu_provisional_above_wire_still_may_not_act(machine):
    """MU wire >= 900: the FLIP direction — provisional 899.85 (no), settled
    900.20 (yes). And the harder assertion: even a provisional print ABOVE
    the wire may not act, because provisional is never actionable."""
    verdicts = adjudicate("snapshot", root=machine,
                          snapshot_rows={"MU": _snapshot("MU", 900.55)})
    v = next(x for x in verdicts if x.wire_id == "mu-900-flip-example")
    assert v.provisional is True and v.fired is True  # it MAY say "would fire"
    assert not list((machine / "consults").glob("OPEN_mu*")), \
        "PROVISIONAL verdict acted — law 2 violation"
    assert _wire_status(machine, "mu-900-flip-example")["status"] == "armed"
    assert _wire_status(machine, "mu-900-flip-example")["history"] == []

    append_rows("MU", [_settled("MU", "2026-07-27", 900.20)], machine)
    verdicts = adjudicate("settled", root=machine)
    v = next(x for x in verdicts if x.wire_id == "mu-900-flip-example")
    assert v.fired is True
    assert len(list((machine / "consults").glob("OPEN_mu-900-flip-example_*.md"))) == 1


def test_conflict_flagged_row_cannot_adjudicate(machine):
    """Law 3: a settled row whose sources disagreed is flagged and blocked —
    the wire stays armed and the verdict says why."""
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52, conflict=True)], machine)
    verdicts = adjudicate("settled", root=machine)
    v = next(x for x in verdicts if x.wire_id == "intc-92-flip-example")
    assert v.fired is None
    assert "no usable price row" in v.reason or "conflict" in v.reason.lower()
    assert not list((machine / "consults").glob("OPEN_intc*"))
    assert _wire_status(machine, "intc-92-flip-example")["status"] == "armed"


def test_settled_refire_is_idempotent(machine):
    """Running the pass twice on the same settled print must not duplicate
    consults or history (fired wires are no longer armed)."""
    append_rows("MU", [_settled("MU", "2026-07-27", 900.20)], machine)
    adjudicate("settled", root=machine)
    adjudicate("settled", root=machine)  # second run — wire already fired
    assert len(list((machine / "consults").glob("OPEN_mu-900-flip-example_*.md"))) == 1
    wire = _wire_status(machine, "mu-900-flip-example")
    assert len(wire["history"]) == 1
