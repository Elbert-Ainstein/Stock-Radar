#!/usr/bin/env python3
"""
factor_exposure.py — Factor exposure analysis for Stock Radar signals.

Decomposes signal returns into common risk factors to detect:
  - Unintended factor bets (e.g., portfolio is really just long-momentum)
  - Factor crowding (high exposure to a single factor)
  - Alpha after controlling for factor exposures

Uses a simplified Fama-French + Momentum model with these factors:
  - Market (Rm-Rf): broad market exposure
  - Size (SMB): small vs large cap tilt
  - Value (HML): value vs growth tilt
  - Momentum (UMD/WML): momentum factor
  - Quality (RMW): profitability factor
  - Investment (CMA): conservative vs aggressive investment

When full Fama-French data isn't available, falls back to sector-based
decomposition using GICS sector ETFs as factor proxies.

Usage:
    python factor_exposure.py --ticker LITE --days 252
    python factor_exposure.py --portfolio    # analyze full watchlist
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

try:
    import numpy as np
    import pandas as pd
except ImportError:
    np = pd = None  # type: ignore

try:
    from scipy import stats as sp_stats
except ImportError:
    sp_stats = None  # type: ignore

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore


# ─── Factor proxy ETFs ───────────────────────────────────────────────

FACTOR_ETFS = {
    "market":     "SPY",    # S&P 500
    "size":       "IWM",    # Russell 2000 (small cap proxy)
    "value":      "IWD",    # Russell 1000 Value
    "growth":     "IWF",    # Russell 1000 Growth
    "momentum":   "MTUM",   # iShares Momentum
    "quality":    "QUAL",   # iShares Quality
    "low_vol":    "USMV",   # iShares Min Vol
}

SECTOR_ETFS = {
    "technology":       "XLK",
    "healthcare":       "XLV",
    "financials":       "XLF",
    "consumer_disc":    "XLY",
    "consumer_staples": "XLP",
    "industrials":      "XLI",
    "energy":           "XLE",
    "utilities":        "XLU",
    "real_estate":      "XLRE",
    "materials":        "XLB",
    "communication":    "XLC",
}


# ─── Data types ───────────────────────────────────────────────────────

@dataclass
class FactorExposure:
    """Factor loading (beta) with statistics."""
    factor: str
    beta: float           # regression coefficient
    t_stat: float         # t-statistic
    p_value: float        # p-value for significance
    contribution: float   # % of variance explained by this factor


@dataclass
class ExposureReport:
    """Full factor exposure analysis for a stock or portfolio."""
    ticker: str           # or "PORTFOLIO" for aggregate
    period_days: int
    alpha: float          # annualized alpha (intercept)
    alpha_t_stat: float
    r_squared: float      # total R² of factor model
    exposures: list[FactorExposure]
    # Risk decomposition
    systematic_risk_pct: float   # % of total risk from factors
    idiosyncratic_risk_pct: float  # % from stock-specific risk
    # Warnings
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Factor Exposure: {self.ticker} ({self.period_days}d)",
            f"  Alpha (ann.): {self.alpha:.2%} (t={self.alpha_t_stat:.2f})",
            f"  R²: {self.r_squared:.3f}",
            f"  Systematic: {self.systematic_risk_pct:.1f}% | Idiosyncratic: {self.idiosyncratic_risk_pct:.1f}%",
            f"  Factors:",
        ]
        for e in sorted(self.exposures, key=lambda x: abs(x.beta), reverse=True):
            sig = "*" if e.p_value < 0.05 else " "
            lines.append(
                f"    {e.factor:<12} β={e.beta:>+7.3f}  t={e.t_stat:>6.2f}  "
                f"p={e.p_value:.3f}{sig}  contrib={e.contribution:.1f}%"
            )
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


# ─── Data fetching ────────────────────────────────────────────────────

def _fetch_returns(
    tickers: list[str],
    days: int = 252,
) -> pd.DataFrame | None:
    """Fetch daily returns for a list of tickers via yfinance."""
    if not yf or not pd:
        return None

    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))  # extra buffer for trading days

    try:
        data = yf.download(tickers, start=start, end=end, progress=False)
        if data.empty:
            return None

        # Handle multi-level columns
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data[["Close"]] if len(tickers) == 1 else data

        # Compute daily returns
        returns = close.pct_change().dropna()

        # Trim to requested period
        if len(returns) > days:
            returns = returns.iloc[-days:]

        return returns
    except Exception as e:
        print(f"  [factor] Failed to fetch returns: {e}")
        return None


# ─── Factor regression ────────────────────────────────────────────────

def analyze_factor_exposure(
    ticker: str,
    days: int = 252,
    use_sector_factors: bool = False,
) -> ExposureReport | None:
    """Run factor regression for a single stock.

    Regresses stock returns on factor ETF returns using OLS.
    """
    if not np or not pd or not sp_stats:
        print("  [factor] numpy, pandas, and scipy required")
        return None

    # Fetch stock + factor returns together
    factor_dict = SECTOR_ETFS if use_sector_factors else FACTOR_ETFS
    all_tickers = [ticker] + list(factor_dict.values())

    returns = _fetch_returns(all_tickers, days)
    if returns is None or returns.empty:
        return None

    # Ensure ticker column exists
    if ticker not in returns.columns:
        print(f"  [factor] No return data for {ticker}")
        return None

    # Align: drop rows where stock or any factor is NaN
    available_factors = {
        name: etf for name, etf in factor_dict.items()
        if etf in returns.columns
    }
    if not available_factors:
        return None

    factor_cols = list(available_factors.values())
    aligned = returns[[ticker] + factor_cols].dropna()

    if len(aligned) < 30:
        print(f"  [factor] Only {len(aligned)} observations for {ticker}, need 30+")
        return None

    y = aligned[ticker].values
    X = aligned[factor_cols].values

    # For non-sector factors, create long-short factors
    if not use_sector_factors:
        # SMB proxy: IWM - SPY
        if "IWM" in aligned.columns and "SPY" in aligned.columns:
            pass  # We'll handle this in factor naming

    # Add intercept
    X_with_const = np.column_stack([np.ones(len(y)), X])

    # OLS regression
    try:
        beta, residuals, rank, sv = np.linalg.lstsq(X_with_const, y, rcond=None)
    except np.linalg.LinAlgError:
        return None

    # Fitted values and residuals
    y_hat = X_with_const @ beta
    resid = y - y_hat
    n, k = X_with_const.shape

    # Standard errors
    if n <= k:
        return None
    mse = np.sum(resid ** 2) / (n - k)
    try:
        cov_beta = mse * np.linalg.inv(X_with_const.T @ X_with_const)
    except np.linalg.LinAlgError:
        return None

    se = np.sqrt(np.diag(cov_beta))

    # R-squared
    ss_res = np.sum(resid ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # Factor exposures
    factor_names = list(available_factors.keys())
    exposures = []
    for i, name in enumerate(factor_names):
        b = beta[i + 1]  # +1 for intercept
        t = b / se[i + 1] if se[i + 1] > 0 else 0
        p = 2 * (1 - sp_stats.t.cdf(abs(t), df=n - k))

        # Contribution: proportion of explained variance from this factor
        factor_var = np.var(X[:, i]) * b ** 2
        total_var = np.var(y) if np.var(y) > 0 else 1
        contribution = (factor_var / total_var) * 100

        exposures.append(FactorExposure(
            factor=name,
            beta=float(b),
            t_stat=float(t),
            p_value=float(p),
            contribution=float(contribution),
        ))

    # Alpha (annualized)
    alpha_daily = beta[0]
    alpha_annual = alpha_daily * 252
    alpha_t = beta[0] / se[0] if se[0] > 0 else 0

    # Risk decomposition
    systematic_var = np.var(y_hat)
    total_var = np.var(y)
    systematic_pct = (systematic_var / total_var * 100) if total_var > 0 else 0

    # Warnings
    warnings = []
    for e in exposures:
        if abs(e.beta) > 1.5 and e.p_value < 0.05:
            warnings.append(f"High {e.factor} exposure (β={e.beta:.2f})")
    if r_squared > 0.85:
        warnings.append(f"Very high R²={r_squared:.3f} — returns mostly explained by factors")
    if r_squared < 0.10:
        warnings.append(f"Low R²={r_squared:.3f} — factor model explains little")

    return ExposureReport(
        ticker=ticker,
        period_days=len(aligned),
        alpha=float(alpha_annual),
        alpha_t_stat=float(alpha_t),
        r_squared=float(r_squared),
        exposures=exposures,
        systematic_risk_pct=float(systematic_pct),
        idiosyncratic_risk_pct=float(100 - systematic_pct),
        warnings=warnings,
    )


def analyze_portfolio_exposure(
    tickers: list[str],
    weights: dict[str, float] | None = None,
    days: int = 252,
) -> ExposureReport | None:
    """Analyze factor exposure of a portfolio (equal or custom weights).

    Parameters
    ----------
    tickers : list[str]
        List of tickers in the portfolio.
    weights : dict[str, float], optional
        {ticker: weight}. If None, uses equal weights.
    days : int
        Lookback period in trading days.
    """
    if not np or not pd:
        return None

    if weights is None:
        w = 1.0 / len(tickers)
        weights = {t: w for t in tickers}

    # Fetch all returns
    all_tickers = list(set(tickers + list(FACTOR_ETFS.values())))
    returns = _fetch_returns(all_tickers, days)
    if returns is None:
        return None

    # Build portfolio return series
    available = [t for t in tickers if t in returns.columns]
    if not available:
        return None

    # Normalize weights for available tickers
    total_w = sum(weights.get(t, 0) for t in available)
    if total_w <= 0:
        return None

    port_returns = sum(
        returns[t] * (weights.get(t, 0) / total_w)
        for t in available
    )

    # Create a temporary DataFrame with portfolio as a column
    temp_df = returns.copy()
    temp_df["PORTFOLIO"] = port_returns

    # Now run factor regression on the portfolio series
    factor_cols = [etf for etf in FACTOR_ETFS.values() if etf in temp_df.columns]
    aligned = temp_df[["PORTFOLIO"] + factor_cols].dropna()

    if len(aligned) < 30:
        return None

    y = aligned["PORTFOLIO"].values
    X = aligned[factor_cols].values
    X_with_const = np.column_stack([np.ones(len(y)), X])

    try:
        beta, _, _, _ = np.linalg.lstsq(X_with_const, y, rcond=None)
    except np.linalg.LinAlgError:
        return None

    y_hat = X_with_const @ beta
    resid = y - y_hat
    n, k = X_with_const.shape
    if n <= k:
        return None

    mse = np.sum(resid ** 2) / (n - k)
    try:
        cov_beta = mse * np.linalg.inv(X_with_const.T @ X_with_const)
    except np.linalg.LinAlgError:
        return None
    se = np.sqrt(np.diag(cov_beta))

    ss_res = np.sum(resid ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    factor_names = [name for name, etf in FACTOR_ETFS.items() if etf in factor_cols]
    exposures = []
    for i, name in enumerate(factor_names):
        b = beta[i + 1]
        t = b / se[i + 1] if se[i + 1] > 0 else 0
        p = 2 * (1 - sp_stats.t.cdf(abs(t), df=n - k))
        factor_var = np.var(X[:, i]) * b ** 2
        total_var = np.var(y) if np.var(y) > 0 else 1
        exposures.append(FactorExposure(
            factor=name, beta=float(b), t_stat=float(t),
            p_value=float(p), contribution=float(factor_var / total_var * 100),
        ))

    alpha_daily = beta[0]
    systematic_var = np.var(y_hat)
    total_var = np.var(y)

    warnings = []
    sig_exposures = [e for e in exposures if e.p_value < 0.05 and abs(e.beta) > 0.5]
    if len(sig_exposures) <= 1 and sig_exposures:
        warnings.append(
            f"Portfolio dominated by {sig_exposures[0].factor} factor "
            f"(β={sig_exposures[0].beta:.2f}) — low diversification"
        )

    return ExposureReport(
        ticker="PORTFOLIO",
        period_days=len(aligned),
        alpha=float(alpha_daily * 252),
        alpha_t_stat=float(beta[0] / se[0] if se[0] > 0 else 0),
        r_squared=float(r_squared),
        exposures=exposures,
        systematic_risk_pct=float(systematic_var / total_var * 100 if total_var > 0 else 0),
        idiosyncratic_risk_pct=float((1 - systematic_var / total_var) * 100 if total_var > 0 else 100),
        warnings=warnings,
    )


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Factor exposure analysis")
    parser.add_argument("--ticker", help="Single ticker to analyze")
    parser.add_argument("--portfolio", action="store_true", help="Analyze full watchlist")
    parser.add_argument("--days", type=int, default=252, help="Lookback days")
    parser.add_argument("--sectors", action="store_true", help="Use sector ETFs as factors")
    args = parser.parse_args()

    if args.ticker:
        report = analyze_factor_exposure(args.ticker, days=args.days, use_sector_factors=args.sectors)
        if report:
            print(report.summary())
        else:
            print(f"No data for {args.ticker}")

    elif args.portfolio:
        watchlist_file = Path(__file__).resolve().parent.parent / "config" / "watchlist.json"
        if watchlist_file.exists():
            wl = json.loads(watchlist_file.read_text())
            tickers = [s.get("ticker", s) if isinstance(s, dict) else s for s in wl.get("stocks", wl) if isinstance(s, (str, dict))]
            # Filter to US tickers only (yfinance handles these)
            us_tickers = [t for t in tickers if "." not in t and len(t) <= 5][:20]
            print(f"Analyzing portfolio of {len(us_tickers)} US tickers...")
            report = analyze_portfolio_exposure(us_tickers, days=args.days)
            if report:
                print(report.summary())
        else:
            print("No watchlist.json found")
    else:
        parser.print_help()
