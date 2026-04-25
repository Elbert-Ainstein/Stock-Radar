#!/usr/bin/env python3
"""
backtest.py — Walk-forward + Combinatorial Purged Cross-Validation (CPCV).

Implements two backtesting methodologies:

1. **Walk-forward** (anchored or rolling window):
   Train on signals [t0, t_split], test on [t_split+embargo, t_split+test_window].
   Slide t_split forward by step_days. Reports per-fold and aggregate metrics.

2. **CPCV** (de Prado, Advances in Financial Machine Learning ch.12):
   Split signal history into N groups by time. For each combination of
   (N − k) train groups and k test groups, run evaluation with an embargo
   gap to prevent leakage. Reports distribution of metrics across all paths.

Metrics per fold:
  - Hit rate (% correct directional calls)
  - Information Coefficient (rank correlation of score vs forward return)
  - Mean return (of signals acted on)
  - Sharpe ratio (annualized, of signal returns)

Usage:
    python backtest.py --mode walk-forward --window 180 --step 30
    python backtest.py --mode cpcv --n-groups 6 --k-test 2
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(__file__))

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

try:
    from scipy import stats as sp_stats
except ImportError:
    sp_stats = None  # type: ignore


# ─── Data types ───────────────────────────────────────────────────────

@dataclass
class Signal:
    """A single scored signal with outcome."""
    ticker: str
    date: str           # ISO date when signal was generated
    score: float        # composite score (0-10)
    direction: str      # "bullish" | "bearish"
    forward_return: float | None = None  # realized % return over eval window
    price_at_signal: float | None = None
    price_at_eval: float | None = None


@dataclass
class FoldResult:
    """Metrics from a single backtest fold."""
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    n_signals: int
    hit_rate: float         # % of correct directional calls
    ic: float               # Spearman rank correlation (score vs return)
    mean_return: float      # average forward return %
    sharpe: float           # annualized Sharpe of signal returns
    signals: list[Signal] = field(default_factory=list)


@dataclass
class BacktestReport:
    """Aggregate backtest results across all folds."""
    mode: str               # "walk_forward" or "cpcv"
    n_folds: int
    total_signals: int
    # Aggregate metrics (mean across folds)
    mean_hit_rate: float
    std_hit_rate: float
    mean_ic: float
    std_ic: float
    mean_return: float
    mean_sharpe: float
    # Per-fold detail
    folds: list[FoldResult] = field(default_factory=list)
    # Deflated Sharpe (only for CPCV — accounts for selection bias)
    deflated_sharpe_p: float | None = None

    def summary(self) -> str:
        lines = [
            f"Backtest ({self.mode}): {self.n_folds} folds, {self.total_signals} signals",
            f"  Hit rate:  {self.mean_hit_rate:.1f}% ± {self.std_hit_rate:.1f}%",
            f"  IC:        {self.mean_ic:.4f} ± {self.std_ic:.4f}",
            f"  Return:    {self.mean_return:.2f}%",
            f"  Sharpe:    {self.mean_sharpe:.2f}",
        ]
        if self.deflated_sharpe_p is not None:
            lines.append(f"  Deflated Sharpe p-value: {self.deflated_sharpe_p:.4f}")
        return "\n".join(lines)


# ─── Metric computation ──────────────────────────────────────────────

def _hit_rate(signals: list[Signal]) -> float:
    """Fraction of signals where direction matched realized return."""
    if not signals:
        return 0.0
    hits = 0
    for s in signals:
        if s.forward_return is None:
            continue
        correct = (
            (s.direction == "bullish" and s.forward_return > 0)
            or (s.direction == "bearish" and s.forward_return < 0)
        )
        if correct:
            hits += 1
    evaluated = sum(1 for s in signals if s.forward_return is not None)
    return (hits / evaluated * 100) if evaluated > 0 else 0.0


def _information_coefficient(signals: list[Signal]) -> float:
    """Spearman rank correlation between score and forward return."""
    pairs = [
        (s.score, s.forward_return)
        for s in signals
        if s.forward_return is not None
    ]
    if len(pairs) < 5:
        return 0.0

    if sp_stats:
        scores, returns = zip(*pairs)
        corr, _ = sp_stats.spearmanr(scores, returns)
        return float(corr) if not math.isnan(corr) else 0.0

    # Fallback: manual Spearman
    scores, returns = zip(*pairs)
    n = len(scores)
    rank_s = _rank(scores)
    rank_r = _rank(returns)
    d_sq = sum((rank_s[i] - rank_r[i]) ** 2 for i in range(n))
    return 1 - (6 * d_sq) / (n * (n ** 2 - 1))


def _rank(values: tuple) -> list[float]:
    """Simple ranking (average rank for ties)."""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 1) / 2  # 1-based average
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def _sharpe(signals: list[Signal], annualize_factor: float = 252 / 30) -> float:
    """Annualized Sharpe ratio from signal returns."""
    returns = [s.forward_return for s in signals if s.forward_return is not None]
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(var_r) if var_r > 0 else 1e-10
    return (mean_r / std_r) * math.sqrt(annualize_factor)


def _compute_fold_metrics(
    fold_id: int,
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
    test_signals: list[Signal],
) -> FoldResult:
    """Compute all metrics for a single fold."""
    return FoldResult(
        fold_id=fold_id,
        train_start=train_start,
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
        n_signals=len(test_signals),
        hit_rate=_hit_rate(test_signals),
        ic=_information_coefficient(test_signals),
        mean_return=(
            sum(s.forward_return for s in test_signals if s.forward_return is not None)
            / max(1, sum(1 for s in test_signals if s.forward_return is not None))
        ),
        sharpe=_sharpe(test_signals),
        signals=test_signals,
    )


def _aggregate_folds(folds: list[FoldResult], mode: str) -> BacktestReport:
    """Aggregate fold results into a report."""
    if not folds:
        return BacktestReport(
            mode=mode, n_folds=0, total_signals=0,
            mean_hit_rate=0, std_hit_rate=0,
            mean_ic=0, std_ic=0,
            mean_return=0, mean_sharpe=0,
        )

    hit_rates = [f.hit_rate for f in folds if f.n_signals > 0]
    ics = [f.ic for f in folds if f.n_signals > 0]
    returns = [f.mean_return for f in folds if f.n_signals > 0]
    sharpes = [f.sharpe for f in folds if f.n_signals > 0]

    def _mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    def _std(xs):
        if len(xs) < 2:
            return 0.0
        m = _mean(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

    return BacktestReport(
        mode=mode,
        n_folds=len(folds),
        total_signals=sum(f.n_signals for f in folds),
        mean_hit_rate=_mean(hit_rates),
        std_hit_rate=_std(hit_rates),
        mean_ic=_mean(ics),
        std_ic=_std(ics),
        mean_return=_mean(returns),
        mean_sharpe=_mean(sharpes),
        folds=folds,
    )


# ─── Walk-Forward ─────────────────────────────────────────────────────

def walk_forward(
    signals: list[Signal],
    train_window_days: int = 180,
    test_window_days: int = 30,
    step_days: int = 30,
    embargo_days: int = 5,
    anchored: bool = True,
) -> BacktestReport:
    """Run anchored or rolling walk-forward backtest.

    Parameters
    ----------
    signals : list[Signal]
        All historical signals, sorted by date.
    train_window_days : int
        Training window size in days (ignored if anchored=True, which
        uses all data from the start).
    test_window_days : int
        Test window size in days.
    step_days : int
        How far to slide the split point each fold.
    embargo_days : int
        Gap between train end and test start to prevent leakage.
    anchored : bool
        If True, training always starts from the first signal date.
        If False, uses a rolling window of train_window_days.
    """
    if not signals:
        return _aggregate_folds([], "walk_forward")

    signals = sorted(signals, key=lambda s: s.date)
    first_date = datetime.strptime(signals[0].date, "%Y-%m-%d")
    last_date = datetime.strptime(signals[-1].date, "%Y-%m-%d")

    folds: list[FoldResult] = []
    fold_id = 0

    # Start the first split after enough training data
    split_date = first_date + timedelta(days=train_window_days)

    while split_date + timedelta(days=embargo_days + test_window_days) <= last_date:
        train_start = first_date if anchored else split_date - timedelta(days=train_window_days)
        train_end = split_date
        test_start = split_date + timedelta(days=embargo_days)
        test_end = test_start + timedelta(days=test_window_days)

        # Filter test signals
        ts_str = test_start.strftime("%Y-%m-%d")
        te_str = test_end.strftime("%Y-%m-%d")
        test_signals = [
            s for s in signals
            if ts_str <= s.date <= te_str
        ]

        if test_signals:
            fold = _compute_fold_metrics(
                fold_id=fold_id,
                train_start=train_start.strftime("%Y-%m-%d"),
                train_end=train_end.strftime("%Y-%m-%d"),
                test_start=ts_str,
                test_end=te_str,
                test_signals=test_signals,
            )
            folds.append(fold)
            fold_id += 1

        split_date += timedelta(days=step_days)

    return _aggregate_folds(folds, "walk_forward")


# ─── CPCV (Combinatorial Purged Cross-Validation) ────────────────────

def cpcv(
    signals: list[Signal],
    n_groups: int = 6,
    k_test: int = 2,
    embargo_days: int = 5,
) -> BacktestReport:
    """Run Combinatorial Purged Cross-Validation (de Prado).

    Splits signals into n_groups time-ordered groups, then for each
    combination of k_test test groups (and n_groups-k_test train groups),
    evaluates with an embargo gap around test boundaries.

    This produces C(n_groups, k_test) folds — far more than standard
    k-fold — giving a distribution of performance metrics that accounts
    for path dependency.

    Parameters
    ----------
    signals : list[Signal]
        All historical signals, sorted by date.
    n_groups : int
        Number of time groups to split signals into.
    k_test : int
        Number of groups to use as test in each fold.
    embargo_days : int
        Gap in days around test group boundaries to purge from training.
    """
    if not signals or n_groups < 3 or k_test < 1 or k_test >= n_groups:
        return _aggregate_folds([], "cpcv")

    signals = sorted(signals, key=lambda s: s.date)
    n = len(signals)
    group_size = n // n_groups

    # Assign signals to time-ordered groups
    groups: list[list[Signal]] = []
    for g in range(n_groups):
        start_idx = g * group_size
        end_idx = start_idx + group_size if g < n_groups - 1 else n
        groups.append(signals[start_idx:end_idx])

    folds: list[FoldResult] = []
    fold_id = 0

    # Generate all C(n_groups, k_test) test group combinations
    for test_group_indices in combinations(range(n_groups), k_test):
        test_group_set = set(test_group_indices)
        train_group_indices = [i for i in range(n_groups) if i not in test_group_set]

        # Collect test signals
        test_signals = []
        for gi in test_group_indices:
            test_signals.extend(groups[gi])

        if not test_signals:
            continue

        # Determine test date boundaries for embargo purging
        test_dates = [datetime.strptime(s.date, "%Y-%m-%d") for s in test_signals]
        test_min = min(test_dates)
        test_max = max(test_dates)

        # Purge training signals that are within embargo_days of test boundaries
        train_signals = []
        for gi in train_group_indices:
            for s in groups[gi]:
                s_date = datetime.strptime(s.date, "%Y-%m-%d")
                if (s_date < test_min - timedelta(days=embargo_days)
                        or s_date > test_max + timedelta(days=embargo_days)):
                    train_signals.append(s)

        # Compute test date range strings
        test_start = min(s.date for s in test_signals)
        test_end = max(s.date for s in test_signals)
        train_start = min(s.date for s in train_signals) if train_signals else test_start
        train_end = max(s.date for s in train_signals) if train_signals else test_start

        fold = _compute_fold_metrics(
            fold_id=fold_id,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            test_signals=test_signals,
        )
        folds.append(fold)
        fold_id += 1

    report = _aggregate_folds(folds, "cpcv")

    # Compute deflated Sharpe ratio (accounts for multiple testing)
    if folds and sp_stats:
        sharpes = [f.sharpe for f in folds if f.n_signals > 0]
        if len(sharpes) >= 2:
            report.deflated_sharpe_p = _deflated_sharpe_pvalue(
                sharpes, n_trials=len(sharpes)
            )

    return report


def _deflated_sharpe_pvalue(sharpes: list[float], n_trials: int) -> float:
    """Compute the Deflated Sharpe Ratio p-value (Bailey & de Prado 2014).

    Tests H0: the best observed Sharpe is no better than what you'd expect
    from trying n_trials strategies on noise.

    Returns p-value — lower is better (reject the null = strategy is real).
    """
    if not sp_stats or not sharpes or n_trials < 2:
        return 1.0

    sr_max = max(sharpes)
    sr_mean = sum(sharpes) / len(sharpes)
    sr_std = math.sqrt(
        sum((s - sr_mean) ** 2 for s in sharpes) / (len(sharpes) - 1)
    ) if len(sharpes) > 1 else 1.0

    if sr_std < 1e-10:
        return 1.0

    # Expected max Sharpe under the null (Euler-Mascheroni approximation)
    euler_mascheroni = 0.5772
    expected_max = sr_std * (
        (1 - euler_mascheroni) * sp_stats.norm.ppf(1 - 1 / n_trials)
        + euler_mascheroni * sp_stats.norm.ppf(1 - 1 / (n_trials * math.e))
    )

    # Test statistic
    z = (sr_max - expected_max) / sr_std
    p_value = 1 - sp_stats.norm.cdf(z)
    return float(p_value)


# ─── Load signals from Supabase ───────────────────────────────────────

def load_signals_from_supabase() -> list[Signal]:
    """Load historical signals from the signal_outcomes table.

    Falls back to the scout_signals table if signal_outcomes is empty.
    """
    try:
        from supabase_helper import get_client
        sb = get_client()
    except Exception:
        print("  [backtest] Supabase not available, returning empty signals")
        return []

    signals: list[Signal] = []

    # Try signal_outcomes first (has realized returns)
    try:
        resp = sb.table("signal_outcomes").select("*").execute()
        if resp.data:
            for row in resp.data:
                signals.append(Signal(
                    ticker=row.get("ticker", ""),
                    date=row.get("signal_date", row.get("created_at", ""))[:10],
                    score=float(row.get("composite_score", 5.0)),
                    direction=row.get("direction", "bullish"),
                    forward_return=row.get("realized_return_pct"),
                    price_at_signal=row.get("price_at_signal"),
                    price_at_eval=row.get("price_at_eval"),
                ))
    except Exception:
        pass

    if not signals:
        # Fallback: scout_signals table (no realized returns yet)
        try:
            resp = sb.table("scout_signals").select(
                "ticker, created_at, signal, score"
            ).order("created_at").execute()
            if resp.data:
                for row in resp.data:
                    direction = "bullish" if (row.get("signal") or "").lower() in (
                        "bullish", "buy", "positive"
                    ) else "bearish"
                    signals.append(Signal(
                        ticker=row.get("ticker", ""),
                        date=row.get("created_at", "")[:10],
                        score=float(row.get("score", 5.0)),
                        direction=direction,
                    ))
        except Exception as e:
            print(f"  [backtest] Failed to load scout_signals: {e}")

    return signals


def backfill_returns(
    signals: list[Signal],
    eval_days: int = 30,
) -> list[Signal]:
    """Backfill forward_return for signals missing it (via yfinance)."""
    try:
        import yfinance as yf
    except ImportError:
        print("  [backtest] yfinance not available, cannot backfill returns")
        return signals

    # Group by ticker for batch fetching
    ticker_signals: dict[str, list[Signal]] = {}
    for s in signals:
        if s.forward_return is None:
            ticker_signals.setdefault(s.ticker, []).append(s)

    for ticker, sigs in ticker_signals.items():
        earliest = min(s.date for s in sigs)
        latest = max(s.date for s in sigs)
        start = (datetime.strptime(earliest, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
        end = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=eval_days + 10)).strftime("%Y-%m-%d")

        try:
            hist = yf.download(ticker, start=start, end=end, progress=False)
            if hist.empty:
                continue

            # Flatten MultiIndex columns if present
            if hasattr(hist.columns, 'levels'):
                hist.columns = hist.columns.get_level_values(0)

            close = hist["Close"].to_dict()
            dates_sorted = sorted(close.keys())

            for s in sigs:
                sig_date = datetime.strptime(s.date, "%Y-%m-%d")
                eval_date = sig_date + timedelta(days=eval_days)

                # Find closest trading day to signal date
                p_signal = _closest_price(close, dates_sorted, sig_date)
                p_eval = _closest_price(close, dates_sorted, eval_date)

                if p_signal and p_eval and p_signal > 0:
                    s.forward_return = ((p_eval - p_signal) / p_signal) * 100
                    s.price_at_signal = p_signal
                    s.price_at_eval = p_eval
        except Exception as e:
            print(f"  [backtest] Failed to fetch {ticker}: {e}")

    return signals


def _closest_price(
    close: dict,
    dates_sorted: list,
    target: datetime,
    max_gap: int = 5,
) -> float | None:
    """Find the closing price on or nearest to target date."""
    import pandas as pd
    target_ts = pd.Timestamp(target)
    for offset in range(max_gap + 1):
        for delta in [timedelta(days=offset), timedelta(days=-offset)]:
            check = target_ts + delta
            if check in close:
                val = close[check]
                return float(val) if val == val else None  # NaN check
    return None


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run backtesting harness")
    parser.add_argument("--mode", choices=["walk-forward", "cpcv", "both"],
                        default="both", help="Backtest mode")
    parser.add_argument("--window", type=int, default=180,
                        help="Training window days (walk-forward)")
    parser.add_argument("--step", type=int, default=30,
                        help="Step size days (walk-forward)")
    parser.add_argument("--test-window", type=int, default=30,
                        help="Test window days (walk-forward)")
    parser.add_argument("--n-groups", type=int, default=6,
                        help="Number of time groups (CPCV)")
    parser.add_argument("--k-test", type=int, default=2,
                        help="Number of test groups (CPCV)")
    parser.add_argument("--embargo", type=int, default=5,
                        help="Embargo days between train/test")
    parser.add_argument("--eval-days", type=int, default=30,
                        help="Forward return evaluation window")
    parser.add_argument("--backfill", action="store_true",
                        help="Backfill missing forward returns via yfinance")
    args = parser.parse_args()

    print("Loading signals from Supabase...")
    signals = load_signals_from_supabase()
    print(f"Loaded {len(signals)} signals")

    if args.backfill:
        print("Backfilling forward returns...")
        signals = backfill_returns(signals, eval_days=args.eval_days)
        filled = sum(1 for s in signals if s.forward_return is not None)
        print(f"  {filled}/{len(signals)} signals have forward returns")

    if args.mode in ("walk-forward", "both"):
        print("\n── Walk-Forward ──")
        wf = walk_forward(
            signals,
            train_window_days=args.window,
            test_window_days=args.test_window,
            step_days=args.step,
            embargo_days=args.embargo,
        )
        print(wf.summary())

    if args.mode in ("cpcv", "both"):
        print("\n── CPCV ──")
        cv = cpcv(
            signals,
            n_groups=args.n_groups,
            k_test=args.k_test,
            embargo_days=args.embargo,
        )
        print(cv.summary())
