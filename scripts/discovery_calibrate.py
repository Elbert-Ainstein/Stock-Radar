#!/usr/bin/env python3
"""
discovery_calibrate.py - Calibration check for the cheap-scan scoring model.

Per the review-squad outsider: "Did anyone check whether this system would
have scored LITE, ALAB, ASML at 7+? If it can't recover names Hume already
trusts, why trust its new nominations?"

Reads the active watchlist from Supabase (stocks table), runs each through
the production cheap-scan prompt + Haiku (now augmented with yfinance's
longBusinessSummary to mitigate stale-knowledge errors like SNDK), prints
a score table and a PASS/PARTIAL/FAIL verdict.

Does NOT write to discovery_universe - calibration only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from utils import load_env  # noqa: E402
load_env()

# Reuse the existing scan worker functions verbatim - that's the point of
# calibration: we want to test the production prompt + inputs, not a variant.
from discovery_scan import (  # noqa: E402
    fetch_fundamentals,
    revenue_ttm_usd,
    build_prompt,
    call_haiku,
)
from scout_discovery import detect_market  # noqa: E402


def load_watchlist() -> list[dict]:
    """Load watchlist tickers from Supabase `stocks` table (active only).

    Falls back to config/watchlist.json if Supabase is unavailable.
    """
    try:
        from supabase_helper import get_client
        sb = get_client()
        resp = sb.table("stocks").select("ticker,name,sector,active").execute()
        rows = resp.data or []
        active = [r for r in rows if r.get("active", True) != False]
        return [{"ticker": r["ticker"], "name": r.get("name") or "",
                 "sector": r.get("sector") or ""} for r in active]
    except Exception as e:
        print(f"  [supabase] watchlist read failed: {e}; falling back to JSON",
              file=sys.stderr)
        repo_root = HERE.parent
        wl_path = repo_root / "config" / "watchlist.json"
        with open(wl_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("watchlist", [])


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Cheap-scan calibration check")
    p.add_argument("--tickers", default="",
                   help="Comma-separated tickers to score instead of watchlist (e.g. KO,JNJ,PG)")
    p.add_argument("--label", default="watchlist",
                   help="Label for this run (e.g. 'watchlist' or 'control-group')")
    args = p.parse_args()

    if args.tickers:
        ticker_list = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        watchlist = [{"ticker": t, "name": "", "sector": ""} for t in ticker_list]
    else:
        watchlist = load_watchlist()

    if not watchlist:
        print("ERROR: no watchlist entries", file=sys.stderr)
        return 1

    print("=" * 78)
    print(f"  DISCOVERY CALIBRATION ({args.label}) - {len(watchlist)} tickers")
    print(f"  Goal: do existing watchlist names score >=7 on the cheap-scan prompt?")
    print("=" * 78)
    print()

    fx_cache: dict[str, float] = {"USD": 1.0}
    results: list[dict] = []
    total_in_tokens = 0
    total_out_tokens = 0

    import yfinance as yf

    for entry in watchlist:
        ticker = entry["ticker"]
        market = detect_market(ticker)
        wl_name = entry.get("name", "")
        wl_sector = entry.get("sector", "")

        sys.stdout.write(f"  [{ticker:<10}] fetching... ")
        sys.stdout.flush()

        fund = fetch_fundamentals(ticker)
        if fund is None:
            print("SKIP (fundamentals fetch failed)")
            results.append({
                "ticker": ticker, "market": market, "score": None,
                "verdict": "fundamentals fetch failed", "name": wl_name,
            })
            continue

        rev_usd = revenue_ttm_usd(ticker, fund, fx_cache)

        # Pull longBusinessSummary to mitigate Haiku's stale corporate-history
        # knowledge (e.g. SNDK was acquired in 2016 and re-listed in 2025).
        try:
            info = yf.Ticker(ticker).info or {}
            biz = (info.get("longBusinessSummary") or "")[:500]
        except Exception:
            biz = ""

        row = {
            "ticker": ticker,
            "market": market,
            "company_name": fund.get("name") or wl_name or ticker,
            "sector": fund.get("sector") or wl_sector or "Unknown",
            "currency": fund.get("currency") or "USD",
            "market_cap_usd": None,
        }

        news_line = f"Business description (current):\n{biz}" if biz else ""
        prompt = build_prompt(row, fund, rev_usd, news_headline=news_line)

        sys.stdout.write("calling Haiku... ")
        sys.stdout.flush()
        try:
            parsed, in_tok, out_tok = call_haiku(prompt)
        except Exception as e:
            print(f"FAIL ({e})")
            results.append({
                "ticker": ticker, "market": market, "score": None,
                "verdict": f"haiku failed: {e}", "name": row["company_name"],
            })
            continue

        total_in_tokens += in_tok
        total_out_tokens += out_tok
        score = parsed.get("score")
        verdict = parsed.get("verdict") or "(no verdict)"
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None

        score_str = f"{score_f:.1f}" if score_f is not None else "??"
        print(f"score={score_str}")

        results.append({
            "ticker": ticker, "market": market,
            "score": score_f, "verdict": verdict,
            "name": row["company_name"],
        })

    # Save full results to disk so they survive the bash timeout cutoff
    out_path = Path("/tmp/calibration_results.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n  [saved] full results to {out_path}")
    except Exception:
        pass

    # Summary
    print()
    print("=" * 78)
    print("  RESULTS")
    print("=" * 78)
    print(f"  {'TICKER':<10} {'MKT':<4} {'SCORE':<6} {'NAME':<28} VERDICT")
    print(f"  {'-'*10} {'-'*4} {'-'*6} {'-'*28} {'-'*30}")
    for r in results:
        score_str = f"{r['score']:.1f}" if r["score"] is not None else "-"
        name = (r.get("name") or "")[:28]
        verdict = (r.get("verdict") or "")[:80]
        print(f"  {r['ticker']:<10} {r['market']:<4} {score_str:<6} {name:<28} {verdict}")

    scored = [r["score"] for r in results if r["score"] is not None]
    if scored:
        print()
        print("=" * 78)
        print("  DISTRIBUTION")
        print("=" * 78)
        print(f"  N scored: {len(scored)}/{len(results)}")
        print(f"  mean: {sum(scored)/len(scored):.2f}, median: {sorted(scored)[len(scored)//2]:.1f}, "
              f"min: {min(scored):.1f}, max: {max(scored):.1f}")
        below4 = sum(1 for s in scored if s < 4)
        mid    = sum(1 for s in scored if 4 <= s < 7)
        prom   = sum(1 for s in scored if s >= 7)
        print(f"  <4 (would be dropped):     {below4}/{len(scored)}")
        print(f"  4-6 (exploring):           {mid}/{len(scored)}")
        print(f"  7+ (would be promising):   {prom}/{len(scored)}")

    cost_in = total_in_tokens / 1_000_000 * 1.00
    cost_out = total_out_tokens / 1_000_000 * 5.00
    cost_out = total_out_tokens / 1_000_000 * 5.00
    print()
    print(f"  tokens: in={total_in_tokens}, out={total_out_tokens}, est cost=${cost_in+cost_out:.4f}")

    print()
    if scored:
        prom = sum(1 for s in scored if s >= 7)
        if prom >= len(scored) * 0.5:
            v = "PASS - majority scored 7+. Scoring has baseline signal."
        elif prom >= len(scored) * 0.25:
            v = "PARTIAL - some names scored 7+. Useful but inconsistent."
        else:
            v = "FAIL - <25% scored 7+."
        print(f"  CALIBRATION: {v}")
    else:
        print("  CALIBRATION: NO DATA")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
