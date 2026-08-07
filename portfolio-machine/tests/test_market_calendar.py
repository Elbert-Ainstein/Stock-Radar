"""Law 5 + law 2 support: exchange-local boundaries and calendar honesty.
The Korea-holiday error (an assumed session) and the UTC settlement-boundary
bug (a same-day close settling at 8 PM ET) both live here as pins."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from engine.market_calendar import (CALENDAR_TZ, calendar_for_ticker,
                                    exchange_today, is_trading_day)


def test_suffix_routing(machine):
    assert calendar_for_ticker("INTC", machine) == "XNYS"
    assert calendar_for_ticker("0981.HK", machine) == "XHKG"
    # Unknown suffix -> None, NEVER a silent default to NYSE (the Korea error).
    assert calendar_for_ticker("005930.KS", machine) is None


def test_unknown_calendar_is_honest(machine):
    # Weekday on an unknown exchange -> None (verify by hand), not a guess.
    assert is_trading_day(date(2026, 7, 28), "005930.KS", machine) is None
    # Weekend is universally False even on unknown exchanges.
    assert is_trading_day(date(2026, 7, 26), "005930.KS", machine) is False


def test_hk_calendar_diverges_from_us(machine):
    # 2026-09-07 is Labor Day (US closed) but a normal HK Monday.
    assert is_trading_day(date(2026, 9, 7), "INTC", machine) is False
    assert is_trading_day(date(2026, 9, 7), "0981.HK", machine) is True
    # 2026-10-01 National Day: HK closed, US open.
    assert is_trading_day(date(2026, 10, 1), "0981.HK", machine) is False
    assert is_trading_day(date(2026, 10, 1), "INTC", machine) is True


def test_exchange_today_is_exchange_local(machine):
    """The law-2 boundary is the EXCHANGE's date, not UTC's."""
    assert exchange_today("INTC", machine) == \
        datetime.now(ZoneInfo("America/New_York")).date()
    assert exchange_today("0981.HK", machine) == \
        datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    # Unknown exchange: the EARLIEST covered date — conservative (fewer rows
    # qualify as settled, never more).
    expected = min(datetime.now(ZoneInfo(z)).date() for z in CALENDAR_TZ.values())
    assert exchange_today("005930.KS", machine) == expected
