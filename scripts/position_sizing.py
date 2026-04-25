#!/usr/bin/env python3
"""
position_sizing.py — Position sizing strategies for Stock Radar.

Provides two primary strategies:

1. **Half-Kelly** (default):
   Uses the Kelly criterion with a 0.5× fractional multiplier for
   conservatism. Edge is derived from model scenario probabilities.
   Individual positions capped at 10%.

2. **HRP (Hierarchical Risk Parity)** (López de Prado 2016):
   Uses hierarchical clustering on the correlation matrix to allocate
   risk across assets. More diversified than mean-variance, more robust
   to estimation error.

Both strategies respect:
  - Per-position caps (default 10%)
  - Maximum total exposure (default 100%)
  - Regime-based scaling (from regime_detection.py)
  - Minimum conviction threshold (composite score ≥ 6)

Usage:
    from position_sizing import half_kelly_weights, hrp_weights

    # Half-Kelly from model outputs
    weights = half_kelly_weights(models, scores)

    # HRP from correlation matrix
    weights = hrp_weights(tickers, days=252)
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

try:
    import numpy as np
    import pandas as pd
except ImportError:
    np = pd = None  # type: ignore

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore

try:
    from scipy.cluster.hierarchy import linkage, leaves_list
    from scipy.spatial.distance import squareform
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ─── Config ───────────────────────────────────────────────────────────

MAX_POSITION = 0.10        # 10% max per position
KELLY_FRACTION = 0.5       # half-Kelly
MIN_SCORE = 6.0            # minimum composite score to trade
MIN_EXPECTED_RETURN = 0.02 # minimum 2% expected return
MAX_POSITIONS = 15


# ─── Data types ───────────────────────────────────────────────────────

@dataclass
class PositionAllocation:
    """Allocation for a single position."""
    ticker: str
    weight: float           # fraction of portfolio (0 to MAX_POSITION)
    method: str             # "half_kelly" | "hrp" | "blended"
    score: float            # composite score
    expected_return: float  # from model scenarios
    risk_contribution: float  # % of portfolio risk from this position
    reason: str


# ─── Half-Kelly ───────────────────────────────────────────────────────

def half_kelly_weights(
    models: list[dict],
    scores: dict[str, float],
    regime_scale: float = 1.0,
) -> list[PositionAllocation]:
    """Compute half-Kelly position sizes from model outputs.

    Parameters
    ----------
    models : list[dict]
        Model configs with scenarios.
    scores : dict[str, float]
        {ticker: composite_score} from analyst.
    regime_scale : float
        Multiplier from regime detection (0.5 in risk-off, 1.0 in risk-on).
    """
    allocations: list[PositionAllocation] = []

    for model in models:
        ticker = model.get("ticker", "")
        score = scores.get(ticker, 0)

        if score < MIN_SCORE:
            continue

        scenarios = model.get("scenarios", {})
        current_price = model.get("current_price", 0)
        if not current_price or current_price <= 0:
            continue

        # Expected return from probability-weighted scenarios
        p_bull = scenarios.get("bull", {}).get("probability", 0.25)
        p_base = scenarios.get("base", {}).get("probability", 0.50)
        p_bear = scenarios.get("bear", {}).get("probability", 0.25)

        r_bull = (scenarios.get("bull", {}).get("price", current_price) - current_price) / current_price
        r_base = (scenarios.get("base", {}).get("price", current_price) - current_price) / current_price
        r_bear = (scenarios.get("bear", {}).get("price", current_price) - current_price) / current_price

        expected_return = p_bull * r_bull + p_base * r_base + p_bear * r_bear

        if expected_return < MIN_EXPECTED_RETURN:
            continue

        # Kelly: f* = (p*b - q) / b
        prob_win = p_bull + p_base
        avg_win = (p_bull * r_bull + p_base * r_base) / max(prob_win, 0.01)
        avg_loss = abs(r_bear) if r_bear < 0 else 0.01

        if avg_win <= 0 or avg_loss <= 0:
            continue

        b = avg_win / avg_loss
        q = 1 - prob_win
        kelly = max(0, (prob_win * b - q) / b)

        weight = min(kelly * KELLY_FRACTION * regime_scale, MAX_POSITION)

        if weight > 0.005:  # minimum 0.5% to bother
            allocations.append(PositionAllocation(
                ticker=ticker,
                weight=weight,
                method="half_kelly",
                score=score,
                expected_return=expected_return,
                risk_contribution=0,  # filled later
                reason=f"Kelly={kelly:.1%}×{KELLY_FRACTION}×{regime_scale:.0%}",
            ))

    # Sort by expected_return × score, take top MAX_POSITIONS
    allocations.sort(key=lambda a: a.expected_return * a.score, reverse=True)
    allocations = allocations[:MAX_POSITIONS]

    # Normalize if total > 1
    total = sum(a.weight for a in allocations)
    if total > 1.0:
        for a in allocations:
            a.weight /= total

    # Compute risk contributions (equal for Kelly — proportional to weight)
    total_w = sum(a.weight for a in allocations)
    for a in allocations:
        a.risk_contribution = (a.weight / total_w * 100) if total_w > 0 else 0

    return allocations


# ─── HRP (Hierarchical Risk Parity) ──────────────────────────────────

def hrp_weights(
    tickers: list[str],
    days: int = 252,
    regime_scale: float = 1.0,
    scores: dict[str, float] | None = None,
) -> list[PositionAllocation]:
    """Compute HRP position sizes (López de Prado 2016).

    Steps:
    1. Compute correlation matrix from return data
    2. Hierarchical clustering (single linkage on correlation distance)
    3. Quasi-diagonalize the correlation matrix
    4. Recursive bisection to allocate weights inversely to cluster variance

    Parameters
    ----------
    tickers : list[str]
        Tickers to allocate across.
    days : int
        Lookback period for correlation estimation.
    regime_scale : float
        Position scale from regime detection.
    scores : dict
        Optional composite scores for filtering.
    """
    if not np or not pd or not HAS_SCIPY or not yf:
        return []

    # Filter by score if provided
    if scores:
        tickers = [t for t in tickers if scores.get(t, 0) >= MIN_SCORE]

    if len(tickers) < 2:
        # Single ticker gets max weight
        if tickers:
            return [PositionAllocation(
                ticker=tickers[0], weight=min(MAX_POSITION, regime_scale),
                method="hrp", score=scores.get(tickers[0], 0) if scores else 0,
                expected_return=0, risk_contribution=100,
                reason="Single ticker — max weight",
            )]
        return []

    # Fetch returns
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))
    try:
        data = yf.download(tickers, start=start, end=end, progress=False)
        if data.empty:
            return []
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data
        returns = close.pct_change().dropna()
    except Exception:
        return []

    # Only keep tickers with enough data
    valid_tickers = [t for t in tickers if t in returns.columns and returns[t].notna().sum() > 60]
    if len(valid_tickers) < 2:
        return []

    returns = returns[valid_tickers].dropna()

    # Correlation & covariance
    corr = returns.corr()
    cov = returns.cov()

    # Step 1: Correlation distance
    dist = np.sqrt((1 - corr) / 2)
    dist_condensed = squareform(dist.values, checks=False)

    # Step 2: Hierarchical clustering
    link = linkage(dist_condensed, method="single")

    # Step 3: Quasi-diagonalize (get leaf order)
    sorted_idx = leaves_list(link).tolist()
    sorted_tickers = [valid_tickers[i] for i in sorted_idx]

    # Step 4: Recursive bisection
    weights = _recursive_bisection(cov, sorted_tickers)

    # Apply regime scale and cap
    allocations = []
    for ticker in sorted_tickers:
        w = min(weights.get(ticker, 0) * regime_scale, MAX_POSITION)
        if w < 0.005:
            continue
        allocations.append(PositionAllocation(
            ticker=ticker,
            weight=w,
            method="hrp",
            score=scores.get(ticker, 0) if scores else 0,
            expected_return=0,  # HRP is risk-based, not return-based
            risk_contribution=0,
            reason=f"HRP weight={weights.get(ticker, 0):.1%}×{regime_scale:.0%}",
        ))

    # Compute risk contributions
    total_w = sum(a.weight for a in allocations)
    if total_w > 0:
        port_var = 0
        w_vec = np.array([a.weight for a in allocations])
        t_list = [a.ticker for a in allocations]
        cov_sub = cov.loc[t_list, t_list].values
        port_var = w_vec @ cov_sub @ w_vec

        if port_var > 0:
            marginal = cov_sub @ w_vec
            for i, a in enumerate(allocations):
                a.risk_contribution = float(a.weight * marginal[i] / port_var * 100)

    return allocations[:MAX_POSITIONS]


def _recursive_bisection(
    cov: pd.DataFrame,
    sorted_tickers: list[str],
) -> dict[str, float]:
    """HRP recursive bisection step.

    Split the sorted ticker list in half recursively. At each split,
    allocate weight inversely proportional to cluster variance.
    """
    weights = {t: 1.0 for t in sorted_tickers}

    clusters = [sorted_tickers]
    while clusters:
        new_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue

            mid = len(cluster) // 2
            left = cluster[:mid]
            right = cluster[mid:]

            # Cluster variance = inverse-variance weight
            var_left = _cluster_variance(cov, left)
            var_right = _cluster_variance(cov, right)

            total_var = var_left + var_right
            if total_var < 1e-15:
                alpha = 0.5
            else:
                alpha = 1 - var_left / total_var  # more var → less weight

            for t in left:
                weights[t] *= alpha
            for t in right:
                weights[t] *= (1 - alpha)

            if len(left) > 1:
                new_clusters.append(left)
            if len(right) > 1:
                new_clusters.append(right)

        clusters = new_clusters

    return weights


def _cluster_variance(cov: pd.DataFrame, tickers: list[str]) -> float:
    """Compute variance of an equally-weighted cluster."""
    if not tickers:
        return 0.0
    sub_cov = cov.loc[tickers, tickers].values
    n = len(tickers)
    w = np.ones(n) / n
    return float(w @ sub_cov @ w)


# ─── Blended strategy ────────────────────────────────────────────────

def blended_weights(
    models: list[dict],
    scores: dict[str, float],
    tickers: list[str],
    kelly_weight: float = 0.6,
    hrp_weight: float = 0.4,
    regime_scale: float = 1.0,
) -> list[PositionAllocation]:
    """Blend half-Kelly (conviction-based) with HRP (risk-based).

    Default: 60% Kelly + 40% HRP. This gives conviction-overweight to
    high-score stocks while maintaining risk diversification.
    """
    kelly = half_kelly_weights(models, scores, regime_scale)
    hrp = hrp_weights(tickers, scores=scores, regime_scale=regime_scale)

    kelly_map = {a.ticker: a.weight for a in kelly}
    hrp_map = {a.ticker: a.weight for a in hrp}

    all_tickers = set(kelly_map.keys()) | set(hrp_map.keys())
    allocations = []

    for ticker in all_tickers:
        kw = kelly_map.get(ticker, 0)
        hw = hrp_map.get(ticker, 0)
        blended = kw * kelly_weight + hw * hrp_weight
        blended = min(blended, MAX_POSITION)

        if blended < 0.005:
            continue

        score = scores.get(ticker, 0)
        allocations.append(PositionAllocation(
            ticker=ticker,
            weight=blended,
            method="blended",
            score=score,
            expected_return=0,
            risk_contribution=0,
            reason=f"Kelly={kw:.1%}×{kelly_weight} + HRP={hw:.1%}×{hrp_weight}",
        ))

    allocations.sort(key=lambda a: a.weight, reverse=True)
    return allocations[:MAX_POSITIONS]


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Position sizing")
    parser.add_argument("--method", choices=["kelly", "hrp", "blended"],
                        default="blended")
    parser.add_argument("--tickers", nargs="+", help="Tickers to size")
    parser.add_argument("--days", type=int, default=252)
    args = parser.parse_args()

    tickers = args.tickers
    if not tickers:
        # Load from watchlist
        from pathlib import Path
        wl_file = Path(__file__).resolve().parent.parent / "config" / "watchlist.json"
        if wl_file.exists():
            wl = json.loads(wl_file.read_text())
            tickers = [
                s.get("ticker", s) if isinstance(s, dict) else s
                for s in wl.get("stocks", wl)
                if isinstance(s, (str, dict))
            ]
            tickers = [t for t in tickers if "." not in t][:20]

    if not tickers:
        print("No tickers specified")
        sys.exit(1)

    scores = {t: 7.0 for t in tickers}  # dummy scores for standalone use

    if args.method == "hrp":
        print(f"Computing HRP weights for {len(tickers)} tickers...")
        allocs = hrp_weights(tickers, days=args.days, scores=scores)
    elif args.method == "kelly":
        print("Kelly requires model outputs — use via paper_trade.py")
        sys.exit(0)
    else:
        print(f"Computing blended weights for {len(tickers)} tickers...")
        # Need models for Kelly component — use HRP only in standalone mode
        allocs = hrp_weights(tickers, days=args.days, scores=scores)

    print(f"\n{'Ticker':<8} {'Weight':>8} {'Risk%':>8} {'Method':<10} Reason")
    print(f"{'─'*60}")
    for a in allocs:
        print(f"{a.ticker:<8} {a.weight:>7.1%} {a.risk_contribution:>7.1f}% {a.method:<10} {a.reason}")
    total = sum(a.weight for a in allocs)
    print(f"\nTotal allocation: {total:.1%}")
