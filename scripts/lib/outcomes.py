"""
outcomes.py - Helpers for the thesis_outcomes table.

The thesis_outcomes table is the falsifiability mechanism for the thesis
engine: every thesis target gets compared to actual prices at T+30/90/180.
Without it, the system has no external check on whether targets are
calibrated.

Two entry points:
  - log_thesis_outcome(): called immediately after a thesis is saved.
    Creates the outcome row with NULL forward prices.
  - refresh_outcomes(): called periodically (daily cron OK). Fills in
    the T+30/90/180 cells for any thesis where the time window has
    elapsed AND the cell is still NULL.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Optional

import yfinance as yf

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _get_client():
    from supabase_helper import get_client
    return get_client()


def log_thesis_outcome(thesis_id: int) -> bool:
    """Create the thesis_outcomes row for a freshly-saved thesis.

    Pulls ticker/thesis_target/spot_at_run/conviction/position_size_pct from
    the theses table by ID. Idempotent: if a row already exists, returns
    True without modification.

    Failure modes are distinguished so the caller can tell the difference:
      - Row not found at all → likely RLS or wrong thesis_id.
      - Row found but `thesis_target` / `spot_at_run` keys are MISSING from
        the response (schema drift — column was renamed or removed). Loud.
      - Row found, keys present, but values are NULL. This is expected for
        thesis runs where the model didn't produce a target (e.g. BROKEN
        conviction). Quiet skip.
    """
    sb = _get_client()
    # Check if outcome row already exists
    existing = sb.table("thesis_outcomes").select("thesis_id").eq("thesis_id", thesis_id).execute()
    if existing.data:
        return True

    # Pull from theses
    th = sb.table("theses").select(
        "id,ticker,run_at,thesis_target,spot_at_run,conviction,position_size_pct"
    ).eq("id", thesis_id).execute()
    if not th.data:
        print(f"  [outcomes] no thesis with id={thesis_id}", file=sys.stderr)
        return False
    t = th.data[0]
    # Schema-drift detection: if the SELECT returned a row but the expected
    # fields are MISSING from the keys, that's a column rename/removal — not
    # a "this thesis didn't produce a target" miss. The two cases need
    # different signals because one needs ops attention and the other is a
    # routine BROKEN-conviction skip.
    expected_keys = {"thesis_target", "spot_at_run"}
    missing_keys = expected_keys - set(t.keys())
    if missing_keys:
        print(
            f"  [outcomes] HARD WARNING: theses row for id={thesis_id} is "
            f"missing expected columns {sorted(missing_keys)}. Schema drift "
            f"suspected — outcome tracking is BROKEN until the schema is "
            f"reconciled. Got keys: {sorted(t.keys())[:10]}",
            file=sys.stderr, flush=True,
        )
        return False
    if t.get("thesis_target") is None or t.get("spot_at_run") is None:
        # Routine: model produced no target, or spot was unavailable at run.
        # Quiet skip — this is expected for BROKEN-conviction runs.
        print(
            f"  [outcomes] thesis {thesis_id} ({t.get('ticker')}) has NULL "
            f"target or spot — skipping outcome row "
            f"(target={t.get('thesis_target')}, spot={t.get('spot_at_run')})",
            file=sys.stderr,
        )
        return False

    row = {
        "thesis_id": t["id"],
        "ticker": t["ticker"],
        "thesis_date": t["run_at"],
        "thesis_target": float(t["thesis_target"]),
        "spot_at_run": float(t["spot_at_run"]),
        "conviction": t.get("conviction"),
        "position_size_pct": t.get("position_size_pct"),
    }
    try:
        sb.table("thesis_outcomes").insert(row).execute()
        return True
    except Exception as e:
        print(f"  [outcomes] insert failed for thesis_id={thesis_id}: {e}", file=sys.stderr)
        return False


def _trading_close_on_or_after(ticker: str, target_date: date,
                                window_days: int = 7) -> tuple[Optional[float], Optional[date]]:
    """Return (close_price, actual_date) — first trading-day close on or
    after target_date within window_days. None if no data."""
    try:
        start = target_date.isoformat()
        end = (target_date + timedelta(days=window_days)).isoformat()
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
        if hist is None or hist.empty:
            return None, None
        row = hist.iloc[0]
        close = float(row["Close"]) if "Close" in row.index else None
        idx_date = hist.index[0].date()
        return close, idx_date
    except Exception as e:
        print(f"  [outcomes] yfinance threw on {ticker} @ {target_date}: {e}", file=sys.stderr)
        return None, None


def refresh_outcomes(verbose: bool = True) -> dict:
    """Iterate all thesis_outcomes rows; fill in *_t30/*_t90/*_t180 cells
    for theses where the time window has elapsed AND the cell is currently NULL.

    Returns summary counts.
    """
    sb = _get_client()
    all_rows = sb.table("thesis_outcomes").select("*").execute()
    rows = all_rows.data or []

    today = datetime.now(timezone.utc).date()
    summary = {"checked": len(rows), "t30_filled": 0, "t90_filled": 0, "t180_filled": 0,
               "skipped_too_recent": 0, "yfinance_misses": 0}

    for r in rows:
        outcome_id = r["id"]            # UUID PK — never null, safe to update by
        thesis_id = r.get("thesis_id")  # nullable after ON DELETE SET NULL
        ticker = r["ticker"]
        thesis_date = r["thesis_date"]
        # Robust date extraction: Supabase returns ISO timestamps with variable
        # fractional-second precision (5 digits), which Python 3.10
        # datetime.fromisoformat rejects. We only need the date, so slice.
        if isinstance(thesis_date, str):
            thesis_d = date.fromisoformat(thesis_date[:10])
        elif isinstance(thesis_date, datetime):
            thesis_d = thesis_date.date()
        else:
            thesis_d = thesis_date
        spot = r["spot_at_run"]
        target = r["thesis_target"]

        updates: dict = {}

        for label, days in (("t30", 30), ("t90", 90), ("t180", 180)):
            cell_price = r.get(f"price_{label}")
            if cell_price is not None:
                continue  # already filled
            target_date = thesis_d + timedelta(days=days)
            if target_date > today:
                summary["skipped_too_recent"] += 1
                continue
            price, actual = _trading_close_on_or_after(ticker, target_date)
            if price is None:
                summary["yfinance_misses"] += 1
                continue
            updates[f"price_{label}"] = price
            updates[f"price_{label}_date"] = actual.isoformat() if actual else None
            if spot and spot > 0:
                updates[f"return_{label}_pct"] = (price / spot - 1.0) * 100.0
            summary[f"{label}_filled"] += 1

        # thesis_progress_pct_t30/t90/t180 are GENERATED columns in the DB
        # (post 2026-05-05_thesis_outcomes_fixes.sql migration). They auto-recompute
        # whenever price_t30/t90/t180 are written. Don't set them from Python —
        # Postgres will reject writes to GENERATED ALWAYS columns.

        if updates:
            updates["last_refreshed"] = datetime.now(timezone.utc).isoformat()
            try:
                # Update by UUID id, NOT thesis_id. After ON DELETE SET NULL,
                # thesis_id can be NULL on orphaned outcome rows; PostgREST
                # `.eq("thesis_id", None)` won't match NULL, so those rows
                # would never refresh. id is the immutable UUID PK.
                sb.table("thesis_outcomes").update(updates).eq("id", outcome_id).execute()
                if verbose:
                    filled = ", ".join(k.replace("price_", "") for k in updates if k.startswith("price_") and not k.endswith("_date"))
                    print(f"  [{ticker}] outcome_id={outcome_id} thesis_id={thesis_id} filled: {filled}")
            except Exception as e:
                print(f"  [outcomes] update failed for {ticker} outcome_id={outcome_id}: {e}", file=sys.stderr)

    return summary


def backfill_from_theses() -> dict:
    """Create thesis_outcomes rows for every theses row that doesn't have one yet.

    Use this once to seed the table from existing thesis history. Idempotent.
    """
    sb = _get_client()
    th_rows = sb.table("theses").select("id").execute().data or []
    existing = {r["thesis_id"] for r in (sb.table("thesis_outcomes").select("thesis_id").execute().data or [])}
    summary = {"theses_total": len(th_rows), "already_exist": 0, "created": 0, "skipped_no_target": 0}
    for t in th_rows:
        if t["id"] in existing:
            summary["already_exist"] += 1
            continue
        if log_thesis_outcome(t["id"]):
            summary["created"] += 1
        else:
            summary["skipped_no_target"] += 1
    return summary


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    from utils import load_env
    load_env()
    print("=" * 60)
    print("  OUTCOMES — backfill + refresh")
    print("=" * 60)
    bf = backfill_from_theses()
    print(f"  backfill: {bf}")
    rf = refresh_outcomes()
    print(f"  refresh:  {rf}")
