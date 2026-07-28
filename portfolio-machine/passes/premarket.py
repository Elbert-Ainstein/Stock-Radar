#!/usr/bin/env python3
"""Premarket pass (9:00 ET) — Phase 1 scope.

Steps (each logged; constitutional checks inline):
  1. Market-calendar check (law 5) — a non-trading or UNKNOWN day says so
     and stops; it never assumes.
  2. Backfill yesterday's settled closes for every held ticker + FX, with
     the two-source cross-check (laws 2+3). --offline skips fetching and
     adjudicates whatever is already on file.
  3. Adjudicate wires in SETTLED mode — the only actionable verdicts.
     Fires open consult tickets (law 1: the machine's entire action).
  4. Anti-parabola screen (leg (a) of the euphoria clause — informational).
  5. Book valuation on settled basis; gaps declared, never guessed.

Run:  python passes/premarket.py [--offline]
Cron: 0 9 * * 1-5  cd <repo> && python passes/premarket.py >> data/cron.log 2>&1
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from engine import log as logmod
from engine.fetch import (append_rows, cross_check, fetch_settled_stooq,
                          fetch_settled_yfinance)
from engine.market_calendar import is_trading_day
from engine.paths import ROOT, config_dir
from engine.rules import adjudicate, anti_parabola, euphoria_checks
from engine.valuation import FX_TICKERS, value_book


def held_tickers(root: Path = ROOT) -> list[str]:
    holdings = (yaml.safe_load((config_dir(root) / "holdings.yaml")
                               .read_text(encoding="utf-8")) or {})
    tickers = [s["ticker"] for s in holdings.get("holdings") or [] if s.get("ticker")]
    currencies = {s.get("currency", "USD") for s in holdings.get("holdings") or []}
    tickers += [FX_TICKERS[c] for c in currencies if c in FX_TICKERS]
    return tickers


def run(offline: bool = False, root: Path = ROOT) -> int:
    today = datetime.now(timezone.utc).date()
    logmod.append("pass_start", root=root, pass_name="premarket", offline=offline)

    # 1 · Law 5: never assume a session.
    td = is_trading_day(today, root=root)
    if td is False:
        print(f"[premarket] {today} is not a trading day (calendar) — stopping.")
        logmod.append("pass_skip", root=root, pass_name="premarket",
                      reason="not a trading day")
        return 0
    if td is None:
        print(f"[premarket] {today}: calendar UNKNOWN for this date — verify by "
              f"hand (config/market_calendar.yaml has no entry for {today.year}). "
              f"Continuing with settled backfill only; flagging the gap.")
        logmod.append("calendar_unknown", root=root, date=str(today))

    # 2 · Settled backfill + cross-check.
    if offline:
        print("[premarket] --offline: adjudicating rows already on file.")
    else:
        for ticker in held_tickers(root):
            try:
                primary = fetch_settled_yfinance(ticker)
                secondary = fetch_settled_stooq(ticker)
                checked = cross_check(primary, secondary)
                n = append_rows(ticker, checked, root)
                conflicts = sum(1 for r in checked if r.conflict)
                print(f"[premarket] {ticker}: +{n} settled row(s)"
                      + (f", {conflicts} CONFLICT-flagged" if conflicts else ""))
                if conflicts:
                    logmod.append("price_conflict", root=root, ticker=ticker,
                                  count=conflicts)
            except Exception as e:
                # Loud degradation — a source being down is a logged gap,
                # never a silent skip (charter: silence is a violation).
                print(f"[premarket] {ticker}: fetch FAILED — {e}", file=sys.stderr)
                logmod.append("fetch_failed", root=root, ticker=ticker, error=str(e))

    # 3 · Adjudicate — settled mode only in this pass.
    verdicts = adjudicate("settled", root=root)
    fired = [v for v in verdicts if v.fired]
    blocked = [v for v in verdicts if v.fired is None]
    print(f"[premarket] wires: {len(verdicts)} evaluated, {len(fired)} FIRED, "
          f"{len(blocked)} could not adjudicate")
    for v in fired:
        print(f"  >> {v.wire_id}: {v.reason} — consult opened in consults/")
    for v in blocked:
        print(f"  ?? {v.wire_id}: {v.reason}")

    # 4 · Charter §V monitors: euphoria protocol (ACTS — opens consults on
    # settled >=2x-cost) and the anti-parabola screen (informational sizing
    # law + Momentum-RISK redline).
    for f in euphoria_checks(root=root):
        print(f"[premarket] EUPHORIA: {f['ticker']} at {f['multiple']}x cost — "
              f"consult opened: {f['consult']}")
    for f in anti_parabola(root=root):
        print(f"[premarket] anti-parabola: {f['ticker']} +{f['gain']:.0%} "
              f"in {f['window_days']}d — {f['note']}")

    # 5 · Valuation on settled basis; the floor reported, never counted.
    book = value_book(root=root)
    t = book["totals"]
    print(f"[premarket] book: ${t['usd']:,.2f}"
          + (" (INCOMPLETE — gaps below)" if t["incomplete"] else ""))
    for g in book["gaps"]:
        print(f"  gap: {g['ticker']} — {g['reason']}")
    fl = book["floor"]
    print(f"[premarket] floor: ${fl['amount']:,.2f} {fl['currency']} — "
          f"sacred, outside the book (Charter §V)")
    logmod.append("pass_done", root=root, pass_name="premarket",
                  wires_fired=len(fired), book_usd=t["usd"],
                  book_incomplete=t["incomplete"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="skip fetching; adjudicate rows already on file")
    args = ap.parse_args()
    sys.exit(run(offline=args.offline))
