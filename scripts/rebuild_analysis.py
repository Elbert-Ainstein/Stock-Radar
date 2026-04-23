#!/usr/bin/env python3
"""
rebuild_analysis.py — One-shot: recompute `analysis` rows from signals
that already live in Supabase, without re-running any scouts.

Use this when:
  - The analyst's save silently failed (e.g. schema drift) and the dashboard
    is stuck on stale analysis rows, but scouts HAVE written fresh signals.
  - You don't want to wait for a full pipeline rerun (~15 min).

Reads from Supabase `latest_signals` (the DB is the source of truth) and
reuses analyst.analyze_stock() so scoring logic stays in one place.

Usage:
    python scripts/rebuild_analysis.py
    python scripts/rebuild_analysis.py --ticker MU    # single stock
"""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from utils import load_env, set_run_id, get_watchlist
load_env()

from supabase_helper import get_client
from analyst import analyze_stock, _save_analysis_to_supabase

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROGRESS_FILE = DATA_DIR / ".rebuild-progress"


def _write_progress(stage: str, message: str, current: int, total: int):
    """Write rebuild progress for dashboard polling."""
    pct = round(current / total * 100) if total > 0 else 0
    progress = {"stage": stage, "message": message, "current": current, "total": total, "percent": pct}
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PROGRESS_FILE.write_text(json.dumps(progress), encoding="utf-8")
    except Exception as e:
        print(f"  [progress] could not write {PROGRESS_FILE.name}: {e}")


def _clear_progress():
    try:
        PROGRESS_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _group_signals_as_scout_data(signal_rows: list[dict]) -> dict:
    """Shape latest_signals rows into the dict analyst.analyze_stock expects:
        {scout_name: {"signals": [...]}, ...}

    The stored signal row already has scout, ticker, signal, summary, data —
    we just reattach it under the scout key (with scout name capitalized the
    way analyst.analyze_stock looks up factors).
    """
    # analyst.analyze_stock uses `s.get("scout") == "Quant"` etc. (capitalized).
    # latest_signals rows may have lowercased scout names. Normalize to match.
    name_map = {
        "quant": "Quant",
        "insider": "Insider",
        "news": "News",
        "social": "Social",
        "youtube": "YouTube",
        "fundamentals": "Fundamentals",
    }

    scouts: dict[str, dict] = {}
    for row in signal_rows:
        scout_raw = (row.get("scout") or "").lower()
        canonical = name_map.get(scout_raw, scout_raw.capitalize())
        key = scout_raw  # analyst indexes `all_scouts` by lowercased name
        bucket = scouts.setdefault(key, {"signals": []})
        bucket["signals"].append({
            "ticker": row.get("ticker"),
            "scout": canonical,
            "signal": row.get("signal"),
            "summary": row.get("summary") or "",
            "data": row.get("data") or {},
            "scores": row.get("scores") or {},
            "ai": row.get("ai") or "",
            "timestamp": row.get("created_at") or "",
        })
    return scouts


def main():
    single_ticker = None
    if "--ticker" in sys.argv:
        i = sys.argv.index("--ticker")
        if i + 1 < len(sys.argv):
            single_ticker = sys.argv[i + 1].upper()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_rebuild_" + uuid.uuid4().hex[:4]
    set_run_id(run_id)

    sb = get_client()
    wl = get_watchlist()
    if single_ticker:
        wl = [w for w in wl if w["ticker"] == single_ticker]
        if not wl:
            print(f"[rebuild] {single_ticker} not in active watchlist — aborting")
            return

    total_stocks = len(wl)
    print("=" * 60)
    print(f"REBUILD ANALYSIS from Supabase signals — run {run_id}")
    print(f"Stocks: {[w['ticker'] for w in wl]}")
    print("=" * 60)

    _write_progress("loading", f"Loading signals for {total_stocks} stocks...", 0, total_stocks + 1)

    # Pull every latest signal in one shot (faster than N round-trips)
    all_rows = sb.table("latest_signals").select("*").execute().data or []
    by_ticker: dict[str, list[dict]] = {}
    for r in all_rows:
        by_ticker.setdefault(r["ticker"], []).append(r)

    results = []
    saved_count = 0
    for idx, stock in enumerate(wl):
        ticker = stock["ticker"]
        name = stock.get("name") or ticker
        sector = stock.get("sector") or "Unknown"
        sig_rows = by_ticker.get(ticker, [])

        _write_progress("analyzing", f"Rebuilding {ticker} ({idx + 1}/{total_stocks})...", idx + 1, total_stocks + 1)

        if not sig_rows:
            print(f"\n  [{ticker}] no signals in Supabase — skipping")
            continue

        all_scouts = _group_signals_as_scout_data(sig_rows)
        signals = []
        for s_data in all_scouts.values():
            for sig in s_data["signals"]:
                if sig.get("ticker") == ticker:
                    signals.append(sig)

        print(f"\n  [{ticker}] {len(signals)} signals from {len(all_scouts)} scouts")
        try:
            result = analyze_stock(ticker, name, sector, signals, all_scouts)
            results.append(result)
            print(
                f"    score={result['composite_score']}  "
                f"sig={result['overall_signal']}  "
                f"price=${result['price_data']['price']}  "
                f"scores={result['scores']}"
            )
            # Save immediately per-stock so a crash on stock N doesn't lose
            # stocks 1..N-1 (was: batch save at end, total data loss on crash)
            _save_analysis_to_supabase([result], run_id, {})
            saved_count += 1
            print(f"  [DB] Saved {ticker} to Supabase (run: {run_id})")
        except Exception as e:
            print(f"    [FAIL] analyze_stock error: {e}")
            import traceback; traceback.print_exc()

    _write_progress("saving", f"Saved {saved_count} analysis rows to Supabase", total_stocks, total_stocks + 1)

    _write_progress("complete", f"Rebuild complete — {len(results)} stocks updated", total_stocks + 1, total_stocks + 1)
    print("\n" + "=" * 60)
    print(f"REBUILD COMPLETE — {len(results)} analysis rows written (run {run_id})")
    print("=" * 60)
    _clear_progress()
    return results


if __name__ == "__main__":
    main()
