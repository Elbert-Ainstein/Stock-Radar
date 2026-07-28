"""Book valuation from settled rows (laws 2 + 3: the book's value is a
settled-basis number; unknowns are declared, never guessed)."""
from __future__ import annotations

from pathlib import Path

import yaml

from .fetch import latest_settled
from .paths import ROOT, config_dir

FX_TICKERS = {"HKD": "HKDUSD=X"}  # settled FX rows live in data/prices/ like any ticker


def value_book(root: Path = ROOT) -> dict:
    """Returns {seats: [...], totals: {...}, gaps: [...]}. A seat whose price
    or FX is missing lands in gaps with a reason — the total then carries
    an explicit 'incomplete' flag instead of a silently wrong number."""
    holdings = (yaml.safe_load((config_dir(root) / "holdings.yaml")
                               .read_text(encoding="utf-8")) or {})
    seats_out, gaps = [], []
    total_usd = 0.0

    fx_cache: dict[str, float | None] = {}

    def fx_to_usd(currency: str) -> float | None:
        if currency == "USD":
            return 1.0
        if currency not in fx_cache:
            t = FX_TICKERS.get(currency)
            row = latest_settled(t, root) if t else None
            fx_cache[currency] = row.close if row else None
        return fx_cache[currency]

    for seat in holdings.get("holdings") or []:
        ticker, currency = seat.get("ticker"), seat.get("currency", "USD")
        shares = float(seat.get("shares") or 0)
        row = latest_settled(ticker, root)
        rate = fx_to_usd(currency)
        if row is None:
            gaps.append({"ticker": ticker, "reason": "no settled price row"})
            continue
        if rate is None:
            gaps.append({"ticker": ticker, "reason": f"no settled FX for {currency}"})
            continue
        value_usd = shares * row.close * rate
        total_usd += value_usd
        seats_out.append({
            "ticker": ticker, "shares": shares, "close": row.close,
            "close_date": row.date, "currency": currency, "fx": rate,
            "value_usd": round(value_usd, 2), "source": row.source,
        })

    for c in holdings.get("cash") or []:
        rate = fx_to_usd(c.get("currency", "USD"))
        amt = float(c.get("amount") or 0)
        if rate is None:
            gaps.append({"ticker": f"CASH:{c.get('currency')}", "reason": "no settled FX"})
            continue
        total_usd += amt * rate

    # THE FLOOR (Charter §V): reported, NEVER counted in the investable book.
    floor_cfg = holdings.get("floor") or {}
    floor = {
        "amount": float(floor_cfg.get("amount") or 0),
        "currency": floor_cfg.get("currency", "USD"),
        "counted_in_book": False,
        "note": floor_cfg.get("note", ""),
    }

    return {
        "seats": seats_out,
        "totals": {"usd": round(total_usd, 2), "incomplete": bool(gaps)},
        "gaps": gaps,
        "floor": floor,
    }
