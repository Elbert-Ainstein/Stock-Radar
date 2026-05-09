#!/usr/bin/env python3
"""
convergence_detector.py - Module 11a: Cross-source convergence scoring.

Per the Tier 1 dashboard design (option D from tier1_dashboard_design_briefing.md):
a candidate that surfaced from MULTIPLE INDEPENDENT discovery sources gets
priority over single-source candidates. The smartest-friend × smartest-friend
× smartest-friend filter — three independent processes flagging the same
ticker is far stronger evidence than one process flagging it three times.

Inputs (current — Module 11a):
  - discovery_universe.source: comma-separated string of source tags. 13F
    manager filings accumulate here as e.g.
    "13f_druckenmiller_2025q4_new_position, 13f_coatue_2025q4_significant_add".
  - discovery_universe.cheap_score: Haiku-graded 0-10 score from cheap_scan.
  - discovery_universe.status: "exploring" / "promising" / etc.

Inputs deferred to Module 11b (KNOWN LIMITATIONS):
  - Insider buying scout output is in `signals` table only; no feeder yet
    populates discovery_universe with `source="insider_buying"`.
  - News scout output is in `signals` table only; no feeder yet.
  - Theme scan output doesn't exist yet at all.
  Once those feeders exist, this detector will read them automatically — the
  query is source-agnostic, it just counts distinct source tags.

Output:
  - Top-N tickers by `convergence_score = independent_source_count`,
    tie-broken by cheap_score (higher first), then by alpha ticker.
  - Each row includes: ticker, source_count, sources, cheap_score, status.
  - JSON dumped to data/convergence/<run_at>.json for dashboard consumption.
  - Tier classification: STRONG (>=3 sources), MEDIUM (2 sources), SINGLE (1).

The score function deliberately treats EACH UNIQUE SOURCE TAG as one
independent vote, even multiple 13F managers — three managers buying ENTG
(per the project memory) is genuinely three independent votes from different
funds, even though they're all "13f" type. We could later add a vote-weight
adjustment that down-weights same-type sources, but the squad red-team will
need to evaluate that against the 'three managers' real signal.
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

# Force UTF-8 stdout on Windows
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

REPO_ROOT = HERE.parent
OUTPUT_DIR = REPO_ROOT / "data" / "convergence"


def _split_source_tags(source_str: str | None) -> list[str]:
    """Parse the comma-separated source field into a list of tags.

    Handles: None, "", "a", "a, b", "a, b ,c". Preserves order, drops
    duplicates (rare but defensive — e.g., a manager appearing twice should
    only count once).
    """
    if not source_str:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in source_str.split(","):
        tag = raw.strip()
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


# Source-class taxonomy — each prefix maps to one independent signal class.
# Convergence is now scored on distinct CLASSES, not raw tag count, so that
# news_bullish + news_earnings_beat (both from the news scout) are one class
# vote, not two. The squad review on 11b round 1 caught this double-count.
SOURCE_CLASS_MAP = (
    ("13f_", "smart_money"),
    ("insider_", "insider"),
    ("news_", "news"),
    ("theme_", "theme"),
    ("yahoo_", "momentum"),
    ("watchlist_seed", "manual"),
)


def _tag_to_class(tag: str) -> str:
    """Map a source tag like `13f_druckenmiller_2025Q4_new_position` to its class.
    Returns 'unknown' if no prefix matches — those still count as one class
    each so we don't silently drop new signal types when they're added."""
    t = tag.strip().lower()
    for prefix, cls in SOURCE_CLASS_MAP:
        if t.startswith(prefix):
            return cls
    return f"other:{t[:20]}"


def _classify_tier(class_count: int) -> str:
    """Tier from CLASS count, not raw tag count. STRONG = 3+ independent
    signal classes (e.g., smart_money + insider + news). MEDIUM = 2 classes.
    SINGLE = 1 class regardless of how many tags within that class fired."""
    if class_count >= 3:
        return "STRONG"
    if class_count == 2:
        return "MEDIUM"
    if class_count == 1:
        return "SINGLE"
    return "EMPTY"


def detect_convergence(
    *,
    status_filter: list[str] | None = None,
    min_sources: int = 1,
    top_n: int | None = None,
) -> list[dict]:
    """Score discovery_universe rows by independent-source convergence.

    Args:
      status_filter: only consider rows with status in this list. Default:
        ["exploring", "promising", "qualified"]. The dashboard shouldn't
        re-surface "killed" or "watching" tickers via convergence — those
        had their decision made.
      min_sources: minimum source count to include. 1 returns everything;
        2 hides single-source noise.
      top_n: cap on returned rows. None = unlimited.

    Returns: list of dicts ordered by score desc.
    """
    from supabase_helper import get_client

    sb = get_client()
    if status_filter is None:
        status_filter = ["exploring", "promising", "qualified"]

    q = sb.table("discovery_universe").select(
        "ticker,source,status,cheap_score,first_seen,last_scanned,market,sector"
    ).in_("status", status_filter)
    rows = q.execute().data or []

    scored: list[dict] = []
    for r in rows:
        tags = _split_source_tags(r.get("source"))
        classes = sorted({_tag_to_class(t) for t in tags})
        n_tags = len(tags)
        n_classes = len(classes)
        # min_sources is a CLASS threshold post-fix — interface unchanged.
        if n_classes < min_sources:
            continue
        scored.append({
            "ticker": r["ticker"],
            "source_count": n_tags,         # raw tag count (transparency)
            "class_count": n_classes,       # independent signal classes
            "classes": classes,
            "sources": tags,
            "tier": _classify_tier(n_classes),
            "cheap_score": r.get("cheap_score"),
            "status": r.get("status"),
            "market": r.get("market"),
            "sector": r.get("sector"),
            "first_seen": r.get("first_seen"),
            "last_scanned": r.get("last_scanned"),
        })

    # Sort: source_count desc, then cheap_score desc (None sinks),
    # then ticker asc for stability.
    def sort_key(d: dict) -> tuple:
        cs = d.get("cheap_score")
        return (
            -d["class_count"],            # primary: independent signal classes (tier)
            -(cs if cs is not None else -1),  # secondary: cheap_score (highest first)
            -d["source_count"],           # tiebreak: more confirming tags within tier
            d["ticker"],
        )

    scored.sort(key=sort_key)
    if top_n is not None:
        scored = scored[:top_n]
    return scored


def write_run_artifact(rows: list[dict], run_at: datetime) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"convergence_{run_at.strftime('%Y%m%d_%H%M%S')}.json"
    out_path = OUTPUT_DIR / fname
    payload = {
        "run_at": run_at.isoformat(),
        "row_count": len(rows),
        "tier_counts": {
            "STRONG": sum(1 for r in rows if r["tier"] == "STRONG"),
            "MEDIUM": sum(1 for r in rows if r["tier"] == "MEDIUM"),
            "SINGLE": sum(1 for r in rows if r["tier"] == "SINGLE"),
        },
        "rows": rows,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-sources", type=int, default=1,
                        help="Minimum independent CLASS count (default 1). Class taxonomy: "
                             "smart_money / insider / news / momentum / theme / manual.")
    parser.add_argument("--top", type=int, default=50,
                        help="Cap on returned rows (default 50)")
    parser.add_argument("--status", default="exploring,promising,qualified",
                        help="Comma-separated discovery_universe statuses to include")
    parser.add_argument("--no-write", action="store_true",
                        help="Print only; do not write JSON artifact")
    args = parser.parse_args()

    statuses = [s.strip() for s in args.status.split(",") if s.strip()]
    rows = detect_convergence(
        status_filter=statuses,
        min_sources=args.min_sources,
        top_n=args.top,
    )

    run_at = datetime.now(timezone.utc)
    tier_counts = {
        "STRONG": sum(1 for r in rows if r["tier"] == "STRONG"),
        "MEDIUM": sum(1 for r in rows if r["tier"] == "MEDIUM"),
        "SINGLE": sum(1 for r in rows if r["tier"] == "SINGLE"),
    }
    print(f"\n=== convergence detector — {run_at.strftime('%Y-%m-%d %H:%M:%S %Z')} ===")
    print(f"  rows returned: {len(rows)}")
    print(f"  STRONG (>=3 sources): {tier_counts['STRONG']}")
    print(f"  MEDIUM (2 sources):   {tier_counts['MEDIUM']}")
    print(f"  SINGLE (1 source):    {tier_counts['SINGLE']}")
    print()
    print(f"  {'TIER':<7} {'TICKER':<8} {'CLS':<3} {'TAGS':<4} {'CHEAP':<6} {'STATUS':<10} CLASSES")
    print(f"  {'-'*7} {'-'*8} {'-'*3} {'-'*4} {'-'*6} {'-'*10} {'-'*40}")
    for r in rows[:25]:
        cs = r.get("cheap_score")
        cs_str = f"{cs:.1f}" if cs is not None else "—"
        cls_str = ", ".join(r.get("classes") or [])
        print(f"  {r['tier']:<7} {r['ticker']:<8} {r['class_count']:<3} "
              f"{r['source_count']:<4} {cs_str:<6} {r['status']:<10} {cls_str[:55]}")

    if not args.no_write:
        out = write_run_artifact(rows, run_at)
        print(f"\n  wrote artifact → {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
