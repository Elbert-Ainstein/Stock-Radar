"""
run_checkpoint.py — Stage 1 of the Async Checkpoint Feedback loop: the GRADER.

A separate, async, idempotent cron process. It reads sealed prediction records
(prediction_log), and for every record that has ripened to a horizon (T+30/60/90)
and isn't graded yet, it fetches the date-pinned close and writes an outcome to
prediction_outcomes. It NEVER mutates a seal and the main pipeline never waits on it.

Design (see docs/CHECKPOINT_FEEDBACK_ASSESSMENT_2026-06-01.md):
  - Read-only on prediction_log; append-only on prediction_outcomes.
  - Idempotent: the DB UNIQUE(prediction_id, days_elapsed) plus an explicit skip
    means re-running any day double-grades nothing.
  - Date-pinned: uses checkpoint_seal.close_on_or_after — never a wrong-day price.
  - Direction is scored band-midpoint vs ref_price (no extra field needed).
  - Stage 1 produces graded outcomes only; the [CALIBRATION] feedback into live
    analysis is Stage 4 and stays dark until N >= 10.

Usage:
    python run_checkpoint.py                 # grade everything ripe
    python run_checkpoint.py --ticker LITE   # one ticker
    python run_checkpoint.py --dry-run       # show what would grade, write nothing
    python run_checkpoint.py --horizons 30   # only T+30
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

# Load .env so the cron grader picks up SUPABASE_* without a shell export.
try:
    from utils import load_env as _load_env
    _load_env()
except Exception:
    pass

HORIZONS = (30, 60, 90)
DIR_EPS = 0.02  # ±2% dead-band around ref_price counts as "flat"


# ── Pure grading helpers (no IO; unit-tested) ──────────────────────────────────

def _mid(low: Optional[float], base: Optional[float], high: Optional[float]) -> Optional[float]:
    """Representative target: base if present, else midpoint of low/high."""
    if base is not None:
        return float(base)
    if low is not None and high is not None:
        return (float(low) + float(high)) / 2.0
    if high is not None:
        return float(high)
    if low is not None:
        return float(low)
    return None


def expected_direction(low, base, high, ref_price, eps: float = DIR_EPS) -> Optional[str]:
    """Thesis direction implied by the target band vs the sealed ref_price.

    'up' / 'down' / 'flat', or None if there isn't enough to say.
    """
    if ref_price in (None, 0):
        return None
    mid = _mid(low, base, high)
    if mid is None:
        return None
    rel = mid / float(ref_price) - 1.0
    if rel > eps:
        return "up"
    if rel < -eps:
        return "down"
    return "flat"


def directional_correct(expected: Optional[str], ref_price, actual, eps: float = DIR_EPS) -> Optional[bool]:
    """Did the stock actually move the way the thesis implied?"""
    if expected is None or ref_price in (None, 0) or actual is None:
        return None
    rel = float(actual) / float(ref_price) - 1.0
    actual_dir = "up" if rel > eps else "down" if rel < -eps else "flat"
    return actual_dir == expected


def band_label(actual, low, high) -> Optional[str]:
    """Where the actual price landed relative to the target band."""
    if actual is None:
        return None
    a = float(actual)
    if high is not None and a >= float(high):
        return "at/above high"
    if low is not None and a <= float(low):
        return "at/below low"
    if low is not None or high is not None:
        return "within band"
    return None


def return_pct(actual, ref_price) -> Optional[float]:
    if actual is None or ref_price in (None, 0):
        return None
    return round((float(actual) / float(ref_price) - 1.0) * 100.0, 2)


def grade(seal: dict, actual_price: float) -> dict:
    """Combine the helpers into a grade dict from a prediction_log row + actual price.

    Direction prefers the sealed models' lean (reasoning_fingerprint.directional_lean)
    — the honest thesis direction — and only falls back to the band midpoint when the
    models gave no clean lean (conflict) or the seal predates the field.
    """
    ref = seal.get("current_price")
    low, base, high = seal.get("target_low"), seal.get("target_base"), seal.get("target_high")
    fp = seal.get("reasoning_fingerprint") or {}
    lean = fp.get("directional_lean")
    exp = lean if lean in ("up", "down", "flat") else expected_direction(low, base, high, ref)
    return {
        "expected_direction": exp,
        "direction_source": "models" if lean in ("up", "down", "flat") else "band",
        "directional_correct": directional_correct(exp, ref, actual_price),
        "band": band_label(actual_price, low, high),
        "return_pct": return_pct(actual_price, ref),
    }


# ── Seal source/integrity filter (pure; 2026-07-02) ───────────────────────────

SEAL_RUN_PREFIX = "soc-"  # checkpoint_seal.seal_socratic_prediction stamps run_id "soc-<id>"


def is_gradeable_seal(row: dict) -> tuple[bool, str]:
    """Decide whether a prediction_log row is a genuine, gradeable Socratic seal.

    The legacy engine pipeline wrote snapshot rows into the same table with
    fabricated ±30% bands and — due to reading keys analyst.py never emits —
    all-zero targets and ref prices (audit 2026-07-02 §4.3). Grading those
    would poison prediction_outcomes, which is append-only by design.

    Returns (ok, reason). Reasons: ok | quarantined | not_socratic |
    zero_ref_price | no_target_band.
    """
    if row.get("quarantined"):
        return False, "quarantined"
    run_id = str(row.get("run_id") or "")
    fingerprint = row.get("reasoning_fingerprint") or {}
    # Socratic seals carry the soc- run prefix (base-schema column, survives
    # pre-migration column stripping); a non-empty reasoning_fingerprint also
    # qualifies (post-migration seals whose run_id used the run_at fallback).
    if not (run_id.startswith(SEAL_RUN_PREFIX) or fingerprint):
        return False, "not_socratic"
    ref = row.get("current_price")
    if ref in (None, 0) or float(ref) == 0.0:
        return False, "zero_ref_price"
    if all(row.get(k) in (None, 0) for k in ("target_low", "target_base", "target_high")):
        return False, "no_target_band"
    return True, "ok"


# ── Ripeness (pure) ────────────────────────────────────────────────────────────

def _parse_dt(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    try:
        s = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def ripe_horizons(sealed_at, today: date, horizons=HORIZONS) -> list[tuple[int, date]]:
    """Horizons whose target date (sealed_at + H) is on or before `today`.

    Returns [(H, target_date), ...]. Empty if sealed_at is unparseable.
    """
    dt = _parse_dt(sealed_at)
    if dt is None:
        return []
    seal_date = dt.date()
    out = []
    for h in horizons:
        target = seal_date + timedelta(days=h)
        if target <= today:
            out.append((h, target))
    return out


# ── IO: price fetch + DB ───────────────────────────────────────────────────────

def fetch_close_series(ticker: str, around: date) -> list[tuple[str, float]]:
    """Daily closes in a window bracketing `around`, as [(YYYY-MM-DD, close), ...]."""
    try:
        import yfinance as yf
    except ImportError:
        print("  [checkpoint] yfinance not installed: pip install yfinance", file=sys.stderr)
        return []
    try:
        start = (around - timedelta(days=4)).strftime("%Y-%m-%d")
        end = (around + timedelta(days=8)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, end=end)
        if hist.empty:
            return []
        return [(d.strftime("%Y-%m-%d"), float(c)) for d, c in zip(hist.index, hist["Close"])]
    except Exception as e:
        print(f"  [checkpoint] price fetch failed for {ticker} @ {around}: {e}", file=sys.stderr)
        return []


def _already_graded(sb, prediction_id, days_elapsed: int) -> bool:
    try:
        resp = (sb.table("prediction_outcomes").select("id")
                .eq("prediction_id", prediction_id).eq("days_elapsed", days_elapsed)
                .limit(1).execute())
        return bool(resp.data)
    except Exception:
        return False  # belt-and-suspenders; the DB UNIQUE constraint is the real guard


def _load_seals(sb, ticker: Optional[str]) -> list[dict]:
    base_cols = ("id,ticker,run_id,created_at,current_price,target_low,target_base,"
                 "target_high,archetype,cohort_key,reasoning_fingerprint")
    # Prefer to read the quarantine flag; fall back if the column predates the
    # 2026-07-02 consolidated migration (is_gradeable_seal treats absent as false).
    for cols in (base_cols + ",quarantined", base_cols):
        q = sb.table("prediction_log").select(cols).order("created_at", desc=True)
        if ticker:
            q = q.eq("ticker", ticker.upper())
        try:
            return q.execute().data or []
        except Exception as e:
            if "quarantined" in str(e) and "quarantined" in cols:
                continue  # pre-migration schema — retry without the flag
            raise
    return []


def run_checkpoint(*, dry_run: bool = False, ticker: Optional[str] = None,
                   horizons=HORIZONS, today: Optional[date] = None) -> dict:
    from checkpoint_seal import close_on_or_after
    from prediction_logger import record_price_outcome
    from supabase_helper import get_client

    today = today or datetime.now(timezone.utc).date()
    sb = get_client()
    rows = _load_seals(sb, ticker)
    seals: list[dict] = []
    excluded: dict[str, int] = {}
    for row in rows:
        ok, reason = is_gradeable_seal(row)
        if ok:
            seals.append(row)
        else:
            excluded[reason] = excluded.get(reason, 0) + 1
    print(f"[checkpoint] {len(rows)} row(s) loaded; grading {len(seals)} genuine seal(s); "
          f"excluded {excluded or 'none'} (today={today}, dry_run={dry_run})", flush=True)

    graded = skipped = no_price = 0
    for s in seals:
        ref = s.get("current_price")
        for h, target in ripe_horizons(s.get("created_at"), today, horizons):
            if _already_graded(sb, s["id"], h):
                skipped += 1
                continue
            series = fetch_close_series(s["ticker"], target)
            pick = close_on_or_after(series, target)
            if pick is None:
                no_price += 1
                print(f"  [{s['ticker']}] id={s['id']} T+{h}: no close on/after {target} — skip", flush=True)
                continue
            price, date_used = pick
            g = grade(s, price)
            tag = ("✓" if g["directional_correct"] else "✗") if g["directional_correct"] is not None else "·"
            print(f"  [{s['ticker']}] id={s['id']} T+{h} @ {date_used}: ${price:.2f} "
                  f"(ref ${ref}) {g['return_pct']:+}% dir={g['expected_direction']} {tag} band={g['band']}",
                  flush=True)
            if not dry_run:
                record_price_outcome(s["ticker"], s["id"], h, price, actual_date_used=date_used)
            graded += 1

    print(f"[checkpoint] done — graded={graded} skipped(existing)={skipped} no_price={no_price} "
          f"excluded={excluded or 'none'}", flush=True)
    return {"graded": graded, "skipped": skipped, "no_price": no_price, "excluded": excluded}


def main():
    ap = argparse.ArgumentParser(description="Grade ripe sealed predictions (Stage 1 checkpoint grader).")
    ap.add_argument("--ticker", help="Only grade this ticker")
    ap.add_argument("--dry-run", action="store_true", help="Show grades, write nothing")
    ap.add_argument("--horizons", help="Comma list, e.g. 30,60,90 (default all)")
    args = ap.parse_args()
    horizons = tuple(int(x) for x in args.horizons.split(",")) if args.horizons else HORIZONS
    run_checkpoint(dry_run=args.dry_run, ticker=args.ticker, horizons=horizons)


if __name__ == "__main__":
    main()
