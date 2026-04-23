#!/usr/bin/env python3
"""
One-shot fix: Update LITE's guided_op_margin from 30% to 40% in Supabase signals.

LITE's actual guided non-GAAP operating margin target is ~40%, but the
fundamentals scout scraped 30% from an older source. This script patches the
signal data directly so the forward_drivers pipeline picks up the correct value
on the next engine run.

Usage:
    python scripts/fix_lite_op_margin.py          # dry-run (default)
    python scripts/fix_lite_op_margin.py --apply  # actually update
"""
from __future__ import annotations
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_env
load_env()
from supabase_helper import get_client

TICKER = "LITE"
OLD_MARGIN_MAX = 35  # anything at or below this is wrong (actual is ~40%)
NEW_MARGIN = 40      # percent — LITE's guided non-GAAP op margin
DRY_RUN = "--apply" not in sys.argv


def main():
    sb = get_client()
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    print(f"\n  [{mode}] Fixing LITE guided_op_margin: anything ≤{OLD_MARGIN_MAX}% → {NEW_MARGIN}%\n")

    # Find fundamentals signals for LITE that contain guided_op_margin_pct
    resp = sb.table("signals") \
        .select("id, ticker, scout, data, created_at") \
        .eq("ticker", TICKER) \
        .in_("scout", ["fundamentals", "news"]) \
        .order("created_at", desc=True) \
        .limit(20) \
        .execute()

    updated = 0
    for row in resp.data or []:
        data = row.get("data") or {}
        # Check nested structures — the guided_op_margin_pct might be in
        # data.analysis.forward_guidance or data.forward_guidance
        locations = [
            data,
            data.get("analysis", {}),
            data.get("analysis", {}).get("forward_guidance", {}),
            data.get("forward_guidance", {}),
        ]

        found = False
        for loc in locations:
            if isinstance(loc, dict) and "guided_op_margin_pct" in loc:
                current = loc["guided_op_margin_pct"]
                if isinstance(current, (int, float)) and current <= OLD_MARGIN_MAX:
                    found = True
                    print(f"  Found: signal {row['id']} ({row['scout']}, {row['created_at']})")
                    print(f"    guided_op_margin_pct: {current} → {NEW_MARGIN}")
                    loc["guided_op_margin_pct"] = NEW_MARGIN

        if found:
            if not DRY_RUN:
                sb.table("signals").update({"data": data}).eq("id", row["id"]).execute()
                print(f"    ✓ Updated in Supabase")
            else:
                print(f"    (would update — run with --apply to commit)")
            updated += 1

    if updated == 0:
        print(f"  No signals found with guided_op_margin_pct ≤ {OLD_MARGIN_MAX} for {TICKER}")
        print(f"  The margin may already be correct, or stored differently.")
        print(f"\n  Checking current values...")
        for row in (resp.data or [])[:5]:
            data = row.get("data") or {}
            for path_name, loc in [
                ("data", data),
                ("data.analysis.forward_guidance", data.get("analysis", {}).get("forward_guidance", {})),
                ("data.forward_guidance", data.get("forward_guidance", {})),
            ]:
                if isinstance(loc, dict) and "guided_op_margin_pct" in loc:
                    print(f"    signal {row['id']} ({row['scout']}): {path_name}.guided_op_margin_pct = {loc['guided_op_margin_pct']}")
    else:
        print(f"\n  {updated} signal(s) {'would be updated' if DRY_RUN else 'updated'}.")
        if DRY_RUN:
            print(f"  Run with --apply to commit changes.")


if __name__ == "__main__":
    main()
