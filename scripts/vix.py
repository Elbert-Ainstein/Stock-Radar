"""
vix.py — VIX tracker: the macro layer's first LIVE signal.

Fetches the CBOE Volatility Index (^VIX), classifies the volatility regime, and
summarizes the recent trend. The VIX is the market's "fear gauge" — a spike means
risk-off, which should make the judgment layer more cautious on high-beta names.

The classifier + trend + context-line builders are PURE (unit-tested, no network).
`fetch_vix()` is the only networked function (yfinance).
"""

from __future__ import annotations

from typing import Optional

# Volatility-regime bands. Standard-ish VIX levels; the note frames the macro tilt.
# (lo inclusive, hi exclusive, regime, note)
VIX_BANDS = [
    (0.0, 15.0, "calm", "low-vol / risk-on; complacency risk"),
    (15.0, 20.0, "normal", "baseline volatility"),
    (20.0, 28.0, "elevated", "rising stress; risk-off tilt — discipline high-beta sizing"),
    (28.0, 40.0, "stress", "risk-off; de-risking underway"),
    (40.0, 1e9, "crisis", "panic / dislocation"),
]


def classify_vix_regime(level: Optional[float]) -> dict:
    """Map a VIX level to {regime, note, band}. Unknown if level is missing/invalid."""
    if level is None or level < 0:
        return {"regime": "unknown", "note": "", "band": ""}
    for lo, hi, name, note in VIX_BANDS:
        if lo <= level < hi:
            band = f"{lo:g}-{hi:g}" if hi < 1e9 else f"{lo:g}+"
            return {"regime": name, "note": note, "band": band}
    return {"regime": "unknown", "note": "", "band": ""}


def trend_label(level: Optional[float], reference: Optional[float]) -> str:
    """Direction of VIX vs a reference (e.g. a week ago). Pure."""
    if not level or not reference or reference <= 0:
        return "n/a"
    chg = (level / reference - 1.0) * 100.0
    if chg >= 20:
        return "spiking"
    if chg >= 5:
        return "rising"
    if chg <= -20:
        return "collapsing"
    if chg <= -5:
        return "falling"
    return "flat"


def vix_context_line(vix: Optional[dict]) -> str:
    """One-line [VIX] block for injection into the macro context. Pure."""
    if not vix or vix.get("level") is None:
        return "[VIX] unavailable"
    day = vix.get("day_change_pct")
    day_s = f"{day:+.1f}% vs prior close" if isinstance(day, (int, float)) else "n/a"
    return (
        f"[VIX] {vix['level']:g} — {vix['regime']} ({vix.get('note', '')}); "
        f"{vix.get('trend', 'n/a')}, {day_s}."
    )


def fetch_vix() -> Optional[dict]:
    """Live VIX snapshot from yfinance (^VIX). None if unavailable.

    Returns {level, prev_close, day_change_pct, week_ago, trend, regime, note,
    band, history:[(date, close), ...]}.
    """
    try:
        import yfinance as yf
        h = yf.Ticker("^VIX").history(period="1mo")["Close"]
        if h is None or len(h) == 0:
            return None
        level = float(h.iloc[-1])
        prev = float(h.iloc[-2]) if len(h) >= 2 else level
        week_ago = float(h.iloc[-6]) if len(h) >= 6 else float(h.iloc[0])
        reg = classify_vix_regime(level)
        return {
            "level": round(level, 2),
            "prev_close": round(prev, 2),
            "day_change_pct": round((level / prev - 1.0) * 100.0, 1) if prev else None,
            "week_ago": round(week_ago, 2),
            "trend": trend_label(level, week_ago),
            "regime": reg["regime"],
            "note": reg["note"],
            "band": reg["band"],
            "history": [(d.strftime("%Y-%m-%d"), round(float(c), 2)) for d, c in h.items()],
        }
    except Exception as e:
        import sys
        print(f"  [vix] fetch failed: {e}", file=sys.stderr)
        return None


def main():
    v = fetch_vix()
    if not v:
        print("VIX unavailable")
        return
    print(vix_context_line(v))
    print(f"  level={v['level']} regime={v['regime']} band={v['band']} "
          f"trend={v['trend']} (week_ago={v['week_ago']}, day {v['day_change_pct']:+}%)")


if __name__ == "__main__":
    main()
