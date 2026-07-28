"""Price acquisition — one fetcher, two modes (laws 2 + 3).

- SNAPSHOT mode: informational, settled=False. Never adjudicates anything.
- SETTLED mode: authoritative — only sessions strictly BEFORE the current
  exchange date qualify (a same-day close is provisional by definition; the
  INTC/MU flips are why).

Every row carries provenance: source + fetched_at + settled flag (law 3).
Two-source cross-check on settled rows: conflicts are FLAGGED, never
averaged, and a flagged row cannot adjudicate a wire (rules.py enforces).

Storage is append-only CSV per ticker. A changed number for an existing date
gets a NEW row with note="correction"; readers take the LATEST unflagged
settled row per date (law 6: corrections go forward).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict, field
from datetime import date as Date, datetime, timezone
from pathlib import Path

from .paths import ROOT, prices_dir

CSV_COLUMNS = ["date", "close", "settled", "source", "fetched_at", "conflict", "note"]
CROSS_CHECK_TOLERANCE = 0.005  # 0.5% — beyond this, sources conflict


@dataclass
class PriceRow:
    ticker: str
    date: str            # YYYY-MM-DD, exchange-local session date
    close: float
    settled: bool
    source: str
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    conflict: bool = False
    note: str = ""


# ── Pure mechanics (offline-testable) ──────────────────────────────────────────

def mark_settled(rows: list[PriceRow], today: Date) -> list[PriceRow]:
    """Law 2: only sessions strictly before `today` may be settled. Any row
    dated today or later is force-downgraded to snapshot."""
    out = []
    for r in rows:
        settled = r.settled and Date.fromisoformat(r.date) < today
        out.append(PriceRow(**{**asdict(r), "settled": settled}))
    return out


def cross_check(primary: list[PriceRow], secondary: list[PriceRow],
                tolerance: float = CROSS_CHECK_TOLERANCE) -> list[PriceRow]:
    """Law 3: two-source verification of settled rows. A date whose sources
    disagree beyond tolerance is FLAGGED (conflict=True) — never averaged.
    Dates the secondary doesn't cover pass through unflagged but noted."""
    sec_by_date = {r.date: r for r in secondary}
    out = []
    for r in primary:
        if not r.settled:
            out.append(r)
            continue
        s = sec_by_date.get(r.date)
        if s is None:
            out.append(PriceRow(**{**asdict(r), "note": (r.note + " single-source").strip()}))
            continue
        rel = abs(r.close - s.close) / r.close if r.close else 1.0
        if rel > tolerance:
            out.append(PriceRow(**{
                **asdict(r), "conflict": True,
                "note": (r.note + f" CONFLICT {r.source}={r.close} vs {s.source}={s.close}").strip(),
            }))
        else:
            out.append(PriceRow(**{**asdict(r), "note": (r.note + f" xchk:{s.source}").strip()}))
    return out


def _csv_path(ticker: str, root: Path) -> Path:
    safe = ticker.replace("/", "_").replace("\\", "_")
    return prices_dir(root) / f"{safe}.csv"


def load_rows(ticker: str, root: Path = ROOT) -> list[PriceRow]:
    p = _csv_path(ticker, root)
    if not p.exists():
        return []
    out = []
    with open(p, newline="", encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            out.append(PriceRow(
                ticker=ticker, date=rec["date"], close=float(rec["close"]),
                settled=rec["settled"] == "True", source=rec["source"],
                fetched_at=rec["fetched_at"], conflict=rec["conflict"] == "True",
                note=rec.get("note", ""),
            ))
    return out


def append_rows(ticker: str, rows: list[PriceRow], root: Path = ROOT) -> int:
    """Append-only persistence (law 6). Rules:
    - a (date, settled) pair not on file appends normally;
    - a settled date already on file with a DIFFERENT close appends a new row
      with note 'correction' (the old row is never touched);
    - an identical settled row is skipped (idempotent backfills);
    - snapshot rows always append (they are a time series of observations).
    Returns the number of rows written."""
    existing = load_rows(ticker, root)
    settled_latest: dict[str, PriceRow] = {}
    for r in existing:
        if r.settled:
            settled_latest[r.date] = r  # file order == chronological appends

    p = _csv_path(ticker, root)
    is_new_file = not p.exists()
    written = 0
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if is_new_file:
            w.writeheader()
        for r in rows:
            if r.settled and r.date in settled_latest:
                prev = settled_latest[r.date]
                if abs(prev.close - r.close) < 1e-9 and prev.conflict == r.conflict:
                    continue  # identical — idempotent
                r = PriceRow(**{**asdict(r), "note": (r.note + " correction").strip()})
            rec = asdict(r)
            rec.pop("ticker")
            w.writerow(rec)
            if r.settled:
                settled_latest[r.date] = r
            written += 1
    return written


def latest_settled(ticker: str, root: Path = ROOT) -> PriceRow | None:
    """Latest-dated settled row, taking the LAST unflagged write per date
    (corrections go forward). Flagged-conflict rows are excluded — a
    conflicted print cannot be the book's truth."""
    per_date: dict[str, PriceRow] = {}
    for r in load_rows(ticker, root):
        if r.settled and not r.conflict:
            per_date[r.date] = r
    if not per_date:
        return None
    return per_date[max(per_date)]


# ── Network fetchers (thin; passes call these, tests never do) ────────────────

def fetch_settled_yfinance(ticker: str, lookback_days: int = 30) -> list[PriceRow]:
    import yfinance as yf  # lazy: keeps the engine importable offline
    today = datetime.now(timezone.utc).date()
    hist = yf.Ticker(ticker).history(period=f"{lookback_days}d", auto_adjust=False)
    rows = [
        PriceRow(ticker=ticker, date=d.strftime("%Y-%m-%d"), close=float(c),
                 settled=True, source="yfinance")
        for d, c in zip(hist.index, hist["Close"])
    ]
    return mark_settled(rows, today)  # today's bar, if present, demotes to snapshot


def fetch_settled_stooq(ticker: str) -> list[PriceRow]:
    """Second source (law 3). Stooq covers US tickers keylessly; unsupported
    symbols return [] — the cross-check then marks rows single-source."""
    import requests
    if "." in ticker:
        return []  # non-US suffixes unsupported here; single-source noted
    sym = f"{ticker.lower()}.us"
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception:
        return []
    today = datetime.now(timezone.utc).date()
    rows = []
    lines = resp.text.strip().splitlines()
    if len(lines) < 2 or not lines[0].lower().startswith("date"):
        return []
    for rec in csv.DictReader(lines):
        try:
            rows.append(PriceRow(ticker=ticker, date=rec["Date"],
                                 close=float(rec["Close"]), settled=True,
                                 source="stooq"))
        except (KeyError, ValueError):
            continue
    return mark_settled(rows, today)


def fetch_snapshot_yfinance(ticker: str) -> PriceRow | None:
    import yfinance as yf
    t = yf.Ticker(ticker)
    price = None
    try:
        price = t.fast_info.last_price
    except Exception:
        pass
    if not price:
        hist = t.history(period="1d")
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])
    return PriceRow(ticker=ticker, date=datetime.now(timezone.utc).date().isoformat(),
                    close=float(price), settled=False, source="yfinance-snapshot")
