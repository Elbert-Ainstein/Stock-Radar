#!/usr/bin/env python3
"""
ingest_scout_jsons.py — push scout JSON outputs into Supabase signals table.

Why this exists: when a scout runs standalone (e.g. `python scripts/scout_news.py
--source discovery`), `save_signals` falls through to a JSON-only write because
`get_run_id()` returns None outside the orchestrated pipeline. The data lands
in `data/{scout}_signals.json` but never reaches Supabase, so the feeders and
convergence detector never see it.

This script reads each `data/{scout}_signals.json` and inserts the rows into
Supabase with a synthetic run_id derived from the file's generated_at timestamp.
Idempotent — re-running with the same JSON produces the same run_id, so a
quick existence check skips already-ingested files.

Error code: SR-SCOUT-002 (scout output written to JSON only; ingest required).

Usage:
  python scripts/ingest_scout_jsons.py              # ingest all scout JSONs
  python scripts/ingest_scout_jsons.py --scout news # only news_signals.json
  python scripts/ingest_scout_jsons.py --dry-run    # show what would happen
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env  # noqa: E402

load_env()

DATA_DIR = HERE.parent / "data"


def _run_id_from_generated_at(generated_at: str, scout_name: str) -> str:
    """Build a stable, idempotent run_id from the JSON's timestamp.
    Format: 'standalone_YYYYMMDD_HHMMSS_<scout>' — distinguishes from
    orchestrated pipeline run_ids (which use a different prefix)."""
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)
    return f"standalone_{dt.strftime('%Y%m%d_%H%M%S')}_{scout_name}"


def ingest_one(json_path: Path, *, dry_run: bool = False) -> dict:
    if not json_path.exists():
        return {"path": str(json_path), "status": "missing"}
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    scout_name = payload.get("scout") or json_path.stem.replace("_signals", "")
    generated_at = payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
    signals = payload.get("signals") or []
    run_id = _run_id_from_generated_at(generated_at, scout_name)

    from supabase_helper import get_client
    sb = get_client()

    # Idempotency: if any row already has this run_id, skip — file was ingested before.
    existing = sb.table("signals").select("id").eq("run_id", run_id).limit(1).execute().data or []
    if existing:
        return {"path": str(json_path.name), "scout": scout_name, "run_id": run_id,
                "status": "already_ingested", "row_count": len(signals)}

    rows = []
    for sig in signals:
        rows.append({
            "ticker": sig["ticker"],
            "scout": (sig.get("scout") or scout_name).lower(),
            "signal": sig.get("signal", "neutral"),
            "ai": sig.get("ai", "Script"),
            "summary": sig.get("summary", "")[:2000],  # cap to avoid Supabase TEXT size issues
            "data": sig.get("data", {}),
            "scores": sig.get("scores", {}),
            "run_id": run_id,
        })

    if dry_run:
        return {"path": str(json_path.name), "scout": scout_name, "run_id": run_id,
                "status": "dry_run", "would_insert": len(rows)}

    if not rows:
        return {"path": str(json_path.name), "scout": scout_name, "run_id": run_id,
                "status": "no_rows", "inserted": 0}

    try:
        sb.table("signals").insert(rows).execute()
        return {"path": str(json_path.name), "scout": scout_name, "run_id": run_id,
                "status": "ok", "inserted": len(rows)}
    except Exception as e:
        return {"path": str(json_path.name), "scout": scout_name, "run_id": run_id,
                "status": "error", "error": str(e)[:300]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scout", help="Only ingest a specific scout (e.g. news, insider). "
                                        "Omit to ingest all *_signals.json files.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.scout:
        files = [DATA_DIR / f"{args.scout}_signals.json"]
    else:
        files = sorted(DATA_DIR.glob("*_signals.json"))

    if not files:
        print(f"  no JSON files found in {DATA_DIR}")
        return

    print(f"=== ingest_scout_jsons — {len(files)} file(s) ===")
    for f in files:
        result = ingest_one(f, dry_run=args.dry_run)
        # Pretty-print
        if result.get("status") == "ok":
            print(f"  OK    {result['path']:<32} scout={result['scout']:<10} "
                  f"inserted={result['inserted']:<4} run_id={result['run_id']}")
        elif result.get("status") == "already_ingested":
            print(f"  SKIP  {result['path']:<32} scout={result['scout']:<10} "
                  f"already ingested ({result['row_count']} rows in JSON)")
        elif result.get("status") == "dry_run":
            print(f"  DRY   {result['path']:<32} scout={result['scout']:<10} "
                  f"would_insert={result['would_insert']:<4} run_id={result['run_id']}")
        elif result.get("status") == "missing":
            print(f"  MISS  {result['path']} — file not found")
        else:
            print(f"  FAIL  {result.get('path')} — {result.get('status')}: {result.get('error', '')}")


if __name__ == "__main__":
    main()
