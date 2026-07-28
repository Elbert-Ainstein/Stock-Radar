"""Law 5 support: no pass may assume a trading day.

is_trading_day returns True / False / None — None means "calendar unknown for
this date" (e.g. a year we haven't listed). Passes must treat None as
"verify by hand and say so", never as either boolean. (The Korea holiday
error: an assumed session that didn't exist.)
"""
from __future__ import annotations

from datetime import date as Date
from pathlib import Path

import yaml

from .paths import ROOT, config_dir


def _load_calendars(root: Path = ROOT) -> dict:
    p = config_dir(root) / "market_calendar.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def calendar_for_ticker(ticker: str, root: Path = ROOT) -> str:
    cfg = _load_calendars(root)
    suffix_map = cfg.get("suffix_map") or {}
    if "." in ticker:
        suffix = ticker.rsplit(".", 1)[1].upper()
        return suffix_map.get(suffix, "XNYS")
    return "XNYS"


def is_trading_day(d: Date, ticker: str = "SPY", root: Path = ROOT) -> bool | None:
    """True/False when the calendar covers d's year; None when it doesn't."""
    if d.weekday() >= 5:  # Sat/Sun — universal
        return False
    cfg = _load_calendars(root)
    cal_name = calendar_for_ticker(ticker, root)
    cal = (cfg.get("calendars") or {}).get(cal_name) or {}
    key = f"holidays_{d.year}"
    if key not in cal:
        return None  # unknown year — the pass must say so, not guess
    holidays = {h if isinstance(h, Date) else Date.fromisoformat(str(h))
                for h in (cal[key] or [])}
    return d not in holidays
