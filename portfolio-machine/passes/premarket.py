#!/usr/bin/env python3
"""Premarket pass (9:00 ET) — Phase 1 scope.

Steps (each logged; constitutional checks inline):
  1. Catalyst config validation + upcoming listing (the file's promise).
  2. Settled backfill PER EXCHANGE CALENDAR (2026-07-28 review fix: the old
     XNYS-only gate skipped the whole book on a US holiday with HK open).
     Fetch universe = held tickers ∪ armed-wire tickers ∪ FX. Two-source
     cross-check; every degradation (secondary down, single-source rows,
     fetch failure) is logged and printed — silence is a violation.
  3. Adjudicate wires in SETTLED mode — the only actionable verdicts.
     Fires open consult tickets (law 1: the machine's entire action).
     Adjudication and valuation run regardless of today's calendars — they
     read what is on file.
  4. Charter §V monitors: euphoria protocol (acts) + anti-parabola (informs).
  5. Book valuation on settled basis; gaps declared; the floor reported,
     never counted.

Exit codes (review fix — cron can now tell health from failure):
  0 = clean (including legitimate all-exchanges-closed skips)
  1 = every fetch failed, or an armed wire was unadjudicable due to a
      failed/absent fetch — the pass ran but the book may be stale.

Run:  python passes/premarket.py [--offline]
Cron (host-local time — recommend CRON_TZ so DST cannot shift the pass):
  CRON_TZ=America/New_York
  0 9 * * 1-5  cd <repo> && python passes/premarket.py >> data/cron.log 2>&1
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as Date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from engine import log as logmod
from engine.fetch import (append_rows, cross_check, fetch_settled_stooq,
                          fetch_settled_yfinance)
from engine.market_calendar import exchange_today, is_trading_day
from engine.paths import ROOT, config_dir
from engine.rules import (adjudicate, anti_parabola, euphoria_checks,
                          load_tripwires, load_wire_state, effective_status)
from engine.valuation import FX_TICKERS, value_book


def fetch_universe(root: Path = ROOT) -> list[str]:
    """Held tickers ∪ armed-wire tickers ∪ FX (review fix: a wire on a
    non-held ticker used to report 'no usable price row' forever because
    nothing ever fetched it)."""
    holdings = (yaml.safe_load((config_dir(root) / "holdings.yaml")
                               .read_text(encoding="utf-8")) or {})
    tickers = [s["ticker"] for s in holdings.get("holdings") or [] if s.get("ticker")]
    currencies = {s.get("currency", "USD") for s in holdings.get("holdings") or []}
    tickers += [FX_TICKERS[c] for c in currencies if c in FX_TICKERS]
    state = load_wire_state(root)
    for wire in load_tripwires(root).get("tripwires") or []:
        t = wire.get("ticker")
        if t and effective_status(wire, state) == "armed" and t not in tickers:
            tickers.append(t)
    return tickers


def validate_catalysts(root: Path = ROOT) -> list[str]:
    """Parse + sanity-check catalysts.yaml; return warnings (loud, logged)."""
    warnings = []
    p = config_dir(root) / "catalysts.yaml"
    if not p.exists():
        return ["catalysts.yaml missing"]
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return [f"catalysts.yaml unreadable: {e}"]
    today = datetime.now(timezone.utc).date()
    upcoming = []
    for i, c in enumerate(data.get("catalysts") or []):
        d = c.get("date")
        try:
            d = d if isinstance(d, Date) else Date.fromisoformat(str(d))
        except Exception:
            warnings.append(f"catalyst #{i}: bad date {c.get('date')!r}")
            continue
        if c.get("pass") not in ("event", "radar", "premarket-note"):
            warnings.append(f"catalyst #{i} ({d}): unknown pass {c.get('pass')!r}")
        if today <= d <= today.__class__.fromordinal(today.toordinal() + 30):
            upcoming.append(f"{d} {c.get('ticker')} — {c.get('what')}")
    for u in upcoming:
        print(f"[premarket] upcoming catalyst: {u}")
    return warnings


def run(offline: bool = False, root: Path = ROOT) -> int:
    logmod.append("pass_start", root=root, pass_name="premarket", offline=offline)
    degraded = False

    # 1 · Catalyst config check (makes the config's claim true).
    for w in validate_catalysts(root):
        print(f"[premarket] catalysts WARNING: {w}", file=sys.stderr)
        logmod.append("catalyst_config_warning", root=root, warning=w)

    universe = fetch_universe(root)

    # 2 · Settled backfill, gated PER TICKER by its own exchange calendar.
    fetch_failures: set[str] = set()
    single_source_rows = 0
    if offline:
        print("[premarket] --offline: adjudicating rows already on file.")
    else:
        for ticker in universe:
            ex_today = exchange_today(ticker, root)
            td = is_trading_day(ex_today, ticker, root)
            if td is False:
                logmod.append("fetch_skip_holiday", root=root, ticker=ticker,
                              date=str(ex_today))
                continue
            if td is None:
                print(f"[premarket] {ticker}: calendar UNKNOWN for {ex_today} — "
                      f"fetching anyway; VERIFY the session by hand "
                      f"(config/market_calendar.yaml gap).", file=sys.stderr)
                logmod.append("calendar_unknown", root=root, ticker=ticker,
                              date=str(ex_today))
            try:
                primary = fetch_settled_yfinance(ticker, root=root)
                secondary, sec_status = fetch_settled_stooq(ticker, root=root)
                if sec_status not in ("ok", "unsupported"):
                    # Law 3 degradation must be LOUD — a dead secondary means
                    # single-source truth, the exact exposure the law exists for.
                    print(f"[premarket] {ticker}: secondary source {sec_status} — "
                          f"rows are SINGLE-SOURCE this run", file=sys.stderr)
                    logmod.append("secondary_source_failed", root=root,
                                  ticker=ticker, status=sec_status)
                checked = cross_check(primary, secondary)
                single_source_rows += sum(
                    1 for r in checked if r.settled and "single-source" in r.note)
                n = append_rows(ticker, checked, root)
                conflicts = sum(1 for r in checked if r.conflict)
                print(f"[premarket] {ticker}: +{n} settled row(s)"
                      + (f", {conflicts} CONFLICT-flagged" if conflicts else ""))
                if conflicts:
                    logmod.append("price_conflict", root=root, ticker=ticker,
                                  count=conflicts)
            except Exception as e:
                fetch_failures.add(ticker)
                print(f"[premarket] {ticker}: fetch FAILED — {e}", file=sys.stderr)
                logmod.append("fetch_failed", root=root, ticker=ticker, error=str(e))
        if single_source_rows:
            print(f"[premarket] NOTE: {single_source_rows} settled row(s) are "
                  f"single-source (no cross-check) this run")
            logmod.append("single_source_rows", root=root, count=single_source_rows)
        if universe and fetch_failures == set(universe):
            degraded = True

    # 3 · Adjudicate — settled mode only; runs regardless of today's calendars.
    verdicts = adjudicate("settled", root=root)
    fired = [v for v in verdicts if v.fired]
    blocked = [v for v in verdicts if v.fired is None]
    print(f"[premarket] wires: {len(verdicts)} evaluated, {len(fired)} FIRED, "
          f"{len(blocked)} could not adjudicate")
    for v in fired:
        print(f"  >> {v.wire_id}: {v.reason} — consult opened in consults/")
    for v in blocked:
        print(f"  ?? {v.wire_id}: {v.reason}")
        if v.ticker in fetch_failures or (not offline and v.close is None
                                          and v.ticker not in universe):
            degraded = True

    # 4 · Charter §V monitors.
    for f in euphoria_checks(root=root):
        print(f"[premarket] EUPHORIA: {f['ticker']} at {f['multiple']}x cost — "
              f"consult opened: {f['consult']}")
    for f in anti_parabola(root=root):
        print(f"[premarket] anti-parabola: {f['ticker']} +{f['gain']:.0%} "
              f"(vs {f['from_date']}) — {f['note']}")

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
                  book_incomplete=t["incomplete"], degraded=degraded,
                  fetch_failures=sorted(fetch_failures))
    if degraded:
        print("[premarket] DEGRADED RUN — see fetch failures above (exit 1)",
              file=sys.stderr)
    return 1 if degraded else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="skip fetching; adjudicate rows already on file")
    args = ap.parse_args()
    sys.exit(run(offline=args.offline))
