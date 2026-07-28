"""Law 1 as a test: the machine never trades — no broker surface anywhere in
engine/ or passes/. Crude by design: a tripwire, not a proof. Plus law 5's
calendar honesty and the valuation gap-declaration rule."""
import re
from datetime import date
from pathlib import Path

from engine.market_calendar import is_trading_day
from engine.valuation import value_book

PKG = Path(__file__).resolve().parent.parent
FORBIDDEN = re.compile(
    r"(place_order|submit_order|create_order|alpaca|ibkr|ib_insync|ccxt|"
    r"tradier|binance|paper_trad|brokerage)", re.IGNORECASE)


def test_no_broker_surface_in_code():
    offenders = []
    for folder in ("engine", "passes"):
        for py in (PKG / folder).rglob("*.py"):
            for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line):
                    offenders.append(f"{py.name}:{i}: {line.strip()[:80]}")
    assert not offenders, f"law 1 violation — broker surface found: {offenders}"


def test_calendar_returns_unknown_not_a_guess(machine):
    # A weekday in a year the calendar doesn't cover -> None, never True/False.
    assert is_trading_day(date(2031, 3, 12), root=machine) is None
    # Weekend is universally False even for unknown years.
    assert is_trading_day(date(2031, 3, 15), root=machine) is False
    # A listed 2026 holiday is False; a plain 2026 weekday is True.
    assert is_trading_day(date(2026, 12, 25), root=machine) is False
    assert is_trading_day(date(2026, 7, 28), root=machine) is True


def test_valuation_declares_gaps_never_guesses(machine):
    """No price rows on file -> every seat is a declared gap and the total is
    flagged incomplete (never a silently wrong number)."""
    book = value_book(machine)
    assert book["totals"]["incomplete"] is True
    assert len(book["gaps"]) >= 4     # all seeded seats lack settled rows
    assert book["seats"] == []
