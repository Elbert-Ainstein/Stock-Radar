"""Law 5 support: no pass may assume a trading day.

is_trading_day returns True / False / None — None means "calendar unknown for
this date" (e.g. a year we haven't listed). Passes must treat None as
"verify by hand and say so", never as either boolean. (The Korea holiday
error: an assumed session that didn't exist.)
"""
from __future__ import annotations

from datetime import date as Date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .paths import ROOT, config_dir

# Exchange-local timezones (law 2 review fix: settlement boundaries and
# session dates are EXCHANGE-LOCAL, never UTC — a 9 PM ET run must not treat
# the same-day US close as settled just because UTC rolled over).
CALENDAR_TZ = {
    "XNYS": "America/New_York",
    "XHKG": "Asia/Hong_Kong",
}


def _load_calendars(root: Path = ROOT) -> dict:
    p = config_dir(root) / "market_calendar.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def calendar_for_ticker(ticker: str, root: Path = ROOT) -> str | None:
    """Calendar name for a ticker, or None for an UNKNOWN suffix — the
    memorialized Korea-holiday error was an assumed calendar; unknown maps
    to unknown, never silently to NYSE (review fix)."""
    cfg = _load_calendars(root)
    suffix_map = cfg.get("suffix_map") or {}
    if "." in ticker:
        suffix = ticker.rsplit(".", 1)[1].upper()
        return suffix_map.get(suffix)  # None when unmapped
    return "XNYS"


def exchange_today(ticker: str, root: Path = ROOT) -> Date:
    """Today's date in the ticker's exchange-local timezone. Unknown
    calendars fall back to the EARLIEST covered timezone date (the most
    conservative settled boundary — fewer rows qualify, never more)."""
    cal = calendar_for_ticker(ticker, root)
    tz = CALENDAR_TZ.get(cal or "")
    if tz is None:
        return min(datetime.now(ZoneInfo(z)).date() for z in CALENDAR_TZ.values())
    return datetime.now(ZoneInfo(tz)).date()


def is_trading_day(d: Date, ticker: str = "SPY", root: Path = ROOT) -> bool | None:
    """True/False when the calendar covers d's year; None when the calendar
    or the year is unknown (the pass must say so, not guess)."""
    if d.weekday() >= 5:  # Sat/Sun — universal
        return False
    cfg = _load_calendars(root)
    cal_name = calendar_for_ticker(ticker, root)
    if cal_name is None:
        return None  # unknown exchange — never assume a session
    cal = (cfg.get("calendars") or {}).get(cal_name) or {}
    key = f"holidays_{d.year}"
    if key not in cal:
        return None  # unknown year — the pass must say so, not guess
    holidays = {h if isinstance(h, Date) else Date.fromisoformat(str(h))
                for h in (cal[key] or [])}
    return d not in holidays
