#!/usr/bin/env python3
"""After-market close pass (~16:45 ET) — the evening half of the built-in
report mechanism. EVERYTHING here is PROVISIONAL (law 2):

  - fetches same-day close snapshots (settled=False, appended as observations)
  - evaluates wires in SNAPSHOT mode: verdicts are logged and displayed,
    but NO consult opens, NO wire state changes, NO history appends —
    the INTC $91.63→$92.52 and MU $899.85→$900.20 flips are the reason
  - book value stays on the SETTLED basis (the number of record); today's
    tape shows as provisional moves against the last settled close
  - renders out/close.html wearing the PROVISIONAL banner

Adjudication of today's prints happens tomorrow morning in the premarket
pass, on the settled row. This pass exists so the evening report is a
RENDERING of observations, never a verdict.

Exit codes: 0 clean · 1 every ATTEMPTED snapshot fetch failed (holiday
skips are not attempts; the brief still renders from what's on file).

Run:  python passes/close.py [--offline]
Cron (with the premarket line; CRON_TZ so DST cannot shift either pass):
  CRON_TZ=America/New_York
  0 9   * * 1-5  cd <repo> && python passes/premarket.py >> data/cron.log 2>&1
  45 16 * * 1-5  cd <repo> && python passes/close.py     >> data/cron.log 2>&1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import log as logmod
from engine.fetch import (append_rows, fetch_snapshot_yfinance,
                          latest_settled, latest_snapshot)
from engine.market_calendar import exchange_today, is_trading_day
from engine.paths import ROOT
from engine.report import render_brief, upcoming_catalysts
from engine.rules import adjudicate
from engine.valuation import value_book
from passes.premarket import fetch_universe


def run(offline: bool = False, root: Path = ROOT) -> int:
    logmod.append("pass_start", root=root, pass_name="close", offline=offline)
    warnings: list[str] = []
    universe = fetch_universe(root)
    fetch_failures: set[str] = set()

    # 1 · Same-day snapshots (observations, never verdicts). `attempted`
    # excludes holiday-skips so a partial-holiday day can still be judged
    # degraded when 100% of the ATTEMPTED fetches fail (review fix).
    attempted: set[str] = set()
    if offline:
        print("[close] --offline: rendering from snapshots already on file.")
    else:
        for ticker in universe:
            td = is_trading_day(exchange_today(ticker, root), ticker, root)
            if td is False:
                logmod.append("snapshot_skip_holiday", root=root, ticker=ticker)
                warnings.append(f"{ticker}: exchange closed today — no new "
                                f"snapshot; the one on file may be stale")
                continue
            if td is None:
                print(f"[close] {ticker}: calendar UNKNOWN — fetching anyway; "
                      f"verify the session by hand", file=sys.stderr)
                logmod.append("calendar_unknown", root=root, ticker=ticker)
                warnings.append(f"{ticker}: calendar unknown for today — verify by hand")
            attempted.add(ticker)
            try:
                row = fetch_snapshot_yfinance(ticker, root=root)
                if row is None:
                    raise RuntimeError("no usable snapshot price returned")
                if append_rows(ticker, [row], root) == 0:
                    raise RuntimeError(f"snapshot row rejected by the store ({row.close})")
                print(f"[close] {ticker}: snapshot {row.close} ({row.date})")
            except Exception as e:
                fetch_failures.add(ticker)
                print(f"[close] {ticker}: snapshot FAILED — {e}", file=sys.stderr)
                logmod.append("fetch_failed", root=root, ticker=ticker, error=str(e))
                warnings.append(f"{ticker}: snapshot fetch FAILED — {e}")
    degraded = bool(attempted) and fetch_failures == attempted

    # 2 · Provisional wire read — law 2: display-only, never acts. A snapshot
    # older than the ticker's exchange-local today is STALE: still shown,
    # but dated and marked (review fix — an undated old print rendered as
    # "today's tape" was a session claim for a non-session day).
    snapshot_rows = {}
    stale: dict[str, str] = {}
    for ticker in universe:
        snap = latest_snapshot(ticker, root)
        if snap is None:
            continue
        snapshot_rows[ticker] = snap
        if snap.date < exchange_today(ticker, root).isoformat():
            stale[ticker] = snap.date
            warnings.append(f"{ticker}: latest snapshot is {snap.date} — STALE "
                            f"vs exchange today")
    verdicts = adjudicate("snapshot", root=root, snapshot_rows=snapshot_rows)
    would = [v for v in verdicts if v.fired]
    print(f"[close] wires (PROVISIONAL): {len(verdicts)} evaluated, "
          f"{len(would)} would fire if their latest snapshot settles as-is")
    for v in would:
        print(f"  ~~ {v.wire_id}: {v.reason} — NOT actionable until settled (law 2)")

    # 3 · Latest tape vs last settled close (snapshot dates carried through).
    moves = []
    for ticker in universe:
        snap = snapshot_rows.get(ticker)
        settled = latest_settled(ticker, root)
        settled_ok = settled is not None and not settled.conflict
        pct = None
        if snap is not None and settled_ok and settled.close:
            pct = snap.close / settled.close - 1.0
        moves.append({
            "ticker": ticker,
            "settled_close": settled.close if settled_ok else None,
            "settled_date": settled.date if settled_ok else
                            ("CONFLICT-flagged" if settled is not None else None),
            "snap_close": snap.close if snap is not None else None,
            "snap_date": snap.date if snap is not None else None,
            "stale": ticker in stale,
            "pct": pct,
        })

    # 4 · Book of record (settled basis — unchanged by anything above).
    book = value_book(root=root)
    t = book["totals"]
    print(f"[close] book (settled basis): ${t['usd']:,.2f}"
          + (" (INCOMPLETE — gaps in brief)" if t["incomplete"] else ""))

    # 5 · Render the after-market brief.
    cats, cat_warns = upcoming_catalysts(root)
    for w in cat_warns:
        print(f"[close] catalysts WARNING: {w}", file=sys.stderr)
        logmod.append("catalyst_config_warning", root=root, warning=w)
        warnings.append(w)
    try:
        brief = render_brief("close", {
            "degraded": degraded,
            "verdicts": [vars(v) for v in verdicts],
            "moves": moves,
            "stale": stale,
            "book": book,
            "catalysts": cats,
            "warnings": warnings,
        }, root=root)
        print(f"[close] brief → {brief}")
        logmod.append("brief_rendered", root=root, pass_name="close", path=str(brief))
    except Exception as e:
        print(f"[close] brief render FAILED — {e}", file=sys.stderr)
        logmod.append("brief_render_failed", root=root, pass_name="close", error=str(e))

    logmod.append("pass_done", root=root, pass_name="close",
                  provisional_would_fire=len(would), degraded=degraded,
                  fetch_failures=sorted(fetch_failures))
    if degraded:
        print("[close] DEGRADED RUN — every snapshot fetch failed (exit 1)",
              file=sys.stderr)
    return 1 if degraded else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="skip fetching; render from snapshots already on file")
    args = ap.parse_args()
    sys.exit(run(offline=args.offline))
