#!/usr/bin/env python3
"""
feed_insider_to_universe.py — Module 11b feeder for insider activity.

Reads recent insider scout signals from `signals` table and tags matching
tickers in `discovery_universe` with source="insider_active". This is what
unlocks cross-type convergence in Module 11a — once 13F-flagged tickers also
carry an `insider_active` tag, the convergence detector counts them as
2-source candidates without any code change to the detector itself.

LIMITATION (well-known, see report Module 11):
The upstream scout currently fails to parse Form-4 transaction codes — every
row reads `buys: 0, sells: 0, kind: unknown`. So `insider_active` here means
"the scout saw at least one Form-4 filing in the recent window," not
"insiders are buying." When the scout learns to classify codes (P=open-market
purchase, S=sale, A=grant), this feeder will tighten its filter from
`transaction_count >= 1` to `data.buys > 0` and rename the tag to
`insider_buying`.

The feeder also requires the upstream insider scout to have been run with
`--source discovery` so it scanned the broader universe (not just the legacy
watchlist of 52 tickers). Without that, the only `signals` rows are for
watchlist-seeded tickers and there's no overlap with the 13F-flagged names.
The feeder will print a warning when the input data shows no insider
coverage on 13F-flagged tickers — that's the diagnostic that the scout
needs to be re-run with `--source discovery`.

Usage:
  python scripts/feed_insider_to_universe.py
  python scripts/feed_insider_to_universe.py --window-days 60 --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env  # noqa: E402

load_env()

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

INSIDER_TAG = "insider_active"


def _accumulate_source(existing: str | None, new_tag: str) -> str:
    """Append new_tag to existing comma-separated source field if not already
    present. Same accumulation pattern as discovery_13f.py (append-only,
    deduped). Status is never downgraded — that's the discovery_universe
    invariant, this feeder doesn't touch it."""
    tags = [t.strip() for t in (existing or "").split(",") if t.strip()]
    if new_tag not in tags:
        tags.append(new_tag)
    return ", ".join(tags)


def find_active_tickers(
    *,
    window_days: int,
    min_transactions: int = 1,
) -> list[dict]:
    """Return tickers that have insider scout activity within the recent window.

    Window: rows where `created_at >= now - window_days`. We look at the
    scout's last run, not the filing date inside the row, because the
    scout's coverage rotates per run and the most recent run is what
    represents 'has been observed recently'.

    Threshold: max(transaction_count) across rows in the window must be >=
    min_transactions. Default 1 — any insider activity at all qualifies,
    given the upstream scout's classification gap. Caller can raise this.
    """
    from supabase_helper import get_client
    sb = get_client()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    rows = sb.table("signals").select(
        "ticker,data,created_at,signal"
    ).eq("scout", "insider").gte("created_at", cutoff).execute().data or []

    # Per-ticker max transaction_count + most recent created_at + signal label
    by_ticker: dict[str, dict] = {}
    for r in rows:
        t = r["ticker"]
        d = r.get("data") or {}
        tx = d.get("transaction_count", 0) or 0
        ca = r.get("created_at")
        sig = r.get("signal")
        cur = by_ticker.get(t)
        if cur is None:
            by_ticker[t] = {
                "ticker": t,
                "max_tx": tx,
                "latest_run": ca,
                "rows": 1,
                "signal": sig,
                # Track buys/sells if upstream ever populates them
                "buys": d.get("buys", 0) or 0,
                "sells": d.get("sells", 0) or 0,
            }
        else:
            cur["rows"] += 1
            if tx > cur["max_tx"]:
                cur["max_tx"] = tx
            if ca and (cur["latest_run"] is None or ca > cur["latest_run"]):
                cur["latest_run"] = ca
                cur["signal"] = sig
            cur["buys"] = max(cur["buys"], d.get("buys", 0) or 0)
            cur["sells"] = max(cur["sells"], d.get("sells", 0) or 0)

    return [v for v in by_ticker.values() if v["max_tx"] >= min_transactions]


def upsert_to_universe(active: list[dict], *, dry_run: bool = False) -> dict:
    """For each active ticker that ALREADY exists in discovery_universe,
    append the insider_active tag to its source field. Skip tickers that
    are NOT in discovery_universe — this feeder enriches existing rows, it
    doesn't seed new ones (that's the 13F ingester's job, or the discovery
    scout's, or the watchlist seeder).

    Why skip new tickers: a Form-4 filing alone isn't a discovery signal —
    every public company has insider Form-4 activity. We only want to
    upgrade the source count on tickers that ALSO appeared in some other
    discovery channel.

    Returns: summary dict.
    """
    from supabase_helper import get_client
    sb = get_client()

    # Fetch existing rows once
    tickers = [a["ticker"] for a in active]
    if not tickers:
        return {"checked": 0, "updated": 0, "skipped_not_in_universe": 0, "already_tagged": 0}

    # PostgREST `in_` filter
    existing = sb.table("discovery_universe").select(
        "ticker,source,status"
    ).in_("ticker", tickers).execute().data or []
    existing_by_t = {r["ticker"]: r for r in existing}

    summary = {
        "checked": len(active),
        "updated": 0,
        "skipped_not_in_universe": 0,
        "already_tagged": 0,
    }
    updates_planned: list[dict] = []
    for a in active:
        t = a["ticker"]
        cur = existing_by_t.get(t)
        if cur is None:
            summary["skipped_not_in_universe"] += 1
            continue
        existing_src = cur.get("source") or ""
        if INSIDER_TAG in [s.strip() for s in existing_src.split(",")]:
            summary["already_tagged"] += 1
            continue
        new_src = _accumulate_source(existing_src, INSIDER_TAG)
        updates_planned.append({"ticker": t, "old_src": existing_src, "new_src": new_src})

    if dry_run:
        summary["would_update"] = len(updates_planned)
        return summary

    # Apply updates
    for u in updates_planned:
        try:
            sb.table("discovery_universe").update(
                {"source": u["new_src"]}
            ).eq("ticker", u["ticker"]).execute()
            summary["updated"] += 1
        except Exception as e:
            print(f"  [WARN] update failed for {u['ticker']}: {e}", file=sys.stderr)

    return summary


def diagnose_overlap_with_13f() -> dict:
    """Diagnostic: how many 13F-tagged tickers also appear in the recent
    insider scout output? If this is zero, the scout was NOT run with
    `--source discovery` — re-run the scout before re-running this feeder."""
    from supabase_helper import get_client
    sb = get_client()
    # 13F-tagged tickers in discovery_universe
    rows = sb.table("discovery_universe").select("ticker,source").like(
        "source", "%13f_%"
    ).execute().data or []
    ticker_13f = {r["ticker"] for r in rows}
    # Recent insider tickers (any window — diagnostic only)
    insider_rows = sb.table("signals").select("ticker").eq("scout", "insider").execute().data or []
    ticker_insider = {r["ticker"] for r in insider_rows}
    overlap = ticker_13f & ticker_insider
    return {
        "13f_tagged_count": len(ticker_13f),
        "insider_scanned_count": len(ticker_insider),
        "overlap_count": len(overlap),
        "overlap_sample": sorted(overlap)[:10],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-days", type=int, default=30,
                        help="Look back this many days for insider scout activity (default 30)")
    parser.add_argument("--min-transactions", type=int, default=1,
                        help="Minimum insider transactions in window to qualify (default 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change; don't write")
    args = parser.parse_args()

    print(f"\n=== feed_insider_to_universe — window={args.window_days}d, min_tx={args.min_transactions} ===")

    diag = diagnose_overlap_with_13f()
    print(f"  diagnostic: 13F-tagged tickers={diag['13f_tagged_count']}, "
          f"insider-scanned tickers={diag['insider_scanned_count']}, "
          f"overlap={diag['overlap_count']}")
    if diag["overlap_sample"]:
        print(f"  overlap sample: {diag['overlap_sample']}")
    if diag["overlap_count"] == 0:
        print("  WARNING: zero overlap. The insider scout has not been run with "
              "--source discovery. Run `python scripts/scout_insider.py --source "
              "discovery` first, then re-run this feeder.")

    active = find_active_tickers(
        window_days=args.window_days,
        min_transactions=args.min_transactions,
    )
    print(f"  found {len(active)} tickers with insider activity in window")

    summary = upsert_to_universe(active, dry_run=args.dry_run)
    print(f"  result: {summary}")

    if not args.dry_run and summary.get("updated", 0) > 0:
        print(f"\n  Hint: re-run convergence detector to see new cross-type signals:")
        print(f"  python scripts/convergence_detector.py --top 25")


if __name__ == "__main__":
    main()
