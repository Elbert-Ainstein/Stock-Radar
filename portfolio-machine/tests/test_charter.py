"""Charter §V regressions: the euphoria protocol (>=2x cost fires an
automatic consult, settled basis only) and the floor (reported, never
counted in the book).

Euphoria scenarios run on `euphoria_machine` (test-owned holdings, INTC cost
30 -> 2x line 60) so they survive operator SEED_REPLACE edits. The floor
tests run on the REAL config: $40,000 is a charter constant, not a seed."""
import yaml

from engine.fetch import PriceRow, append_rows
from engine.rules import euphoria_checks
from engine.valuation import value_book


def _settled(ticker, d, close, conflict=False):
    return PriceRow(ticker=ticker, date=d, close=close, settled=True,
                    source="test", conflict=conflict)


def test_euphoria_fires_at_2x_cost_settled_only(euphoria_machine):
    """Test cost for INTC is 30.00 -> the 2x line is 60.00. A settled 61
    fires an automatic consult with the trim/defend doors; a snapshot-only
    world must not (law 2 — euphoria adjudicates on settled rows)."""
    assert euphoria_checks(euphoria_machine) == []
    assert not list((euphoria_machine / "consults").glob("*euphoria*"))

    append_rows("INTC", [_settled("INTC", "2026-07-27", 61.00)], euphoria_machine)
    fired = euphoria_checks(euphoria_machine)
    assert len(fired) == 1 and fired[0]["ticker"] == "INTC"
    assert fired[0]["multiple"] >= 2.0
    tickets = list((euphoria_machine / "consults").glob("*euphoria-INTC*"))
    assert len(tickets) == 1
    body = tickets[0].read_text()
    assert "TRIM" in body and "DEFEND" in body      # the §V doors
    assert "law 1" in body                           # constitutional note


def test_euphoria_below_2x_does_not_fire(euphoria_machine):
    append_rows("INTC", [_settled("INTC", "2026-07-27", 59.99)], euphoria_machine)
    assert euphoria_checks(euphoria_machine) == []


def test_euphoria_blocked_on_conflicted_print(euphoria_machine):
    """Law 3 (review fix): a disputed latest print cannot certify a double —
    the check logs a block instead of opening a ticket."""
    append_rows("INTC", [_settled("INTC", "2026-07-27", 61.00, conflict=True)],
                euphoria_machine)
    assert euphoria_checks(euphoria_machine) == []
    assert not list((euphoria_machine / "consults").glob("*euphoria*"))
    from engine import log as logmod
    events = [r["event"] for r in logmod.read(euphoria_machine)]
    assert "euphoria_blocked_on_conflict" in events


def test_euphoria_is_idempotent_per_episode(euphoria_machine):
    append_rows("INTC", [_settled("INTC", "2026-07-27", 61.00)], euphoria_machine)
    assert len(euphoria_checks(euphoria_machine)) == 1
    append_rows("INTC", [_settled("INTC", "2026-07-28", 65.00)], euphoria_machine)
    assert euphoria_checks(euphoria_machine) == []    # episode already open
    assert len(list((euphoria_machine / "consults").glob("*euphoria-INTC*"))) == 1


def test_floor_reported_never_counted(machine):
    """§V: the $40K floor is sacred — valuation reports it and never adds it
    to book totals."""
    book = value_book(machine)
    assert book["floor"]["amount"] == 40000.00
    assert book["floor"]["counted_in_book"] is False
    # Empty price data -> book total 0 even though the floor is $40K.
    assert book["totals"]["usd"] == 0.0


def test_floor_is_config_not_code(machine):
    cfg = yaml.safe_load((machine / "config" / "holdings.yaml").read_text())
    assert cfg["floor"]["amount"] == 40000.00
    assert "never" in cfg["floor"]["note"].lower()
