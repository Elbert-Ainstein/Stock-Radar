"""Charter §V regressions: the euphoria protocol (>=2x cost fires an
automatic consult, settled basis only) and the floor (reported, never
counted in the book)."""
import yaml

from engine.fetch import PriceRow, append_rows
from engine.rules import euphoria_checks
from engine.valuation import value_book


def _settled(ticker, d, close):
    return PriceRow(ticker=ticker, date=d, close=close, settled=True, source="test")


def test_euphoria_fires_at_2x_cost_settled_only(machine):
    """Seed cost for INTC is 30.00 -> the 2x line is 60.00. A settled 61
    fires an automatic consult with the trim/defend doors; a snapshot-only
    61 must not (law 2 — euphoria adjudicates on settled rows)."""
    # Snapshot-only world: no settled rows on file -> nothing fires.
    assert euphoria_checks(machine) == []
    assert not list((machine / "consults").glob("*euphoria*"))

    append_rows("INTC", [_settled("INTC", "2026-07-27", 61.00)], machine)
    fired = euphoria_checks(machine)
    assert len(fired) == 1 and fired[0]["ticker"] == "INTC"
    assert fired[0]["multiple"] >= 2.0
    tickets = list((machine / "consults").glob("*euphoria-INTC*"))
    assert len(tickets) == 1
    body = tickets[0].read_text()
    assert "TRIM" in body and "DEFEND" in body      # the §V doors
    assert "law 1" in body                           # constitutional note


def test_euphoria_below_2x_does_not_fire(machine):
    append_rows("INTC", [_settled("INTC", "2026-07-27", 59.99)], machine)
    assert euphoria_checks(machine) == []


def test_euphoria_is_idempotent_per_episode(machine):
    append_rows("INTC", [_settled("INTC", "2026-07-27", 61.00)], machine)
    assert len(euphoria_checks(machine)) == 1
    append_rows("INTC", [_settled("INTC", "2026-07-28", 65.00)], machine)
    assert euphoria_checks(machine) == []            # episode already open
    assert len(list((machine / "consults").glob("*euphoria-INTC*"))) == 1


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
