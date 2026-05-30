#!/usr/bin/env python3
"""run_judgment.py — Phase 5 MVP: record a bet from a Socratic analysis.

The conversational judgment card from BUILD_PLAN_v2 §Phase 5 is split into
two pieces. This MVP is the bet-write half — takes structured input from the
CLI, validates, computes T+30/60/90 dates, and writes a row to the `bets`
table. The AI-conversational follow-up half (Phase 5.2 increment, when the
frontend is ready) will use `prompts/socratic/judgment_conversation.md` to
detect vague input and ask one clarifying question — that prompt is already
in the library, just not invoked from here yet.

Usage:
    python scripts/run_judgment.py LITE \\
        --judgment "Scale in 5% now at $970; add another 5% if it pulls back to $700 after Coherent 200G EML demo confirmed." \\
        --falsification "Coherent ships 200G D-EML in volume to a tier-1 hyperscaler before LITE's next earnings (Aug 2026), OR LITE Q4 FY2026 revenue misses guide by >10%." \\
        --position-pct 5

Pass criterion (Phase 5.3):
  - bets row appears with all required fields
  - falsification is non-null (DB-level CHECK enforces this)
  - t30 / t60 / t90 dates computed from entry_date
  - linked to the latest socratic_analyses row via socratic_id
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env
load_env()

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _get_sb_client():
    try:
        from supabase_helper import get_client
        return get_client()
    except ImportError:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SECRET_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY not set")
        return create_client(url, key)


def latest_socratic_for_ticker(ticker: str) -> Optional[dict]:
    """Pull the most recent socratic_analyses row for this ticker."""
    sb = _get_sb_client()
    result = (
        sb.table("socratic_analyses")
        .select("id, ticker, run_at, mode, spot_at_run, rough_target_low, rough_target_high, downside_price")
        .eq("ticker", ticker.upper())
        .order("run_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


def compute_checkpoint_dates(entry_date: datetime) -> dict:
    """Compute T+30 / T+60 / T+90 date strings (date-only, calendar days)."""
    base = entry_date.date()
    return {
        "t30_date": (base + timedelta(days=30)).isoformat(),
        "t60_date": (base + timedelta(days=60)).isoformat(),
        "t90_date": (base + timedelta(days=90)).isoformat(),
    }


def write_bet(
    ticker: str,
    *,
    entry_price: float,
    position_pct: float,
    judgment_text: str,
    falsification: str,
    target_low: Optional[float],
    target_high: Optional[float],
    downside_price: Optional[float],
    socratic_id: Optional[int],
    judgment_mode: str = "custom",
) -> int:
    """Insert a bets row. Returns bet id. Raises on any DB error or RLS empty-return."""
    sb = _get_sb_client()
    entry_date = datetime.now(timezone.utc)
    checkpoints = compute_checkpoint_dates(entry_date)

    row = {
        "ticker": ticker.upper(),
        "socratic_id": socratic_id,
        "entry_price": entry_price,
        "entry_date": entry_date.isoformat(),
        "target_low": target_low,
        "target_high": target_high,
        "downside_price": downside_price,
        "position_pct": position_pct,
        "judgment_text": judgment_text,
        "falsification": falsification,
        "judgment_mode": judgment_mode,
        "status": "active",
        **checkpoints,
    }

    result = sb.table("bets").insert(row).execute()
    if not result.data:
        raise RuntimeError(
            "bets insert returned empty data — likely RLS denies SELECT on the inserted "
            "row, or the migration hasn't been applied. Check Supabase logs."
        )
    return result.data[0]["id"]


def write_chat_history_entry(ticker: str, judgment_text: str, falsification: str, bet_id: int) -> None:
    """Best-effort log of the judgment into chat_history. Failures don't abort."""
    try:
        import uuid
        sb = _get_sb_client()
        session_id = str(uuid.uuid4())
        rows = [
            {
                "session_id": session_id,
                "role": "user",
                "content": f"Judgment: {judgment_text}\nFalsification: {falsification}",
                "mode": "judgment_card",
                "ticker": ticker.upper(),
            },
            {
                "session_id": session_id,
                "role": "system",
                "content": f"Bet recorded as id={bet_id}, position={ticker} (judgment_card MVP)",
                "mode": "judgment_card",
                "ticker": ticker.upper(),
            },
        ]
        sb.table("chat_history").insert(rows).execute()
    except Exception as e:
        print(f"  [chat_history] WARN: log skipped — {e}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 5 MVP — record a bet from a Socratic analysis."
    )
    parser.add_argument("ticker", help="Ticker symbol, e.g. LITE")
    parser.add_argument("--judgment", required=True, help="The user's judgment text. Must be specific (action + price/trigger + size).")
    parser.add_argument("--falsification", required=True, help="The user's falsification condition. Specific event that would prove the bet wrong. REQUIRED.")
    parser.add_argument(
        "--position-pct", type=float, default=5.0,
        help="Position size as percent of portfolio. Default 5%% (per user_position_sizing_discipline — first-touch signals start at 5%%).",
    )
    parser.add_argument("--entry-price", type=float, default=None, help="Entry price override. Default = spot_at_run from latest Socratic analysis.")
    parser.add_argument("--socratic-id", type=int, default=None, help="Specific socratic_analyses.id to link this bet to. Default = latest for ticker.")
    parser.add_argument("--no-chat-log", action="store_true", help="Skip the chat_history audit-trail write.")
    args = parser.parse_args()

    ticker = args.ticker.upper()

    # Validate non-empty (DB CHECK constraint will also catch falsification, but we want
    # a friendlier error here than a 23514 from Postgres).
    if not args.judgment.strip():
        print("ERROR: --judgment must be non-empty", file=sys.stderr)
        sys.exit(2)
    if not args.falsification.strip():
        print("ERROR: --falsification must be non-empty. Every bet must be falsifiable.", file=sys.stderr)
        sys.exit(2)
    if args.position_pct < 0 or args.position_pct > 100:
        print(f"ERROR: --position-pct must be in [0, 100], got {args.position_pct}", file=sys.stderr)
        sys.exit(2)
    # position_pct = 0 is a valid "pass" decision — still tracked with
    # falsification so the system can settle whether the pass was right.

    # Resolve socratic context
    soc = None
    if args.socratic_id is not None:
        sb = _get_sb_client()
        r = sb.table("socratic_analyses").select("*").eq("id", args.socratic_id).limit(1).execute()
        soc = r.data[0] if r.data else None
        if soc is None:
            print(f"ERROR: --socratic-id {args.socratic_id} not found", file=sys.stderr)
            sys.exit(3)
    else:
        soc = latest_socratic_for_ticker(ticker)
        if soc is None:
            print(
                f"WARN: no socratic_analyses row found for {ticker}. Bet will be written without "
                f"socratic_id link. Consider running `python scripts/run_socratic.py {ticker}` first.",
                file=sys.stderr,
            )

    # Resolve entry price
    if args.entry_price is not None:
        entry_price = args.entry_price
        print(f"  entry_price (CLI override): ${entry_price:.2f}", flush=True)
    elif soc and soc.get("spot_at_run"):
        entry_price = float(soc["spot_at_run"])
        print(f"  entry_price (from socratic spot_at_run): ${entry_price:.2f}", flush=True)
    else:
        print("ERROR: --entry-price not given and no spot available from Socratic. Aborting.", file=sys.stderr)
        sys.exit(4)

    target_low = float(soc["rough_target_low"]) if soc and soc.get("rough_target_low") is not None else None
    target_high = float(soc["rough_target_high"]) if soc and soc.get("rough_target_high") is not None else None
    downside = float(soc["downside_price"]) if soc and soc.get("downside_price") is not None else None
    socratic_id = soc["id"] if soc else None

    print(f"\n=== record bet: {ticker} ===", flush=True)
    print(f"  socratic_id: {socratic_id}  (mode={soc.get('mode') if soc else 'n/a'})", flush=True)
    print(f"  position_pct: {args.position_pct}%", flush=True)
    if target_low is not None:
        print(f"  rough target range: ${target_low}-${target_high}  downside: ${downside}", flush=True)
    else:
        print("  (no rough_target_range on linked Socratic — bet will store nulls for target_low/high/downside)", flush=True)

    try:
        bet_id = write_bet(
            ticker,
            entry_price=entry_price,
            position_pct=args.position_pct,
            judgment_text=args.judgment,
            falsification=args.falsification,
            target_low=target_low,
            target_high=target_high,
            downside_price=downside,
            socratic_id=socratic_id,
            judgment_mode="custom",
        )
    except Exception as e:
        print(f"ERROR: bet write failed — {e}", file=sys.stderr)
        sys.exit(5)

    print(f"  ✓ bet id={bet_id} recorded", flush=True)
    print(f"  t30: {(datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()}", flush=True)
    print(f"  t60: {(datetime.now(timezone.utc).date() + timedelta(days=60)).isoformat()}", flush=True)
    print(f"  t90: {(datetime.now(timezone.utc).date() + timedelta(days=90)).isoformat()}", flush=True)

    if not args.no_chat_log:
        write_chat_history_entry(ticker, args.judgment, args.falsification, bet_id)


if __name__ == "__main__":
    main()
