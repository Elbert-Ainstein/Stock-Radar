"""Valuation gap declarations (laws 2 + 3): unknowns are DECLARED, never
silently valued at zero, NaN, or a stale disputed print (2026-07-28 review
fixes — None shares valued a seat at $0 with the book reporting complete)."""
import csv

import yaml

from engine.fetch import CSV_COLUMNS, PriceRow, append_rows
from engine.valuation import value_book


def _write_holdings(machine, holdings, cash=None):
    (machine / "config" / "holdings.yaml").write_text(yaml.safe_dump({
        "holdings": holdings, "cash": cash or [],
        "floor": {"amount": 40000.00, "currency": "USD", "note": "never invested"},
    }, sort_keys=False), encoding="utf-8")


def _settled(ticker, d, close, conflict=False):
    return PriceRow(ticker=ticker, date=d, close=close, settled=True,
                    source="test", conflict=conflict)


def test_none_shares_is_a_gap_not_zero(machine):
    _write_holdings(machine, [{"ticker": "INTC", "shares": None, "cost": 30.0,
                               "currency": "USD"}])
    append_rows("INTC", [_settled("INTC", "2026-07-27", 50.0)], machine)
    book = value_book(machine)
    assert book["totals"]["incomplete"] is True
    assert any("shares not set" in g["reason"] for g in book["gaps"])
    assert book["seats"] == []


def test_conflicted_latest_print_is_a_gap(machine):
    _write_holdings(machine, [{"ticker": "INTC", "shares": 10, "cost": 30.0,
                               "currency": "USD"}])
    append_rows("INTC", [_settled("INTC", "2026-07-24", 50.0)], machine)
    append_rows("INTC", [_settled("INTC", "2026-07-27", 55.0, conflict=True)], machine)
    book = value_book(machine)
    assert book["totals"]["incomplete"] is True
    assert any("CONFLICT" in g["reason"] for g in book["gaps"])
    assert book["seats"] == [], "a disputed number must not value the book"


def test_none_cash_is_a_gap(machine):
    _write_holdings(machine, [], cash=[{"currency": "USD", "amount": None}])
    book = value_book(machine)
    assert book["totals"]["incomplete"] is True
    assert any("amount not set" in g["reason"] for g in book["gaps"])


def test_nan_close_never_reaches_the_book(machine):
    """append_rows rejects non-finite closes outright; even a NaN smuggled
    into the CSV by hand is a declared gap, not a NaN total."""
    _write_holdings(machine, [{"ticker": "INTC", "shares": 10, "cost": 30.0,
                               "currency": "USD"}])
    n = append_rows("INTC", [_settled("INTC", "2026-07-27", float("nan"))], machine)
    assert n == 0, "non-finite close must be rejected at the choke point"
    p = machine / "data" / "prices" / "INTC.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerow({"date": "2026-07-27", "close": "nan", "settled": "True",
                    "source": "hand", "fetched_at": "t", "conflict": "False",
                    "note": ""})
    book = value_book(machine)
    assert book["totals"]["incomplete"] is True
    assert any("non-finite" in g["reason"] for g in book["gaps"])


def test_hkd_seat_without_fx_is_a_gap(machine):
    _write_holdings(machine, [{"ticker": "0981.HK", "shares": 500, "cost": 20.0,
                               "currency": "HKD"}])
    append_rows("0981.HK", [_settled("0981.HK", "2026-07-27", 25.0)], machine)
    book = value_book(machine)
    assert any("no settled FX" in g["reason"] for g in book["gaps"])
    assert book["totals"]["incomplete"] is True
