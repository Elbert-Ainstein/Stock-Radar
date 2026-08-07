"""Watchman/messenger refinements (operator: "isn't necessarily 100% refined").

Three gaps, three fixes, pinned here:
  1. A fired consult was invisible forever after — nothing tracked whether the
     question was ever answered. For a system whose ONLY action is asking, an
     unanswered question is the failure that makes it decorative.
  2. A wire fired once and went silent — cross $1,325, trim, and nothing ever
     watched $1,500 again.
  3. Dated kill signposts (certification decisions, appropriations) had no home
     at all: the date passed silently and the thesis kept its conviction.
"""
from datetime import date, timedelta

import yaml

from engine import log as logmod
from engine.consult_state import OVERDUE_DAYS, scan_consults, summarize
from engine.fetch import PriceRow, append_rows
from engine.rules import (adjudicate, adjudicate_signposts, effective_condition,
                          effective_status, load_wire_state)


def _settled(ticker, d, close):
    return PriceRow(ticker=ticker, date=d, close=close, settled=True, source="test")


def _write_wires(machine, wires):
    (machine / "config" / "tripwires.yaml").write_text(
        yaml.safe_dump({"tripwires": wires}, sort_keys=False), encoding="utf-8")


# ── 1 · consult lifecycle ────────────────────────────────────────────────────

def test_open_consult_is_counted_and_aged(flip_machine):
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    adjudicate("settled", root=flip_machine)

    s = summarize(flip_machine)
    assert s["open"] == 1 and s["signed"] == 0
    assert s["oldest_days"] == 0            # opened today
    assert s["records"][0]["status"] == "OPEN"


def test_signed_door_closes_the_question(flip_machine):
    """Answered is read from the DOCUMENT — filling the signature line or
    ticking a door both count, because both are how a human actually answers."""
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    adjudicate("settled", root=flip_machine)
    ticket = next((flip_machine / "consults").glob("OPEN_*.md"))

    body = ticket.read_text(encoding="utf-8").replace(
        "- Signed door: _(operator fills in)_", "- Signed door: TRIM the agreed slice")
    ticket.write_text(body, encoding="utf-8")

    s = summarize(flip_machine)
    assert s["open"] == 0 and s["signed"] == 1
    assert s["records"][0]["signed_door"].startswith("TRIM")


def test_ticked_door_also_counts_as_answered(flip_machine):
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    adjudicate("settled", root=flip_machine)
    ticket = next((flip_machine / "consults").glob("OPEN_*.md"))
    body = ticket.read_text(encoding="utf-8").replace("- [ ] ", "- [x] ", 1)
    ticket.write_text(body, encoding="utf-8")
    assert summarize(flip_machine)["open"] == 0


def test_stale_consult_goes_overdue(flip_machine):
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    adjudicate("settled", root=flip_machine)
    later = date.today() + timedelta(days=OVERDUE_DAYS + 1)

    s = summarize(flip_machine, today=later)
    assert s["open"] == 1
    assert s["oldest_days"] >= OVERDUE_DAYS
    assert s["overdue"], "an aged, unanswered question must be marked OVERDUE"


def test_open_questions_reach_the_brief(flip_machine):
    from passes import premarket
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    premarket.run(offline=True, root=flip_machine)
    text = (flip_machine / "out" / "premarket.html").read_text(encoding="utf-8")
    assert "Open questions" in text
    assert "awaiting your signature" in text


def test_overdue_never_escalates_into_action(flip_machine):
    """Law 1 is not softened by impatience: an ignored question produces a
    louder line on a page, never a decision."""
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    adjudicate("settled", root=flip_machine)
    before = sorted(p.name for p in (flip_machine / "consults").glob("*"))
    summarize(flip_machine, today=date.today() + timedelta(days=90))
    assert sorted(p.name for p in (flip_machine / "consults").glob("*")) == before


# ── 2 · ladders ──────────────────────────────────────────────────────────────

def test_ladder_rearms_at_the_next_declared_rung(machine):
    _write_wires(machine, [{
        "id": "sndk-ladder", "ticker": "SNDK",
        "condition": {"op": "gte", "level": 1325.00, "basis": "settled_close"},
        "ladder": [1500.00, 1800.00],
        "action": "consult", "status": "armed", "note": "test ladder",
    }])
    append_rows("SNDK", [_settled("SNDK", "2026-07-24", 1330.00)], machine)
    v = adjudicate("settled", root=machine)
    assert v[0].fired is True

    state = load_wire_state(machine)
    wire = {"id": "sndk-ladder", "ladder": [1500.00, 1800.00],
            "condition": {"op": "gte", "level": 1325.00}}
    assert effective_status(wire, state) == "armed", "ladder wire must re-arm"
    assert effective_condition(wire, state)["level"] == 1500.00

    # 1400 does not clear the NEW rung. (Dates stay strictly in the past —
    # a row dated today is refused by law 2, as it should be.)
    append_rows("SNDK", [_settled("SNDK", "2026-07-25", 1400.00)], machine)
    v = adjudicate("settled", root=machine)
    assert v[0].fired is False
    assert len(list((machine / "consults").glob("OPEN_sndk-ladder*"))) == 1

    # 1550 clears rung 2 -> re-arm at 1800.
    append_rows("SNDK", [_settled("SNDK", "2026-07-27", 1550.00)], machine)
    adjudicate("settled", root=machine)
    state = load_wire_state(machine)
    assert effective_condition(wire, state)["level"] == 1800.00
    assert len(list((machine / "consults").glob("OPEN_sndk-ladder*"))) == 2


def test_exhausted_ladder_retires_the_wire(machine):
    _write_wires(machine, [{
        "id": "one-rung", "ticker": "SNDK",
        "condition": {"op": "gte", "level": 100.0, "basis": "settled_close"},
        "ladder": [200.0],
        "action": "consult", "status": "armed", "note": "t",
    }])
    append_rows("SNDK", [_settled("SNDK", "2026-07-24", 150.0)], machine)
    adjudicate("settled", root=machine)
    append_rows("SNDK", [_settled("SNDK", "2026-07-25", 250.0)], machine)
    adjudicate("settled", root=machine)
    state = load_wire_state(machine)
    assert effective_status({"id": "one-rung"}, state) == "fired"


def test_wire_without_a_ladder_is_unchanged(flip_machine):
    """The old behavior is the default: no ladder declared, fires once."""
    append_rows("INTC", [_settled("INTC", "2026-07-27", 92.52)], flip_machine)
    adjudicate("settled", root=flip_machine)
    state = load_wire_state(flip_machine)
    assert effective_status({"id": "intc-92-flip-example"}, state) == "fired"


def test_machine_never_invents_a_rung(machine):
    """The ladder is the operator's, written in advance — the machine may not
    extrapolate one."""
    _write_wires(machine, [{
        "id": "no-ladder", "ticker": "SNDK",
        "condition": {"op": "gte", "level": 100.0}, "action": "consult",
        "status": "armed", "note": "t",
    }])
    append_rows("SNDK", [_settled("SNDK", "2026-07-24", 500.0)], machine)
    adjudicate("settled", root=machine)
    state = load_wire_state(machine)
    assert "rung" not in (state.get("no-ladder") or {})


# ── 3 · dated signposts ──────────────────────────────────────────────────────

def _signpost_wire(due, wid="achr-cert", ticker="ACHR"):
    return {"id": wid, "ticker": ticker,
            "condition": {"type": "signpost", "due": due},
            "action": "consult", "status": "armed",
            "note": "FAA type certification decision expected"}


def test_future_signpost_is_silent(machine):
    _write_wires(machine, [_signpost_wire("2099-01-01")])
    assert adjudicate_signposts(machine) == []
    assert not list((machine / "consults").glob("*"))


def test_due_signpost_asks_the_operator(machine):
    """The machine cannot observe a certification decision. On the due date it
    does the only honest thing: it asks, quoting what the thesis claimed."""
    _write_wires(machine, [_signpost_wire("2026-07-01")])
    fired = adjudicate_signposts(machine, today=date(2026, 7, 28))
    assert len(fired) == 1 and fired[0]["wire"] == "achr-cert"

    ticket = next((machine / "consults").glob("*achr-cert*"))
    body = ticket.read_text(encoding="utf-8")
    assert "SIGNPOST DUE 2026-07-01" in body
    assert "cannot observe" in body
    assert "CONFIRMED" in body and "NOT_YET" in body and "OBSOLETE" in body
    assert "law 1" in body


def test_signpost_fires_once(machine):
    _write_wires(machine, [_signpost_wire("2026-07-01")])
    adjudicate_signposts(machine, today=date(2026, 7, 28))
    assert adjudicate_signposts(machine, today=date(2026, 7, 29)) == []
    assert len(list((machine / "consults").glob("*achr-cert*"))) == 1


def test_signpost_is_never_price_adjudicated(machine):
    """A signpost has no price semantics — adjudicate() must skip it entirely
    rather than treat a missing level as a malformed price wire."""
    _write_wires(machine, [_signpost_wire("2026-07-01")])
    append_rows("ACHR", [_settled("ACHR", "2026-07-27", 12.0)], machine)
    verdicts = adjudicate("settled", root=machine)
    assert verdicts == []
    assert not list((machine / "consults").glob("*"))


def test_undated_signpost_is_logged_not_fired(machine):
    """A signpost without a date is a wish, not a signpost (lesson L5)."""
    w = _signpost_wire(None)
    w["condition"] = {"type": "signpost"}
    _write_wires(machine, [w])
    assert adjudicate_signposts(machine, today=date(2026, 7, 28)) == []
    events = [r["event"] for r in logmod.read(machine)]
    assert "signpost_malformed" in events
    assert not list((machine / "consults").glob("*"))


def test_signpost_reaches_the_premarket_brief(machine):
    from passes import premarket
    _write_wires(machine, [_signpost_wire("2026-07-01")])
    premarket.run(offline=True, root=machine)
    text = (machine / "out" / "premarket.html").read_text(encoding="utf-8")
    assert "Signposts due" in text and "achr-cert" in text
