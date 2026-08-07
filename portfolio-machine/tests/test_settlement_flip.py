"""THE regression: two-phase verdicts (law 2), encoded from the two real
incidents — INTC $91.63 provisional -> $92.52 settled, and MU $899.85
provisional -> $900.20 settled. Two verdict flips in two days.

A snapshot evaluation must NEVER: open a consult, change wire status, or
append wire history — no matter what the number says. Only the settled row
adjudicates. Also pinned here (2026-07-28 review fixes):
- law 3: a CONFLICTED LATEST print blocks adjudication (no sliding back to a
  stale clean date) — blocked_on_conflict is a live, tested path;
- law 2 at the data layer: a same-day row is demoted at the append_rows choke
  point, and even a row that reached the CSV settled is refused until its
  session date is strictly past (defense in depth);
- the machine never rewrites config/tripwires.yaml (state lives in
  data/wire_state.yaml).

Runs on `flip_machine` — test-owned wires, immortal against seed edits.
"""
import csv
from datetime import date

from engine.fetch import CSV_COLUMNS, PriceRow, append_rows, load_rows
from engine.market_calendar import exchange_today
from engine.rules import adjudicate, effective_status, load_tripwires, load_wire_state


def _snapshot(ticker, close):
    return PriceRow(ticker=ticker, date=date.today().isoformat(), close=close,
                    settled=False, source="test-snapshot")


def _settled(ticker, d, close, conflict=False):
    return PriceRow(ticker=ticker, date=d, close=close, settled=True,
                    source="test-settled", conflict=conflict)


def _wire_status(machine, wire_id):
    wire = next(w for w in load_tripwires(machine)["tripwires"]
                if w["id"] == wire_id)
    return effective_status(wire, load_wire_state(machine))


def _wire_history(machine, wire_id):
    return (load_wire_state(machine).get(wire_id) or {}).get("history") or []


def test_intc_provisional_no_fire_settled_fires(flip_machine):
    """INTC wire >= 92.00: the $91.63 same-day close says nothing; the
    settled $92.52 print is what fires."""
    verdicts = adjudicate("snapshot", root=flip_machine,
                          snapshot_rows={"INTC": _snapshot("INTC", 91.63)})
    v = next(x for x in verdicts if x.wire_id == "intc-92-flip-example")
    assert v.provisional is True and v.fired is False
    assert not list((flip_machine / "consults").glob("OPEN_*")), "snapshot opened a consult"
    assert _wire_status(flip_machine, "intc-92-flip-example") == "armed"

    # Next morning: the settled row lands at 92.52 — NOW it adjudicates.
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    verdicts = adjudicate("settled", root=flip_machine)
    v = next(x for x in verdicts if x.wire_id == "intc-92-flip-example")
    assert v.provisional is False and v.fired is True
    tickets = list((flip_machine / "consults").glob("OPEN_intc-92-flip-example_*.md"))
    assert len(tickets) == 1, "settled fire must open exactly one consult"
    assert _wire_status(flip_machine, "intc-92-flip-example") == "fired"
    hist = _wire_history(flip_machine, "intc-92-flip-example")
    assert hist and hist[-1]["event"] == "fired"
    body = tickets[0].read_text()
    assert "92.52" in body and "law 1" in body  # evidence + constitutional note


def test_mu_provisional_above_wire_still_may_not_act(flip_machine):
    """MU wire >= 900: the FLIP direction — provisional 899.85 (no), settled
    900.20 (yes). And the harder assertion: even a provisional print ABOVE
    the wire may not act, because provisional is never actionable."""
    verdicts = adjudicate("snapshot", root=flip_machine,
                          snapshot_rows={"MU": _snapshot("MU", 900.55)})
    v = next(x for x in verdicts if x.wire_id == "mu-900-flip-example")
    assert v.provisional is True and v.fired is True  # it MAY say "would fire"
    assert not list((flip_machine / "consults").glob("OPEN_mu*")), \
        "PROVISIONAL verdict acted — law 2 violation"
    assert _wire_status(flip_machine, "mu-900-flip-example") == "armed"
    assert _wire_history(flip_machine, "mu-900-flip-example") == []

    append_rows("MU", [_settled("MU", "2026-07-27", 900.20)], flip_machine)
    verdicts = adjudicate("settled", root=flip_machine)
    v = next(x for x in verdicts if x.wire_id == "mu-900-flip-example")
    assert v.fired is True
    assert len(list((flip_machine / "consults").glob("OPEN_mu-900-flip-example_*.md"))) == 1


def test_conflicted_latest_blocks_never_slides_back(flip_machine):
    """Law 3, non-degenerate (review fix): a CLEAN older in-the-money row plus
    a CONFLICTED latest row. The old code silently adjudicated (and fired!) on
    the stale clean date; now the disputed latest print BLOCKS the wire."""
    append_rows("INTC", [_settled("INTC", "2026-07-24", 93.10)], flip_machine)
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52, conflict=True)],
                flip_machine)
    verdicts = adjudicate("settled", root=flip_machine)
    v = next(x for x in verdicts if x.wire_id == "intc-92-flip-example")
    assert v.fired is None
    assert "conflict" in v.reason.lower()
    assert v.row_date == "2026-07-27", "must surface the DISPUTED date, not slide back"
    assert not list((flip_machine / "consults").glob("OPEN_intc*"))
    assert _wire_status(flip_machine, "intc-92-flip-example") == "armed"


def test_same_day_settled_row_demoted_at_choke_point(flip_machine):
    """Law 2 at the data layer (review fix): a row CLAIMING settled but dated
    the ticker's exchange-local today is demoted to snapshot by append_rows —
    whatever the fetcher said — so it can never adjudicate."""
    ex_today = exchange_today("INTC", flip_machine).isoformat()
    append_rows("INTC", [_settled("INTC", ex_today, 95.00)], flip_machine)
    stored = load_rows("INTC", flip_machine)
    assert stored and all(not r.settled for r in stored)
    assert "demoted:same-day" in stored[-1].note

    verdicts = adjudicate("settled", root=flip_machine)
    v = next(x for x in verdicts if x.wire_id == "intc-92-flip-example")
    assert v.fired is None and "no usable price row" in v.reason
    assert not list((flip_machine / "consults").glob("OPEN_intc*"))


def test_same_day_settled_in_csv_still_refused(flip_machine):
    """Law 2 defense in depth: even a row that REACHED the CSV settled (choke
    point bypassed — hand edit, old data, bug) is refused by adjudicate until
    its session date is strictly before the exchange-local today."""
    ex_today = exchange_today("INTC", flip_machine).isoformat()
    p = flip_machine / "data" / "prices" / "INTC.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerow({"date": ex_today, "close": "95.00", "settled": "True",
                    "source": "hand-edit", "fetched_at": "2026-07-28T00:00:00+00:00",
                    "conflict": "False", "note": ""})
    verdicts = adjudicate("settled", root=flip_machine)
    v = next(x for x in verdicts if x.wire_id == "intc-92-flip-example")
    assert v.fired is None
    assert "not yet next-day settled" in v.reason
    assert not list((flip_machine / "consults").glob("OPEN_intc*"))
    assert _wire_status(flip_machine, "intc-92-flip-example") == "armed"


def test_settled_refire_is_idempotent(flip_machine):
    """Running the pass twice on the same settled print must not duplicate
    consults or history (fired wires are no longer armed)."""
    append_rows("MU", [_settled("MU", "2026-07-27", 900.20)], flip_machine)
    adjudicate("settled", root=flip_machine)
    adjudicate("settled", root=flip_machine)  # second run — wire already fired
    assert len(list((flip_machine / "consults").glob("OPEN_mu-900-flip-example_*.md"))) == 1
    assert len(_wire_history(flip_machine, "mu-900-flip-example")) == 1


def test_fire_never_rewrites_the_human_config(flip_machine):
    """Review fix pin: the operator's tripwires.yaml is byte-identical after a
    fire — machine state goes to data/wire_state.yaml only."""
    cfg = flip_machine / "config" / "tripwires.yaml"
    before = cfg.read_bytes()
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    adjudicate("settled", root=flip_machine)
    assert cfg.read_bytes() == before
    assert (flip_machine / "data" / "wire_state.yaml").exists()
    assert _wire_status(flip_machine, "intc-92-flip-example") == "fired"


def test_repo_seed_flip_wires_ship_retired(machine):
    """The real config's flip examples must never fire on a first live run
    (they were armed and already in-the-money — review finding)."""
    for wid in ("intc-92-flip-example", "mu-900-flip-example"):
        assert _wire_status(machine, wid) == "retired"
    verdicts = adjudicate("settled", root=machine)
    assert all(v.wire_id == "sndk-1325-consult" for v in verdicts)
