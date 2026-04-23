#!/usr/bin/env python3
"""
feedback_loop.py — Track signal outcomes and compute per-scout accuracy.

The feedback loop answers: "When scout X said bullish, was it actually right?"

Flow:
  1. evaluate_outcomes() — For each historical signal whose evaluation window
     has matured, look up the price at signal time and price now. Record whether
     the signal direction matched the actual price movement.
  2. compute_accuracy() — Aggregate outcomes into per-scout accuracy stats
     across 30d and 90d windows.
  3. get_adaptive_weights() — Return FACTOR_WEIGHTS adjusted by accuracy.

Usage:
    # During pipeline run:
    from feedback_loop import run_feedback_loop, get_adaptive_weights
    run_feedback_loop()                    # evaluate + aggregate
    weights = get_adaptive_weights()       # use in analyst.py

    # Standalone:
    python scripts/feedback_loop.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf

# ─── Path setup ───
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_env

load_env()

# ─── Supabase ───
from supabase_helper import get_client

# ─── Constants ───
EVAL_WINDOWS = [7, 30, 60, 90]  # days after signal to check

# ── Bayesian beta-binomial shrinkage ──
# Instead of a hard cutoff (the old MIN_SIGNALS_FOR_ADJUSTMENT = 20), we use
# Bayesian shrinkage: the observed accuracy is blended with a prior (50% = no
# signal) using beta-binomial conjugacy. With few signals, the prior dominates
# and weights stay near static defaults. With many signals, the data dominates.
#
# PRIOR_STRENGTH controls the equivalent number of "phantom" observations
# baked in at the 50% prior. At n=50 real signals, the data weight is
# 50/(50+50) = 50% — roughly where we start trusting the signal.
PRIOR_STRENGTH = 50  # pseudo-observations at the 50% prior
PRIOR_ACCURACY = 0.5  # uninformative prior (no directional bias)

# Minimum signals before ANY adjustment is attempted. Below this, the beta
# posterior is so dominated by the prior that the multiplier ≈ 1.0 anyway,
# but we skip to avoid spurious noise in logs.
MIN_SIGNALS_FOR_ADJUSTMENT = 10

# How aggressively the shrunk accuracy adjusts weights (0 = no adjustment, 1 = fully replace)
ACCURACY_BLEND = 0.4

# Default static weights (mirrors analyst.py FACTOR_WEIGHTS)
# NOTE: convergence removed — now a conviction gate, not a score input
DEFAULT_WEIGHTS = {
    "quant_score": 0.30,
    "fundamentals": 0.25,
    "momentum": 0.20,
    "insider_score": 0.15,
    "news_sentiment": 0.10,
}

# Map scout names to factor weight keys.
# Some factors (convergence, momentum) are derived, not from a single scout.
SCOUT_TO_FACTOR = {
    "quant": "quant_score",
    "insider": "insider_score",
    "news": "news_sentiment",
    "fundamentals": "fundamentals",
    # social, youtube, catalyst, filings, moat → contribute to convergence indirectly
    # We track their accuracy but they feed into the convergence factor
}

# Scouts that contribute to the convergence factor (their accuracy lifts/lowers convergence weight)
CONVERGENCE_SCOUTS = ["social", "youtube", "catalyst", "filings", "moat"]


def _fetch_historical_price(ticker: str, date: datetime) -> float | None:
    """Fetch the closing price for a ticker on or near a specific date.

    Uses yfinance to get historical data. Returns None if data unavailable.
    """
    try:
        stock = yf.Ticker(ticker)
        # Fetch a 5-day window around the target date to handle weekends/holidays
        start = (date - timedelta(days=2)).strftime("%Y-%m-%d")
        end = (date + timedelta(days=3)).strftime("%Y-%m-%d")
        hist = stock.history(start=start, end=end)
        if hist.empty:
            return None
        # Find the closest date on or after the target
        target_str = date.strftime("%Y-%m-%d")
        close_prices = hist["Close"]
        # Try exact date first
        if target_str in close_prices.index.strftime("%Y-%m-%d"):
            idx = close_prices.index.strftime("%Y-%m-%d").tolist().index(target_str)
            return float(close_prices.iloc[idx])
        # Otherwise take the first available price in the window
        return float(close_prices.iloc[0])
    except Exception as e:
        print(f"  [{ticker}] Price fetch failed for {date.date()}: {e}")
        return None


def _fetch_current_price(ticker: str) -> float | None:
    """Fetch the current/latest price for a ticker."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price:
            return float(price)
        # Fallback to last close from history
        hist = stock.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None
    except Exception:
        return None


def evaluate_outcomes() -> dict:
    """Evaluate signal outcomes for all matured signals.

    For each signal in the signals table:
    - Skip if already evaluated for that window
    - Skip neutral signals (no directional bet to validate)
    - For each window (7, 30, 60, 90 days), if enough time has passed:
      - Look up price at signal time and price at signal_date + window
      - Determine if the signal direction was correct
      - Save to signal_outcomes table

    Returns: {evaluated: int, skipped: int, errors: int}
    """
    sb = get_client()
    stats = {"evaluated": 0, "skipped": 0, "errors": 0}
    now = datetime.now(timezone.utc)

    # Load all signals that have directional calls
    resp = sb.table("signals") \
        .select("id, ticker, scout, signal, data, created_at") \
        .in_("signal", ["bullish", "bearish"]) \
        .order("created_at", desc=True) \
        .limit(2000) \
        .execute()

    signals = resp.data or []
    if not signals:
        print("[feedback] No directional signals found")
        return stats

    # Load existing outcomes to avoid re-evaluation
    outcome_resp = sb.table("signal_outcomes") \
        .select("signal_id, window_days") \
        .execute()
    evaluated_set: set[tuple[int, int]] = set()
    for o in (outcome_resp.data or []):
        evaluated_set.add((o["signal_id"], o["window_days"]))

    # Price cache to avoid redundant yfinance calls
    price_cache: dict[str, float] = {}  # "TICKER:YYYY-MM-DD" → price
    current_price_cache: dict[str, float] = {}  # "TICKER" → current price

    print(f"[feedback] Evaluating {len(signals)} directional signals across {len(EVAL_WINDOWS)} windows...")

    batch_outcomes: list[dict] = []

    for sig in signals:
        sig_id = sig["id"]
        ticker = sig["ticker"]
        scout = sig["scout"].lower()
        direction = sig["signal"]  # bullish or bearish
        sig_data = sig.get("data") or {}
        created_at = sig["created_at"]

        # Parse signal timestamp
        try:
            sig_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            stats["errors"] += 1
            continue

        # Get price at signal time — prefer stored price from quant data
        price_at_signal_key = f"{ticker}:{sig_date.date()}"
        if price_at_signal_key in price_cache:
            price_at_signal = price_cache[price_at_signal_key]
        else:
            # Try to get from the signal's own data first (quant signals store price)
            price_at_signal = sig_data.get("price")
            if not price_at_signal:
                price_at_signal = _fetch_historical_price(ticker, sig_date)
            if price_at_signal:
                price_cache[price_at_signal_key] = price_at_signal

        if not price_at_signal:
            stats["skipped"] += 1
            continue

        for window in EVAL_WINDOWS:
            # Skip if already evaluated
            if (sig_id, window) in evaluated_set:
                continue

            eval_date = sig_date + timedelta(days=window)

            # Skip if window hasn't matured yet
            if eval_date > now:
                continue

            # Get price at evaluation date
            eval_key = f"{ticker}:{eval_date.date()}"
            if eval_key in price_cache:
                price_at_eval = price_cache[eval_key]
            else:
                # If eval date is within last 5 days, use current price
                if (now - eval_date).days <= 5:
                    if ticker not in current_price_cache:
                        current_price_cache[ticker] = _fetch_current_price(ticker) or 0
                    price_at_eval = current_price_cache[ticker] or None
                else:
                    price_at_eval = _fetch_historical_price(ticker, eval_date)
                if price_at_eval:
                    price_cache[eval_key] = price_at_eval

            if not price_at_eval:
                stats["skipped"] += 1
                continue

            # Calculate return
            return_pct = ((price_at_eval - price_at_signal) / price_at_signal) * 100

            # Determine if signal was correct
            if direction == "bullish":
                hit = return_pct > 0  # bullish signal correct if price went up
            else:  # bearish
                hit = return_pct < 0  # bearish signal correct if price went down

            outcome = {
                "signal_id": sig_id,
                "ticker": ticker,
                "scout": scout,
                "signal": direction,
                "window_days": window,
                "signal_date": sig_date.isoformat(),
                "price_at_signal": round(float(price_at_signal), 2),
                "price_at_eval": round(float(price_at_eval), 2),
                "return_pct": round(float(return_pct), 2),
                "hit": hit,
            }
            batch_outcomes.append(outcome)
            stats["evaluated"] += 1

    # Batch insert outcomes
    if batch_outcomes:
        try:
            # Insert in chunks to avoid payload limits
            chunk_size = 100
            for i in range(0, len(batch_outcomes), chunk_size):
                chunk = batch_outcomes[i:i + chunk_size]
                sb.table("signal_outcomes").upsert(
                    chunk, on_conflict="signal_id,window_days"
                ).execute()
            print(f"[feedback] Saved {len(batch_outcomes)} new outcomes")
        except Exception as e:
            print(f"[feedback] Error saving outcomes: {e}")
            stats["errors"] += len(batch_outcomes)
            stats["evaluated"] -= len(batch_outcomes)

    return stats


def compute_accuracy() -> list[dict]:
    """Compute per-scout accuracy from signal_outcomes and save to scout_accuracy table.

    Returns the accuracy rows for downstream use.
    """
    sb = get_client()

    # Load all outcomes
    resp = sb.table("signal_outcomes").select("*").execute()
    outcomes = resp.data or []

    if not outcomes:
        print("[feedback] No outcomes to compute accuracy from")
        return []

    # Aggregate per (scout, window)
    from collections import defaultdict
    stats: dict[tuple[str, int], dict] = defaultdict(lambda: {
        "total": 0, "hits": 0, "misses": 0,
        "returns": [], "hit_returns": [], "miss_returns": [],
        "bullish_total": 0, "bullish_hits": 0,
        "bearish_total": 0, "bearish_hits": 0,
    })

    for o in outcomes:
        key = (o["scout"], o["window_days"])
        s = stats[key]
        s["total"] += 1
        ret = float(o.get("return_pct") or 0)
        s["returns"].append(ret)

        if o["hit"]:
            s["hits"] += 1
            s["hit_returns"].append(ret)
        else:
            s["misses"] += 1
            s["miss_returns"].append(ret)

        sig = o.get("signal", "")
        if sig == "bullish":
            s["bullish_total"] += 1
            if o["hit"]:
                s["bullish_hits"] += 1
        elif sig == "bearish":
            s["bearish_total"] += 1
            if o["hit"]:
                s["bearish_hits"] += 1

    rows = []
    for (scout, window), s in stats.items():
        avg = lambda lst: round(sum(lst) / len(lst), 2) if lst else 0
        accuracy = round(s["hits"] / s["total"] * 100, 1) if s["total"] > 0 else 0
        bullish_acc = round(s["bullish_hits"] / s["bullish_total"] * 100, 1) if s["bullish_total"] > 0 else 0
        bearish_acc = round(s["bearish_hits"] / s["bearish_total"] * 100, 1) if s["bearish_total"] > 0 else 0

        row = {
            "scout": scout,
            "window_days": window,
            "total_signals": s["total"],
            "hits": s["hits"],
            "misses": s["misses"],
            "accuracy_pct": accuracy,
            "avg_return_pct": avg(s["returns"]),
            "avg_hit_return": avg(s["hit_returns"]),
            "avg_miss_return": avg(s["miss_returns"]),
            "bullish_accuracy": bullish_acc,
            "bearish_accuracy": bearish_acc,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(row)

    # Upsert to scout_accuracy table
    if rows:
        try:
            sb.table("scout_accuracy").upsert(rows, on_conflict="scout,window_days").execute()
            print(f"[feedback] Updated accuracy for {len(rows)} scout/window combos")
        except Exception as e:
            print(f"[feedback] Error saving accuracy: {e}")

    # Print summary
    print("\n[feedback] Scout Accuracy Summary (30-day window):")
    for r in sorted(rows, key=lambda x: x["accuracy_pct"], reverse=True):
        if r["window_days"] == 30:
            emoji = "🎯" if r["accuracy_pct"] >= 60 else "📊" if r["accuracy_pct"] >= 50 else "⚠️"
            print(f"  {emoji} {r['scout']:<15} {r['accuracy_pct']:>5.1f}% accuracy "
                  f"({r['hits']}/{r['total_signals']} hits, avg return: {r['avg_return_pct']:+.1f}%)")

    return rows


def get_adaptive_weights(window_days: int = 30) -> dict[str, float]:
    """Return FACTOR_WEIGHTS adjusted by scout accuracy.

    Strategy:
    - Load per-scout accuracy from scout_accuracy table
    - For scouts with enough data (>=MIN_SIGNALS_FOR_ADJUSTMENT), blend
      their accuracy into the default weight
    - Scouts with >60% accuracy get boosted, <40% get reduced
    - Weights are renormalized to sum to 1.0
    - Falls back to DEFAULT_WEIGHTS if not enough data

    Returns: dict matching FACTOR_WEIGHTS shape
    """
    sb = get_client()

    try:
        resp = sb.table("scout_accuracy") \
            .select("*") \
            .eq("window_days", window_days) \
            .execute()
        accuracy_rows = resp.data or []
    except Exception:
        return dict(DEFAULT_WEIGHTS)

    if not accuracy_rows:
        return dict(DEFAULT_WEIGHTS)

    # Build scout → accuracy map
    acc_map: dict[str, dict] = {}
    for r in accuracy_rows:
        acc_map[r["scout"]] = r

    weights = dict(DEFAULT_WEIGHTS)

    # Adjust direct scout → factor mappings using Bayesian shrinkage.
    #
    # Beta-binomial posterior: given n signals with k correct,
    #   shrunk_accuracy = (k + PRIOR_STRENGTH * PRIOR_ACCURACY) / (n + PRIOR_STRENGTH)
    #
    # At n=10:  data weight = 10/60  ≈ 17% — prior dominates, near 50%
    # At n=50:  data weight = 50/100 = 50% — even blend
    # At n=100: data weight = 100/150 ≈ 67% — data dominates
    # At n=200: data weight = 200/250 = 80% — strongly data-driven
    for scout, factor in SCOUT_TO_FACTOR.items():
        if scout not in acc_map:
            continue
        acc = acc_map[scout]
        n = acc["total_signals"]
        if n < MIN_SIGNALS_FOR_ADJUSTMENT:
            continue

        raw_accuracy = acc["accuracy_pct"] / 100.0  # 0.0 - 1.0
        k = raw_accuracy * n  # approximate correct count

        # Beta posterior mean (shrunk toward prior)
        shrunk_accuracy = (k + PRIOR_STRENGTH * PRIOR_ACCURACY) / (n + PRIOR_STRENGTH)

        # Accuracy multiplier: 60% → 1.2x, 50% → 1.0x, 40% → 0.8x
        # Linear scale from 0.5 baseline
        multiplier = 0.6 + (shrunk_accuracy * 0.8)  # 50% → 1.0x, 100% → 1.4x
        multiplier = max(0.5, min(1.5, multiplier))  # clamp

        old_w = weights[factor]
        new_w = old_w * multiplier
        # Blend: partial adaptation
        weights[factor] = old_w * (1 - ACCURACY_BLEND) + new_w * ACCURACY_BLEND

    # NOTE: Convergence weight adjustment removed — convergence is now a
    # conviction gate, not a composite score input. The convergence scouts
    # (social, youtube, catalyst, filings, moat) still have their accuracy
    # tracked but no longer feed into weight adjustment.

    # Renormalize to sum to 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: round(v / total, 4) for k, v in weights.items()}

    return weights


def load_scout_accuracy(window_days: int = 30) -> list[dict]:
    """Load scout accuracy data for dashboard display."""
    sb = get_client()
    try:
        resp = sb.table("scout_accuracy") \
            .select("*") \
            .eq("window_days", window_days) \
            .order("accuracy_pct", desc=True) \
            .execute()
        return resp.data or []
    except Exception:
        return []


def run_feedback_loop() -> dict:
    """Run the full feedback loop: evaluate outcomes, then compute accuracy.

    Returns: {outcomes: {evaluated, skipped, errors}, accuracy_rows: int}
    """
    print("\n" + "=" * 60)
    print("FEEDBACK LOOP — Signal Outcome Evaluation")
    print("=" * 60)

    outcome_stats = evaluate_outcomes()
    print(f"\n[feedback] Outcome evaluation: {outcome_stats['evaluated']} evaluated, "
          f"{outcome_stats['skipped']} skipped, {outcome_stats['errors']} errors")

    accuracy_rows = compute_accuracy()

    # Print adaptive weights comparison
    adaptive = get_adaptive_weights()
    has_adjustments = any(
        abs(adaptive[k] - DEFAULT_WEIGHTS[k]) > 0.005
        for k in DEFAULT_WEIGHTS
    )

    if has_adjustments:
        print("\n[feedback] Adaptive Weight Adjustments:")
        for factor in DEFAULT_WEIGHTS:
            default = DEFAULT_WEIGHTS[factor]
            adapted = adaptive[factor]
            delta = adapted - default
            if abs(delta) > 0.005:
                arrow = "↑" if delta > 0 else "↓"
                print(f"  {factor:<20} {default:.3f} → {adapted:.3f}  ({arrow} {abs(delta):.3f})")
            else:
                print(f"  {factor:<20} {default:.3f}    (unchanged)")
    else:
        print("\n[feedback] Not enough data for weight adjustments yet "
              f"(need {MIN_SIGNALS_FOR_ADJUSTMENT}+ signals per scout)")

    return {
        "outcomes": outcome_stats,
        "accuracy_rows": len(accuracy_rows),
        "adaptive_weights": adaptive,
        "has_adjustments": has_adjustments,
    }


if __name__ == "__main__":
    result = run_feedback_loop()
    print(f"\nDone. {result['outcomes']['evaluated']} outcomes evaluated, "
          f"{result['accuracy_rows']} accuracy rows updated.")
